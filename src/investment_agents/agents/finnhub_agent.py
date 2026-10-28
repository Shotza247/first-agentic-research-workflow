from __future__ import annotations

from dataclasses import asdict

from investment_agents.agents.base import AgentResult
from investment_agents.core.config import Settings, get_settings
from investment_agents.core.observability import event_recorder
from investment_agents.domain.tickers import extract_ticker_symbols
from investment_agents.tools.finnhub import FinnhubInvestmentTool


class FinnhubInvestmentAgent:
    name = "finnhub_investment_agent"
    description = "Analyzes ticker-level market data, price action, and investment signals."

    def __init__(self, tool: FinnhubInvestmentTool, settings: Settings | None = None) -> None:
        self.tool = tool
        self.settings = settings or get_settings()

    def _symbols_for_analysis(
        self,
        question: str,
        symbols: list[str] | None = None,
    ) -> list[str]:
        explicit_symbols = extract_ticker_symbols(question)
        selected = explicit_symbols or symbols or []
        unique_symbols = list(dict.fromkeys(symbol.upper() for symbol in selected if symbol))
        return unique_symbols[: self.settings.max_enrichment_symbols]

    def analyze(
        self,
        question: str,
        trace_id: str,
        symbols: list[str] | None = None,
        currencies: list[str] | None = None,
    ) -> AgentResult:
        selected_symbols = self._symbols_for_analysis(question, symbols)
        selected_currencies = list(dict.fromkeys((currencies or [])))[: self.settings.max_enrichment_symbols]
        if not selected_symbols and not selected_currencies:
            event_recorder.record(
                "agent_skipped",
                self.name,
                "No ticker symbols were available for Finnhub analysis.",
                trace_id,
                {"question": question},
            )
            summary = "Finnhub analysis needs at least one ticker symbol."
            return AgentResult(
                agent_name=self.name,
                task="finnhub_investment_analysis",
                summary=summary,
                observations=[summary],
                metadata={"symbols": [], "tool_status": "needs_symbol"},
            )

        event_recorder.record(
            "agent_started",
            self.name,
            (
                f"Analyzing Finnhub market data for {', '.join(selected_symbols)}."
                if selected_symbols
                else f"Analyzing Finnhub exchange rates for {', '.join(selected_currencies)}."
            ),
            trace_id,
            {
                "symbols": selected_symbols,
                "currencies": selected_currencies,
                "question": question,
            },
        )

        results = []
        for symbol in selected_symbols:
            result = self.tool.analyze_symbol(symbol)
            results.append(result)
            event_recorder.record(
                "tool_called",
                self.name,
                f"Called {result.tool_name} for {symbol}.",
                trace_id,
                asdict(result),
            )

        for currency in selected_currencies:
            result = self.tool.analyze_currency(currency)
            results.append(result)
            event_recorder.record(
                "tool_called",
                self.name,
                f"Called {result.tool_name} for {currency} currency rates.",
                trace_id,
                asdict(result),
            )

        observations = [result.summary for result in results]
        summary = " ".join(observations)
        statuses = [result.status for result in results]
        return AgentResult(
            agent_name=self.name,
            task="finnhub_investment_analysis",
            summary=summary,
            observations=observations,
            tool_calls=[asdict(result) for result in results],
            metadata={
                "symbols": selected_symbols,
                "currencies": selected_currencies,
                "tool_status": statuses[0] if len(set(statuses)) == 1 else "mixed",
                "tool_statuses": statuses,
            },
        )
