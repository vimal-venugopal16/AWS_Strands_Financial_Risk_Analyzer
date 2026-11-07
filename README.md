# Financial Risk Analyzer

A multi-agent credit risk analyzer built with the [Strands Agents SDK](https://strandsagents.com) on Amazon Bedrock.
A **Swarm** of four specialized agents pulls customer financial data (S3) and profile data (DynamoDB),
weighs it against market conditions, and returns a per-customer risk rating with justification,
through a Streamlit dashboard.

## Architecture

```
            ┌──────────────────┐   handoff   ┌──────────────────┐   handoff   ┌──────────────────┐   handoff   ┌──────────────────┐
 prompt ──▶ │ financial_agent  │ ──────────▶ │  profile_agent   │ ──────────▶ │   market_agent   │ ──────────▶ │ summarizer_agent │ ──▶ risk report
            │ tool: S3 CSV     │             │ tool: DynamoDB   │             │ (no tools)       │             │ final ratings    │
            └──────────────────┘             └──────────────────┘             └──────────────────┘             └──────────────────┘
```

| Agent | Data source | Role |
|---|---|---|
| `financial_agent` | S3 CSV via `read_customer_creditdata` | Loan type, amount, occupation, repayment signals |
| `profile_agent` | DynamoDB via `read_customer_profile` | Profile attributes; cross-checks financial data |
| `market_agent` | Model knowledge only | Macro / employment risk by occupation and loan type |
| `summarizer_agent` | Other agents' output | Very High / High / Medium / Low rating, drivers, action |

The swarm starts at `financial_agent`; agents decide handoffs themselves, bounded by the limits in `config.py`.

### Data handling

- Tools take the customer names from the request and return **only those customers**, not the whole dataset.
- Direct identifiers (`SSN`, `License`, `Passport`, `Email`, `Phone`) are **stripped before data reaches the model**
  (see `REDACTED_FIELDS` in `tools.py`).
- The summarizer is instructed not to base ratings on marital status, health condition or age.
- The sample CSVs in this repo contain synthetic data only.

## Project structure

```
├── agents.py            # build_swarm(): agent + swarm definitions (also runnable as a CLI)
├── tools.py             # S3 / DynamoDB tools with name filtering and PII redaction
├── prompts.py           # System prompts for each agent
├── config.py            # Settings from environment variables
├── dashboard.py         # Streamlit UI with live per-agent progress
├── tests/test_tools.py  # Tool tests (AWS mocked with moto)
├── customer_financial_info_updated.csv   # sample data for the S3 bucket
├── customer_profiles.csv                 # sample data for the DynamoDB table
└── ptr_streamlit_ec2_terraform_module-main.zip  # Terraform module to host the app on EC2
```

## Getting started

### Prerequisites

- Python 3.10+
- AWS credentials with access to:
  - Amazon Bedrock, with model access enabled for the configured model
  - `s3:GetObject` on the credit-data object
  - `dynamodb:Scan` on the profile table

### Install

```bash
git clone https://github.com/vimal-venugopal16/AWS_Strands_Financial_Risk_Analyzer.git
cd AWS_Strands_Financial_Risk_Analyzer
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

All settings have defaults and can be overridden with environment variables:

| Variable | Default |
|---|---|
| `AWS_REGION` | `us-east-1` |
| `RISK_MODEL_ID` | `us.anthropic.claude-3-7-sonnet-20250219-v1:0` |
| `RISK_CREDIT_BUCKET` | `awsstrands-riskanalyzer` |
| `RISK_CREDIT_KEY` | `bank_customer_repayment_data.csv` |
| `RISK_PROFILE_TABLE` | `riskanalysis_customer_profilesV1` |
| `RISK_MAX_HANDOFFS` / `RISK_MAX_ITERATIONS` | `20` / `20` |
| `RISK_EXECUTION_TIMEOUT` / `RISK_NODE_TIMEOUT` (seconds) | `900` / `300` |

### Run

```bash
# Dashboard
streamlit run dashboard.py

# Or from the command line
python agents.py "Analyze Ava Wilson and David Miller and provide a risk rating."
```

Example prompt:

> Analyze the following customers based on profile, financial, and market information and provide a risk rating: Ava Brown, Wood Gregory, Fuller Crystal, Mills Susan

Names can be given as "First Last" or "Last First".

### Test

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Deployment

`ptr_streamlit_ec2_terraform_module-main.zip` contains a Terraform module that provisions an EC2 instance
with an IAM role to run the Streamlit app. A GitHub Codespaces dev container is also included (`.devcontainer/`).

## Author

**Vimal Venugopal**
