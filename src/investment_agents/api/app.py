from __future__ import annotations

from threading import Lock

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from investment_agents.agents.orchestrator import OrchestratorAgent
from investment_agents.api.schemas import (
    AgentCard,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ObservabilityStatusResponse,
    StorageStatusResponse,
    TraceEventResponse,
    ToolReadinessCard,
)
from investment_agents.core.config import get_settings
from investment_agents.core.observability import event_recorder
from investment_agents.tools.registry import ToolRegistry

settings = get_settings()
event_recorder.configure(
    enabled=settings.observability_enabled,
    log_path=settings.observability_log_path,
    max_events=settings.observability_max_events,
)
tool_registry = ToolRegistry.from_settings(settings)
orchestrator = OrchestratorAgent.from_tool_registry(tool_registry, model_id=settings.model_id)
orchestrator_lock = Lock()

app = FastAPI(
    title=settings.app_name,
    description="Investment analytics multi-agent API.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.environment,
        model_id=settings.model_id,
    )


@app.get("/agents", response_model=list[AgentCard])
def list_agents() -> list[AgentCard]:
    return [AgentCard(**agent) for agent in orchestrator.available_agents()]


@app.get("/tools/readiness", response_model=list[ToolReadinessCard])
def tool_readiness() -> list[ToolReadinessCard]:
    return [ToolReadinessCard(**item) for item in tool_registry.readiness_dicts()]


@app.get("/storage/status", response_model=StorageStatusResponse)
def storage_status() -> StorageStatusResponse:
    return StorageStatusResponse(**tool_registry.storage_status())


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        with orchestrator_lock:
            result = orchestrator.respond(request.message, chat=request.chat)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    return ChatResponse(
        reply=result.reply,
        chat=result.chat,
        elapsed_seconds=result.elapsed_seconds,
        model_id=result.model_id,
        trace_id=result.trace_id,
        selected_agents=result.selected_agents,
        agent_results=result.agent_results,
        routing_decision=result.routing_decision,
        source_notes=result.source_notes,
        citations=result.citations,
    )


@app.get("/observability/events", response_model=TraceEventResponse)
def list_events(trace_id: str | None = Query(default=None)) -> TraceEventResponse:
    return TraceEventResponse(events=event_recorder.list_events(trace_id=trace_id))


@app.get("/observability/status", response_model=ObservabilityStatusResponse)
def observability_status() -> ObservabilityStatusResponse:
    return ObservabilityStatusResponse(**event_recorder.status())
