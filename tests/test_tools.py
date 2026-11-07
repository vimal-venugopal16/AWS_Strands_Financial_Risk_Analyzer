"""Tests for the data-access tools. AWS is mocked with moto; no credentials needed."""

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import tools  # noqa: E402
from config import settings  # noqa: E402


# ---------- pure helpers ----------
def test_redact_drops_identifiers_case_insensitively():
    rec = {"FName": "Ava", "SSN": "1", "License": "2", "Passport": "3", "Email": "e", "Phone": "p", "Age": 30}
    assert tools.redact(rec) == {"FName": "Ava", "Age": 30}


@pytest.mark.parametrize("query", ["Ava Wilson", "wilson ava", "Wilson, Ava", "  AVA   WILSON "])
def test_name_matching_accepts_either_order(query):
    assert tools.matches_any_name({"FirstName": "Ava", "LastName": "Wilson"}, [query])


def test_name_matching_rejects_partial_names():
    assert not tools.matches_any_name({"FName": "Ava", "LName": "Wilson"}, ["Ava"])


def test_filter_without_names_returns_all_redacted():
    rows = [{"FName": "A", "LName": "B", "SSN": "x"}, {"FName": "C", "LName": "D", "SSN": "y"}]
    assert tools.filter_records(rows, None) == [{"FName": "A", "LName": "B"}, {"FName": "C", "LName": "D"}]


# ---------- tools against mocked AWS ----------
@pytest.fixture
def aws():
    with mock_aws():
        tools._s3.cache_clear()
        tools._profile_table.cache_clear()

        s3 = boto3.client("s3", region_name=settings.aws_region)
        s3.create_bucket(Bucket=settings.credit_bucket)
        csv_body = (ROOT / "customer_financial_info_updated.csv").read_bytes()
        s3.put_object(Bucket=settings.credit_bucket, Key=settings.credit_key, Body=csv_body)

        ddb = boto3.resource("dynamodb", region_name=settings.aws_region)
        table = ddb.create_table(
            TableName=settings.profile_table,
            KeySchema=[{"AttributeName": "customerid", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "customerid", "AttributeType": "N"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.put_item(Item={"customerid": Decimal(397381), "FName": "Ava", "LName": "Wilson",
                             "SSN": "537-62-3727", "Age": Decimal(55), "Occupation": "Consultant"})
        table.put_item(Item={"customerid": Decimal(498475), "FName": "David", "LName": "Miller",
                             "SSN": "593-91-1415", "Age": Decimal(35), "Occupation": "Teacher"})
        yield
        tools._s3.cache_clear()
        tools._profile_table.cache_clear()


def _call(tool_fn, **kwargs):
    return json.loads(tool_fn(**kwargs))


def test_credit_tool_filters_and_redacts(aws):
    out = _call(tools.read_customer_creditdata, customer_names=["Ava Wilson", "Nobody Here"])
    assert out["count"] == 1
    rec = out["records"][0]
    assert rec["FirstName"] == "Ava" and rec["LoanType"] == "Home Loan"
    assert "Email" not in rec and "Phone" not in rec
    assert out["not_found"] == ["Nobody Here"]


def test_profile_tool_filters_redacts_and_serializes_decimals(aws):
    out = _call(tools.read_customer_profile, customer_names=["Miller David"])
    assert out["count"] == 1
    rec = out["records"][0]
    assert rec["Age"] == 35 and rec["customerid"] == 498475
    assert "SSN" not in rec


def test_tool_returns_error_json_instead_of_raising(aws):
    boto3.client("s3", region_name=settings.aws_region).delete_object(
        Bucket=settings.credit_bucket, Key=settings.credit_key
    )
    out = _call(tools.read_customer_creditdata, customer_names=["Ava Wilson"])
    assert "error" in out
