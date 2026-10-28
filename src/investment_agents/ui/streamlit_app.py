from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st

from investment_agents.core.messages import initial_chat
from investment_agents.ui.observability import (
    data_source_attention_count,
    data_source_status_rows,
    event_table_rows,
    portfolio_alert_rows,
    source_note_rows,
    trace_metrics,
)

DEFAULT_API_URL = os.getenv("AGENT_API_URL", "http://localhost:8000")


def _api_url() -> str:
    return st.session_state.api_url.rstrip("/")


def check_api_health(api_url: str) -> dict[str, Any]:
    response = requests.get(f"{api_url.rstrip('/')}/health", timeout=5)
    response.raise_for_status()
    return response.json()


def list_agents(api_url: str) -> list[dict[str, str]]:
    response = requests.get(f"{api_url.rstrip('/')}/agents", timeout=5)
    response.raise_for_status()
    return response.json()


def list_tool_readiness(api_url: str) -> list[dict[str, Any]]:
    response = requests.get(f"{api_url.rstrip('/')}/tools/readiness", timeout=5)
    response.raise_for_status()
    return response.json()


def storage_status(api_url: str) -> dict[str, Any]:
    response = requests.get(f"{api_url.rstrip('/')}/storage/status", timeout=5)
    response.raise_for_status()
    return response.json()


def observability_status(api_url: str) -> dict[str, Any]:
    response = requests.get(f"{api_url.rstrip('/')}/observability/status", timeout=5)
    response.raise_for_status()
    return response.json()


def list_observability_events(api_url: str, trace_id: str | None = None) -> list[dict[str, Any]]:
    params = {"trace_id": trace_id} if trace_id else None
    response = requests.get(
        f"{api_url.rstrip('/')}/observability/events",
        params=params,
        timeout=5,
    )
    response.raise_for_status()
    return response.json().get("events", [])


def send_message(api_url: str, message: str) -> dict[str, Any]:
    response = requests.post(
        f"{api_url.rstrip('/')}/chat",
        json={"message": message, "chat": st.session_state.chat},
        timeout=240,
    )
    response.raise_for_status()
    return response.json()


st.set_page_config(page_title="Investment Agents", layout="wide")
st.title("Investment Agents")

st.session_state.setdefault("chat", initial_chat())
st.session_state.setdefault("api_url", DEFAULT_API_URL)
st.session_state.setdefault("last_trace_id", None)
st.session_state.setdefault("last_routing_decision", None)
st.session_state.setdefault("last_agent_results", [])
st.session_state.setdefault("last_trace_events", [])
st.session_state.setdefault("last_source_notes", [])

with st.sidebar:
    st.text_input("Agent API URL", key="api_url")

    if st.button(":material/network_ping: Check status"):
        try:
            health = check_api_health(_api_url())
            st.success(f"{health['status']} - {health['model_id']}")
        except requests.RequestException as exc:
            st.error(f"API unavailable: {exc}")

    if st.button(":material/groups: Show agents"):
        try:
            agents = list_agents(_api_url())
            for agent in agents:
                st.markdown(f"**{agent['name']}**")
                st.caption(agent["description"])
        except requests.RequestException as exc:
            st.error(f"Could not load agents: {exc}")

    if st.button(":material/construction: Tool readiness"):
        try:
            readiness = list_tool_readiness(_api_url())
            for tool in readiness:
                label = "ready" if tool["configured"] else "needs config"
                st.markdown(f"**{tool['tool_name']}** - {label}")
                if tool["missing_settings"]:
                    st.caption("Missing: " + ", ".join(tool["missing_settings"]))
        except requests.RequestException as exc:
            st.error(f"Could not load tool readiness: {exc}")

    if st.button(":material/database: Storage status"):
        try:
            status = storage_status(_api_url())
            st.markdown(f"**DuckDB** - {'created' if status['exists'] else 'not created yet'}")
            st.caption(status["db_path"])
            if status.get("fx_rate_count") is not None:
                st.caption(
                    "Rows: "
                    f"{status.get('raw_payload_count', 0)} raw payloads, "
                    f"{status.get('curated_snapshot_count', 0)} curated snapshots, "
                    f"{status.get('fx_rate_count', 0)} FX rates"
                )
        except requests.RequestException as exc:
            st.error(f"Could not load storage status: {exc}")

    if st.button(":material/monitoring: Observability"):
        try:
            status = observability_status(_api_url())
            mode = "persistent" if status["persistent"] else "memory"
            label = "enabled" if status["enabled"] else "disabled"
            st.markdown(f"**Tracing** - {label}, {mode}")
            st.caption(f"{status['event_count']} events retained")
        except requests.RequestException as exc:
            st.error(f"Could not load observability status: {exc}")

    if st.button(":material/delete: Clear conversation"):
        st.session_state.chat = initial_chat()
        st.session_state.last_trace_id = None
        st.session_state.last_routing_decision = None
        st.session_state.last_agent_results = []
        st.session_state.last_trace_events = []
        st.session_state.last_source_notes = []
        st.rerun()

chat_tab, trace_tab = st.tabs(["Chat", "Trace"])

with chat_tab:
    for message in st.session_state.chat:
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue

        with st.chat_message(role):
            st.write(message.get("content", ""))

with trace_tab:
    if not st.session_state.last_trace_id:
        st.info("Send a message to inspect its route, specialist agents, and tool calls.")
    else:
        st.subheader("Latest trace")
        st.caption(st.session_state.last_trace_id)

        if st.button(":material/refresh: Refresh trace events"):
            try:
                st.session_state.last_trace_events = list_observability_events(
                    _api_url(),
                    st.session_state.last_trace_id,
                )
            except requests.RequestException as exc:
                st.error(f"Could not refresh trace events: {exc}")

        metrics = trace_metrics(st.session_state.last_trace_events)
        alert_rows = portfolio_alert_rows(st.session_state.last_agent_results)
        data_source_rows = data_source_status_rows(st.session_state.last_agent_results)
        source_rows = source_note_rows(st.session_state.last_source_notes)
        with st.container(horizontal=True):
            st.metric("Events", metrics["events"], border=True)
            st.metric("Agents", metrics["agents"], border=True)
            st.metric("Tools", metrics["tools"], border=True)
            st.metric("Alerts", len(alert_rows), border=True)
            st.metric("Source notes", len(source_rows), border=True)
            st.metric("Data warnings", data_source_attention_count(data_source_rows), border=True)

        routing = st.session_state.last_routing_decision or {}
        with st.container(border=True):
            st.markdown("**Routing decision**")
            st.json(routing)

        rows = event_table_rows(st.session_state.last_trace_events)
        with st.container(border=True):
            st.markdown("**Event timeline**")
            if rows:
                st.dataframe(rows, hide_index=True)
            else:
                st.info("No events are available for this trace yet.")

        with st.container(border=True):
            st.markdown("**Portfolio alerts**")
            if alert_rows:
                st.dataframe(alert_rows, hide_index=True)
            else:
                st.success("No portfolio alerts returned for this trace.")

        with st.container(border=True):
            st.markdown("**Data source status**")
            if data_source_rows:
                st.dataframe(data_source_rows, hide_index=True)
            else:
                st.info("No data source status rows are available for this trace.")

        with st.container(border=True):
            st.markdown("**Source notes**")
            if source_rows:
                st.dataframe(source_rows, hide_index=True)
            else:
                st.success("No source notes returned for this trace.")

        with st.expander("Agent results"):
            st.json(st.session_state.last_agent_results)

if prompt := st.chat_input("Ask about a ticker, currency, market trend, or news"):
    with chat_tab:
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Routing through specialist agents..."):
                try:
                    result = send_message(_api_url(), prompt)
                    st.session_state.chat = result["chat"]
                    st.session_state.last_trace_id = result["trace_id"]
                    st.session_state.last_routing_decision = result["routing_decision"]
                    st.session_state.last_agent_results = result["agent_results"]
                    st.session_state.last_source_notes = result.get("source_notes", [])
                    st.session_state.last_trace_events = list_observability_events(
                        _api_url(),
                        result["trace_id"],
                    )
                    st.markdown(result["reply"])
                    st.caption(
                        f"{result['elapsed_seconds']:.2f}s | trace {result['trace_id']} | "
                        f"agents: {', '.join(result['selected_agents'])}"
                    )
                except requests.RequestException as exc:
                    st.session_state.chat = [
                        *st.session_state.chat,
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": f"API error: {exc}"},
                    ]
                    st.error(f"API error: {exc}")
                except Exception as exc:
                    st.session_state.chat = [
                        *st.session_state.chat,
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": "The app could not render this response."},
                    ]
                    st.error(f"Unexpected response error: {exc}")
