from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from investment_agents.agents.alphavantage_agent import AlphaVantageResearchAgent
from investment_agents.agents.base import AgentResult
from investment_agents.agents.finnhub_agent import FinnhubInvestmentAgent
from investment_agents.agents.ledger_agent import LedgerInterpretationAgent
from investment_agents.agents.routing import AgentRouter
from investment_agents.agents.web_search_agent import WebSearchAgent
from investment_agents.core.config import Settings, get_settings
from investment_agents.core.messages import ChatMessage, DEFAULT_MODEL_ID, initial_chat
from investment_agents.core.observability import event_recorder
from investment_agents.domain.models import RouteDecision
from investment_agents.tools.registry import ToolRegistry
from investment_agents.tools.web_search import WebSearchTool


@dataclass
class SourceNote:
    agent_name: str
    status: str
    message: str
    tool_name: str = ""
    symbol: str = ""
    provider_symbol: str = ""
    cache_status: str = ""
    fetched_at: str = ""
    stale_fetched_at: str = ""
    degraded_from_status: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "agent_name": self.agent_name,
            "tool_name": self.tool_name,
            "symbol": self.symbol,
            "provider_symbol": self.provider_symbol,
            "status": self.status,
            "cache_status": self.cache_status,
            "fetched_at": self.fetched_at,
            "stale_fetched_at": self.stale_fetched_at,
            "degraded_from_status": self.degraded_from_status,
            "message": self.message,
        }


@dataclass
class OrchestratorResponse:
    reply: str
    chat: list[ChatMessage]
    elapsed_seconds: float
    model_id: str
    trace_id: str
    selected_agents: list[str]
    agent_results: list[dict]
    routing_decision: dict
    source_notes: list[dict[str, str]]
    citations: list[dict[str, str]]


class OrchestratorAgent:
    name = "orchestrator_agent"
    description = "Routes investment analytics questions to specialist agents and synthesizes findings."

    def __init__(
        self,
        ledger_agent: LedgerInterpretationAgent,
        finnhub_agent: FinnhubInvestmentAgent,
        alphavantage_agent: AlphaVantageResearchAgent,
        model_id: str = DEFAULT_MODEL_ID,
        web_search_agent: WebSearchAgent | None = None,
    ) -> None:
        self.ledger_agent = ledger_agent
        self.finnhub_agent = finnhub_agent
        self.alphavantage_agent = alphavantage_agent
        self.web_search_agent = web_search_agent or WebSearchAgent(WebSearchTool())
        self.model_id = model_id
        self.router = AgentRouter(
            ledger_agent,
            finnhub_agent,
            alphavantage_agent,
            self.web_search_agent,
        )

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "OrchestratorAgent":
        settings = settings or get_settings()
        return cls.from_tool_registry(ToolRegistry.from_settings(settings), model_id=settings.model_id)

    @classmethod
    def from_tool_registry(
        cls,
        registry: ToolRegistry,
        model_id: str = DEFAULT_MODEL_ID,
    ) -> "OrchestratorAgent":
        return cls(
            ledger_agent=LedgerInterpretationAgent(registry.ledger),
            finnhub_agent=FinnhubInvestmentAgent(registry.finnhub, settings=registry.settings),
            alphavantage_agent=AlphaVantageResearchAgent(registry.alphavantage, settings=registry.settings),
            model_id=model_id,
            web_search_agent=WebSearchAgent(registry.web_search),
        )

    def available_agents(self) -> list[dict[str, str]]:
        return [
            {"name": self.ledger_agent.name, "description": self.ledger_agent.description},
            {"name": self.finnhub_agent.name, "description": self.finnhub_agent.description},
            {"name": self.alphavantage_agent.name, "description": self.alphavantage_agent.description},
            {"name": self.web_search_agent.name, "description": self.web_search_agent.description},
        ]

    def respond(
        self,
        message: str,
        chat: list[ChatMessage] | None = None,
    ) -> OrchestratorResponse:
        message = message.strip()
        if not message:
            raise ValueError("message cannot be empty")

        trace_id = event_recorder.new_trace_id()
        start = perf_counter()
        selected_agents, routing_decision = self.router.route(message)
        event_recorder.record(
            "orchestrator_decision",
            self.name,
            "Selected specialist agents for the user request.",
            trace_id,
            {"message": message, "routing_decision": routing_decision.to_dict()},
        )

        results: list[AgentResult] = []
        symbol_hints: list[str] = []
        for agent in selected_agents:
            if agent.name == self.ledger_agent.name:
                result = agent.analyze(message, trace_id)
                results.append(result)
                symbol_hints = _symbols_from_ledger_result(result, message)
                if symbol_hints:
                    event_recorder.record(
                        "symbol_context_derived",
                        self.name,
                        "Derived ticker symbols from ledger/watchlist context.",
                        trace_id,
                        {"symbols": symbol_hints},
                    )
                continue

            result = agent.analyze(
                message,
                trace_id,
                symbols=symbol_hints,
                currencies=routing_decision.currency_codes,
            )
            results.append(result)

        source_notes = _source_status_notes(results)
        citations = _citations_from_results(results)
        reply = self._synthesize(
            message,
            results,
            trace_id,
            routing_decision,
            source_notes,
            citations,
        )
        next_chat = list(chat or initial_chat())
        next_chat.append({"role": "user", "content": message})
        next_chat.append({"role": "assistant", "content": reply})
        elapsed = perf_counter() - start

        return OrchestratorResponse(
            reply=reply,
            chat=next_chat,
            elapsed_seconds=elapsed,
            model_id=self.model_id,
            trace_id=trace_id,
            selected_agents=[agent.name for agent in selected_agents],
            agent_results=[result.to_dict() for result in results],
            routing_decision=routing_decision.to_dict(),
            source_notes=[note.to_dict() for note in source_notes],
            citations=citations,
        )

    def _synthesize(
        self,
        question: str,
        results: list[AgentResult],
        trace_id: str,
        routing_decision: RouteDecision,
        source_notes: list[SourceNote] | None = None,
        citations: list[dict[str, str]] | None = None,
    ) -> str:
        sections = [
            f"Research: {question}",
            (
                "Coverage: "
                f"{', '.join(routing_decision.focus_areas)}"
                if routing_decision.focus_areas
                else "Coverage: general research"
            ),
            "",
        ]
        if routing_decision.currency_codes:
            sections.append(
                "FX rates are point-in-time cross-rates; a directional trend needs "
                "historical rate data."
            )
            sections.append("")
        citations = citations if citations is not None else _citations_from_results(results)
        citation_ids = _citation_ids_by_tool_call(results, citations)
        citations_by_id = {citation["id"]: citation for citation in citations}
        for result in results:
            if result.tool_calls:
                for tool_call in result.tool_calls:
                    summary = str(tool_call.get("summary", ""))
                    if not summary:
                        continue
                    references = citation_ids.get(id(tool_call), [])
                    if references:
                        for citation_id in references:
                            citation = citations_by_id[citation_id]
                            claim = citation.get("claim") or summary
                            sections.append(f"- {claim} [{citation_id}]")
                    else:
                        sections.append(f"- {summary}")
            else:
                sections.append(f"- {result.summary}")

        source_notes = source_notes if source_notes is not None else _source_status_notes(results)
        if source_notes:
            sections.extend(["", "Data limitations:"])
            sections.extend(f"- {note.message}" for note in source_notes)

        if citations:
            sections.extend(["", "Sources:"])
            for citation in citations:
                citation_id = citation["id"]
                title = citation["title"]
                source = citation["source"]
                url = citation["url"]
                date = citation.get("published_at") or citation.get("retrieved_at", "")
                date_note = f" ({date})" if date else ""
                sections.append(f"[{citation_id}] [{title}]({url}) — {source}{date_note}")

        sections.extend(
            [
                "",
                f"Trace ID: {trace_id}",
            ]
        )
        return "\n".join(sections)


ATTENTION_STATUSES = {
    "malformed_response",
    "needs_configuration",
    "needs_symbol",
    "provider_error",
    "rate_limited",
    "stale_cache",
}


def _source_status_notes(results: list[AgentResult]) -> list[SourceNote]:
    notes: list[SourceNote] = []
    for result in results:
        if result.tool_calls:
            for tool_call in result.tool_calls:
                note = _tool_call_source_note(result.agent_name, tool_call)
                if note:
                    notes.append(note)
            continue

        status = str((result.metadata or {}).get("tool_status", ""))
        if status in ATTENTION_STATUSES:
            notes.append(
                SourceNote(
                    agent_name=result.agent_name,
                    status=status,
                    message=f"{result.agent_name}: {_status_label(status)} - {result.summary}",
                )
            )
    return notes


def _citations_from_results(results: list[AgentResult]) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    for result in results:
        for tool_call in result.tool_calls:
            data = tool_call.get("data") or {}
            for citation in data.get("citations") or []:
                if not isinstance(citation, dict) or not citation.get("url"):
                    continue
                citations.append(
                    {
                        "id": str(len(citations) + 1),
                        "agent_name": result.agent_name,
                        "tool_name": str(tool_call.get("tool_name", "")),
                        "title": str(citation.get("title", "Source")),
                        "url": str(citation["url"]),
                        "source": str(citation.get("source", result.agent_name)),
                        "claim": str(citation.get("claim", "")),
                        "published_at": str(citation.get("published_at", "")),
                        "retrieved_at": str(citation.get("retrieved_at", "")),
                    }
                )
    return citations


def _citation_ids_by_tool_call(
    results: list[AgentResult],
    citations: list[dict[str, str]],
) -> dict[int, list[str]]:
    grouped: dict[int, list[str]] = {}
    citation_iterator = iter(citations)
    for result in results:
        for tool_call in result.tool_calls:
            raw_citations = (tool_call.get("data") or {}).get("citations") or []
            count = sum(
                1
                for citation in raw_citations
                if isinstance(citation, dict) and citation.get("url")
            )
            grouped[id(tool_call)] = [
                next(citation_iterator)["id"]
                for _ in range(count)
            ]
    return grouped


def _tool_call_source_note(agent_name: str, tool_call: dict) -> SourceNote | None:
    status = str(tool_call.get("status", ""))
    if status not in ATTENTION_STATUSES:
        return None

    data = tool_call.get("data") or {}
    symbol = str(data.get("symbol", ""))
    provider_symbol = str(data.get("provider_symbol", ""))
    symbol_text = _symbol_text(symbol, provider_symbol)
    tool_name = str(tool_call.get("tool_name", ""))
    prefix = f"{agent_name}/{tool_name}"
    if symbol_text:
        prefix = f"{prefix} {symbol_text}"
    cache_status = str(data.get("cache_status", ""))
    fetched_at = str(data.get("fetched_at", ""))
    stale_at = str(data.get("stale_fetched_at", ""))
    degraded_from = data.get("degraded_from") or {}
    degraded_status = ""
    if isinstance(degraded_from, dict):
        degraded_status = str(degraded_from.get("status", ""))

    if status == "stale_cache":
        source = f" after {_status_label(degraded_status)}" if degraded_status else ""
        timestamp = f" from {stale_at}" if stale_at else ""
        return SourceNote(
            agent_name=agent_name,
            tool_name=tool_name,
            symbol=symbol,
            provider_symbol=provider_symbol,
            status=status,
            cache_status=cache_status,
            fetched_at=fetched_at or stale_at,
            stale_fetched_at=stale_at,
            degraded_from_status=degraded_status,
            message=f"{prefix}: using stale cached data{timestamp}{source}.",
        )

    return SourceNote(
        agent_name=agent_name,
        tool_name=tool_name,
        symbol=symbol,
        provider_symbol=provider_symbol,
        status=status,
        cache_status=cache_status,
        fetched_at=fetched_at,
        stale_fetched_at=stale_at,
        degraded_from_status=degraded_status,
        message=f"{prefix}: {_status_label(status)} - {tool_call.get('summary', '')}",
    )


def _symbol_text(symbol: str, provider_symbol: str) -> str:
    if symbol and provider_symbol and symbol != provider_symbol:
        return f"{symbol} ({provider_symbol})"
    return symbol or provider_symbol


def _status_label(status: str) -> str:
    return status.replace("_", " ") if status else ""


def _symbols_from_ledger_result(result: AgentResult, question: str) -> list[str]:
    metadata = result.metadata or {}
    portfolio_summary = metadata.get("portfolio_summary") or {}
    watchlist_summary = metadata.get("watchlist_summary") or {}
    normalized = question.lower()
    if "watchlist" in normalized or "watch list" in normalized:
        summaries = [watchlist_summary]
    elif "holding" in normalized or "holdings" in normalized or "portfolio" in normalized:
        summaries = [portfolio_summary]
    else:
        summaries = [portfolio_summary, watchlist_summary]

    symbols: list[str] = []
    for summary in summaries:
        for symbol in summary.get("symbols", []):
            if symbol and symbol not in symbols:
                symbols.append(symbol)
    return symbols
