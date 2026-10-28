from __future__ import annotations

from dataclasses import asdict

from investment_agents.agents.base import AgentResult
from investment_agents.core.observability import event_recorder
from investment_agents.tools.google_sheets_ledger import GoogleSheetsLedgerTool


class LedgerInterpretationAgent:
    name = "ledger_interpretation_agent"
    description = "Interprets portfolio ledger activity, profit/loss, allocation, and exposure."

    def __init__(self, tool: GoogleSheetsLedgerTool) -> None:
        self.tool = tool

    def analyze(
        self,
        question: str,
        trace_id: str,
        symbols: list[str] | None = None,
        currencies: list[str] | None = None,
    ) -> AgentResult:
        event_recorder.record(
            "agent_started",
            self.name,
            "Analyzing Google Sheets ledger context.",
            trace_id,
            {"question": question, "symbols": symbols or [], "currencies": currencies or []},
        )
        result = self.tool.summarize_ledger(question)
        event_recorder.record(
            "tool_called",
            self.name,
            f"Called {result.tool_name}.",
            trace_id,
            asdict(result),
        )
        return AgentResult(
            agent_name=self.name,
            task="ledger_financial_interpretation",
            summary=result.summary,
            observations=[result.summary],
            tool_calls=[asdict(result)],
            metadata={
                "tool_status": result.status,
                "ledger_summary": result.data.get("ledger_summary"),
                "portfolio_summary": result.data.get("portfolio_summary"),
                "watchlist_summary": result.data.get("watchlist_summary"),
            },
        )
