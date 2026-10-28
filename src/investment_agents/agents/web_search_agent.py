from __future__ import annotations

from dataclasses import asdict

from investment_agents.agents.base import AgentResult
from investment_agents.core.observability import event_recorder
from investment_agents.tools.web_search import WebSearchTool


class WebSearchAgent:
    name = "web_search_agent"
    description = "Finds current web sources and returns cited evidence for research questions."

    def __init__(self, tool: WebSearchTool) -> None:
        self.tool = tool

    def analyze(
        self,
        question: str,
        trace_id: str,
        symbols: list[str] | None = None,
        currencies: list[str] | None = None,
    ) -> AgentResult:
        result = self.tool.search(question)
        event_recorder.record(
            "tool_called",
            self.name,
            f"Called {result.tool_name} for the research question.",
            trace_id,
            asdict(result),
        )
        observations = [
            f"{item['title']}: {item['snippet']}"
            for item in result.data.get("results", [])
        ]
        return AgentResult(
            agent_name=self.name,
            task="web_research",
            summary=" ".join(observations) or result.summary,
            observations=observations or [result.summary],
            tool_calls=[asdict(result)],
            metadata={
                "tool_status": result.status,
                "symbols": symbols or [],
                "currencies": currencies or [],
            },
        )
