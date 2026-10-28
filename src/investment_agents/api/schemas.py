from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from investment_agents.core.messages import ChatMessage


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    chat: list[ChatMessage] | None = None


class ChatResponse(BaseModel):
    reply: str
    chat: list[ChatMessage]
    elapsed_seconds: float
    model_id: str
    trace_id: str
    selected_agents: list[str]
    agent_results: list[dict[str, Any]]
    routing_decision: dict[str, Any]
    source_notes: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, str]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    model_id: str


class AgentCard(BaseModel):
    name: str
    description: str


class ToolReadinessCard(BaseModel):
    tool_name: str
    configured: bool
    status: str
    missing_settings: list[str]
    capabilities: list[str]


class TraceEventResponse(BaseModel):
    events: list[dict[str, Any]]


class ObservabilityStatusResponse(BaseModel):
    enabled: bool
    persistent: bool
    log_path: str | None
    max_events: int
    event_count: int


class StorageStatusResponse(BaseModel):
    db_path: str
    exists: bool
    raw_payload_count: int | None = None
    curated_snapshot_count: int | None = None
    fx_rate_count: int | None = None
