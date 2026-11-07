"""Streamlit front end for the Financial Risk Analyzer swarm.

Run with:  streamlit run dashboard.py
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import streamlit as st

from agents import AGENT_ORDER, build_swarm

AGENT_LABELS = {
    "financial_agent": "💰 Financial Data Agent",
    "profile_agent": "🪪 Customer Profile Agent",
    "market_agent": "📈 Market Analysis Agent",
    "summarizer_agent": "🧾 Summarizer Agent",
}

EXAMPLE_PROMPT = (
    "Analyze the following customers based on profile, financial, and market information "
    "and provide a risk rating: Ava Brown, Wood Gregory, Fuller Crystal, Mills Susan"
)


def to_text(result: Any) -> str:
    """Plain text from a NodeResult / AgentResult / exception."""
    if result is None:
        return ""
    if isinstance(result, Exception):
        return f"⚠️ {type(result).__name__}: {result}"
    inner = getattr(result, "result", None)
    if inner is not None and inner is not result:
        return to_text(inner)
    return str(result).strip()


async def run_swarm(prompt: str, status, progress, log) -> Any:
    """Stream swarm events, updating the UI as each agent starts and finishes."""
    swarm = build_swarm()
    final = None
    done: set[str] = set()

    async for event in swarm.stream_async(prompt):
        kind = event.get("type")
        if kind == "multiagent_node_start":
            node = event["node_id"]
            status.update(label=f"Running {AGENT_LABELS.get(node, node)}…")
        elif kind == "multiagent_handoff":
            src = ", ".join(event.get("from_node_ids", []))
            dst = ", ".join(event.get("to_node_ids", []))
            log.caption(f"↪️ Handoff: {src} → {dst}")
        elif kind == "multiagent_node_stop":
            node = event["node_id"]
            done.add(node)
            node_result = event["node_result"]
            with log.expander(f"{AGENT_LABELS.get(node, node)} — {node_result.execution_time / 1000:.1f}s"):
                st.markdown(to_text(node_result))
            progress.progress(min(len(done & set(AGENT_ORDER)) / len(AGENT_ORDER), 1.0))
        elif kind == "multiagent_result":
            final = event["result"]
    return final


def render_summary(result) -> str:
    summary = result.results.get("summarizer_agent")
    if summary is not None:
        return to_text(summary)
    # Fallback: the swarm stopped before summarizing — show whatever each agent produced.
    parts = [f"### {AGENT_LABELS.get(name, name)}\n{to_text(r)}" for name, r in result.results.items()]
    return "⚠️ The summarizer did not run. Partial results:\n\n" + "\n\n".join(parts)


# -------------------------------
# Page
# -------------------------------
st.set_page_config(page_title="Customer Financial Risk Analyzer", layout="wide")
st.markdown(
    "<h1 style='text-align:center;font-family:verdana;font-size:30px;'>Customer Financial Risk Analyzer</h1>",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        "Evaluates a customer's financial data, profile and current market conditions with a "
        "swarm of AI agents, and assigns a risk rating with justification for credit decisions."
    )
    st.header("Example prompt")
    st.code(EXAMPLE_PROMPT, language=None, wrap_lines=True)
    if st.button("Clear history"):
        st.session_state.history = []

st.session_state.setdefault("history", [])
for turn in st.session_state.history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])

if prompt := st.chat_input("Enter customers to analyze…"):
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        progress = st.progress(0.0)
        started = time.perf_counter()
        status = st.status("Starting risk-analysis swarm…", expanded=False)
        log = st.container()
        with status:
            try:
                result = asyncio.run(run_swarm(prompt, status, progress, log))
            except Exception as exc:  # surface AWS / Bedrock errors instead of a stack trace
                status.update(label="❌ Swarm failed", state="error", expanded=True)
                st.error(f"{type(exc).__name__}: {exc}")
                st.info("Check AWS credentials, region, Bedrock model access, and the S3/DynamoDB settings.")
                st.stop()

            if result is None:
                status.update(label="❌ Swarm returned no result", state="error")
                st.stop()

            elapsed = time.perf_counter() - started
            path = " → ".join(n.node_id for n in result.node_history)
            status.update(label=f"✅ Swarm {result.status.value} in {elapsed:.0f}s", state="complete", expanded=False)
        progress.progress(1.0)

        st.caption(f"Agent path: {path}")
        usage = result.accumulated_usage or {}
        if usage:
            c1, c2, c3 = st.columns(3)
            c1.metric("Input tokens", f"{usage.get('inputTokens', 0):,}")
            c2.metric("Output tokens", f"{usage.get('outputTokens', 0):,}")
            c3.metric("Handoffs", max(len(result.node_history) - 1, 0))

        st.subheader("Final risk assessment")
        summary = render_summary(result)
        st.markdown(summary)
        st.session_state.history.append({"role": "assistant", "content": summary})
