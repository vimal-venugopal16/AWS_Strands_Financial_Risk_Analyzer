"""Data-access tools exposed to the swarm agents.

Both tools:
- take the customer names from the request, so the model fetches only what it needs
  instead of the whole dataset;
- strip direct identifiers (SSN, licence, passport, email, phone) before anything
  reaches the model;
- return JSON strings, so DynamoDB Decimal values serialize cleanly.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from decimal import Decimal
from functools import lru_cache
from typing import Any, Iterable

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from strands import tool

from config import settings

logger = logging.getLogger(__name__)

# Fields never sent to the LLM. Compared case-insensitively.
REDACTED_FIELDS = {"ssn", "license", "passport", "email", "phone"}

# Column names used for first/last name across the two data sources.
FIRST_NAME_FIELDS = ("firstname", "fname")
LAST_NAME_FIELDS = ("lastname", "lname")


# -------------------------------
# Pure helpers (unit-testable without AWS)
# -------------------------------
def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().replace(",", " ").split())


def _get_ci(record: dict, candidates: Iterable[str]) -> str:
    lowered = {k.lower(): v for k, v in record.items()}
    for name in candidates:
        if name in lowered:
            return _norm(lowered[name])
    return ""


def redact(record: dict) -> dict:
    """Drop direct identifiers from a record."""
    return {k: v for k, v in record.items() if k.lower() not in REDACTED_FIELDS}


def matches_any_name(record: dict, names: list[str]) -> bool:
    """True if the record's name matches one of `names`.

    Accepts "First Last", "Last First" or "Last, First", case-insensitively.
    """
    first = _get_ci(record, FIRST_NAME_FIELDS)
    last = _get_ci(record, LAST_NAME_FIELDS)
    if not first and not last:
        return False
    candidates = {f"{first} {last}".strip(), f"{last} {first}".strip()}
    return any(_norm(n) in candidates for n in names)


def filter_records(records: Iterable[dict], names: list[str] | None) -> list[dict]:
    """Return redacted records, filtered to `names` when given."""
    wanted = [n for n in (names or []) if n and n.strip()]
    selected = [r for r in records if not wanted or matches_any_name(r, wanted)]
    return [redact(r) for r in selected]


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    raise TypeError(f"Unserializable type: {type(obj).__name__}")


def _to_json(records: list[dict], names: list[str] | None) -> str:
    payload: dict[str, Any] = {"count": len(records), "records": records}
    if names:
        payload["not_found"] = [n for n in names if not any(matches_any_name(r, [n]) for r in records)]
    return json.dumps(payload, default=_json_default)


# -------------------------------
# AWS clients (created once, reused across calls)
# -------------------------------
@lru_cache(maxsize=1)
def _s3():
    return boto3.client("s3", region_name=settings.aws_region)


@lru_cache(maxsize=1)
def _profile_table():
    return boto3.resource("dynamodb", region_name=settings.aws_region).Table(settings.profile_table)


# -------------------------------
# Tools
# -------------------------------
@tool
def read_customer_creditdata(customer_names: list[str] | None = None) -> str:
    """Fetch loan and repayment records for customers from the credit data store (S3).

    Args:
        customer_names: Customer full names to look up, e.g. ["Ava Brown", "Wood Gregory"].
            Leave empty to return every customer.

    Returns:
        JSON with `count`, `records` and, when names are given, `not_found`.
    """
    try:
        obj = _s3().get_object(Bucket=settings.credit_bucket, Key=settings.credit_key)
        text = obj["Body"].read().decode("utf-8-sig")
    except (ClientError, BotoCoreError) as exc:
        logger.exception("Failed to read credit data from S3")
        return json.dumps({"error": f"Could not read credit data: {exc}"})

    records = list(csv.DictReader(io.StringIO(text)))
    return _to_json(filter_records(records, customer_names), customer_names)


@tool
def read_customer_profile(customer_names: list[str] | None = None) -> str:
    """Fetch customer profile records (occupation, demographics, insurance) from DynamoDB.

    Args:
        customer_names: Customer full names to look up, e.g. ["Ava Brown", "Wood Gregory"].
            Leave empty to return every customer.

    Returns:
        JSON with `count`, `records` and, when names are given, `not_found`.
    """
    try:
        table = _profile_table()
        items: list[dict] = []
        kwargs: dict[str, Any] = {}
        while True:
            response = table.scan(**kwargs)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    except (ClientError, BotoCoreError) as exc:
        logger.exception("Failed to read customer profiles from DynamoDB")
        return json.dumps({"error": f"Could not read customer profiles: {exc}"})

    return _to_json(filter_records(items, customer_names), customer_names)
