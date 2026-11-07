"""Agent and swarm definitions for the Financial Risk Analyzer."""

from __future__ import annotations

from strands import Agent
from strands.models import BedrockModel
from strands.multiagent import Swarm

import prompts
import tools
from config import Settings, settings as default_settings

# Execution order shown in the UI; the swarm itself decides handoffs at runtime.
AGENT_ORDER = ["financial_agent", "profile_agent", "market_agent", "summarizer_agent"]


def build_swarm(cfg: Settings = default_settings) -> Swarm:
    """Create a fresh swarm.

    Build one per request: Strands agents keep conversation history, so a swarm
    shared at module level would leak context between users and runs.
    """
    model = BedrockModel(model_id=cfg.model_id, region_name=cfg.aws_region)

    financial_agent = Agent(
        name="financial_agent",
        description="Retrieves and analyzes customer loan and repayment data from S3.",
        model=model,
        tools=[tools.read_customer_creditdata],
        system_prompt=prompts.FINANCE_SYSTEM_PROMPT,
        callback_handler=None,
    )
    profile_agent = Agent(
        name="profile_agent",
        description="Retrieves customer profile data from DynamoDB.",
        model=model,
        tools=[tools.read_customer_profile],
        system_prompt=prompts.PROFILE_SYSTEM_PROMPT,
        callback_handler=None,
    )
    market_agent = Agent(
        name="market_agent",
        description="Assesses macroeconomic and employment risk for each customer's occupation.",
        model=model,
        system_prompt=prompts.MARKET_SYSTEM_PROMPT,
        callback_handler=None,
    )
    summarizer_agent = Agent(
        name="summarizer_agent",
        description="Combines all findings into a per-customer risk rating. Final step.",
        model=model,
        system_prompt=prompts.SUMMARIZER_SYSTEM_PROMPT,
        callback_handler=None,
    )

    return Swarm(
        [financial_agent, profile_agent, market_agent, summarizer_agent],
        entry_point=financial_agent,
        max_handoffs=cfg.max_handoffs,
        max_iterations=cfg.max_iterations,
        execution_timeout=cfg.execution_timeout,
        node_timeout=cfg.node_timeout,
        repetitive_handoff_detection_window=8,
        repetitive_handoff_min_unique_agents=3,
    )


if __name__ == "__main__":
    import sys

    task = " ".join(sys.argv[1:]) or "Analyze Ava Brown and provide a risk rating."
    result = build_swarm()(task)
    print(f"Status: {result.status}")
    print(f"Path:   {' -> '.join(n.node_id for n in result.node_history)}")
    final = result.results.get("summarizer_agent")
    print(final.result if final else "(no summary produced)")
