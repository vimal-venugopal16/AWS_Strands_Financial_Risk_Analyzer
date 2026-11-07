"""Runtime settings, read from environment variables with sensible defaults.

Override any of these without touching code, e.g.:
    export RISK_MODEL_ID="us.anthropic.claude-sonnet-4-20250514-v1:0"
    export RISK_PROFILE_TABLE="my_profiles_table"
"""

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


@dataclass(frozen=True)
class Settings:
    # Bedrock model used by every agent in the swarm.
    model_id: str = field(
        default_factory=lambda: _env("RISK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
    )
    aws_region: str = field(default_factory=lambda: _env("AWS_REGION", "us-east-1"))

    # Data sources.
    credit_bucket: str = field(default_factory=lambda: _env("RISK_CREDIT_BUCKET", "awsstrands-riskanalyzer"))
    credit_key: str = field(default_factory=lambda: _env("RISK_CREDIT_KEY", "bank_customer_repayment_data.csv"))
    profile_table: str = field(default_factory=lambda: _env("RISK_PROFILE_TABLE", "riskanalysis_customer_profilesV1"))

    # Swarm limits.
    max_handoffs: int = field(default_factory=lambda: int(_env("RISK_MAX_HANDOFFS", "20")))
    max_iterations: int = field(default_factory=lambda: int(_env("RISK_MAX_ITERATIONS", "20")))
    execution_timeout: float = field(default_factory=lambda: float(_env("RISK_EXECUTION_TIMEOUT", "900")))
    node_timeout: float = field(default_factory=lambda: float(_env("RISK_NODE_TIMEOUT", "300")))


settings = Settings()
