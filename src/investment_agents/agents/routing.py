from __future__ import annotations

from investment_agents.agents.alphavantage_agent import AlphaVantageResearchAgent
from investment_agents.agents.base import AnalysisAgent
from investment_agents.agents.finnhub_agent import FinnhubInvestmentAgent
from investment_agents.agents.ledger_agent import LedgerInterpretationAgent
from investment_agents.agents.web_search_agent import WebSearchAgent
from investment_agents.domain.currencies import extract_currency_codes
from investment_agents.domain.models import AnalysisFocus, RouteDecision
from investment_agents.domain.tickers import extract_ticker_symbols

LEDGER_TERMS = {
    "ledger",
    "portfolio",
    "holding",
    "holdings",
    "watchlist",
    "watch list",
    "monitored",
    "ideas",
    "profit",
    "profits",
    "loss",
    "losses",
    "p/l",
    "pl",
    "allocation",
    "position",
    "positions",
    "exposure",
}
MARKET_TERMS = {
    "ticker", "tickers", "price", "quote", "finnhub", "analyst", "investment",
    "market", "valuation", "currency", "currencies", "forex", "fx", "exchange rate",
}
RESEARCH_TERMS = {
    "news", "sentiment", "research", "macro", "political", "politics", "economic",
    "economics", "alphavantage", "alpha vantage", "event", "events", "trend",
    "trends", "dollar", "financial",
    "usd", "euro", "yen", "pound", "sterling",
}


class AgentRouter:
    """Keyword/symbol router that can later be replaced by an LLM classifier."""

    def __init__(
        self,
        ledger_agent: LedgerInterpretationAgent,
        finnhub_agent: FinnhubInvestmentAgent,
        alphavantage_agent: AlphaVantageResearchAgent,
        web_search_agent: WebSearchAgent,
    ) -> None:
        self.ledger_agent = ledger_agent
        self.finnhub_agent = finnhub_agent
        self.alphavantage_agent = alphavantage_agent
        self.web_search_agent = web_search_agent

    def route(self, question: str) -> tuple[list[AnalysisAgent], RouteDecision]:
        normalized = question.lower()
        symbols = extract_ticker_symbols(question)
        currencies = extract_currency_codes(question)
        focus_areas: list[AnalysisFocus] = []
        reasons: list[str] = []
        selected: list[AnalysisAgent] = []

        if _contains_any(normalized, LEDGER_TERMS):
            focus_areas.append("ledger")
            reasons.append("Question references portfolio ledger, P/L, allocation, or exposure.")
            selected.append(self.ledger_agent)

        if symbols or currencies or _contains_any(normalized, MARKET_TERMS):
            focus_areas.append("market")
            reasons.append("Question references market, ticker, currency, or pricing data.")
            selected.append(self.finnhub_agent)

        if symbols or currencies or _contains_any(normalized, RESEARCH_TERMS):
            focus_areas.append("research")
            reasons.append("Question references news, sentiment, macro, political, or event context.")
            selected.append(self.alphavantage_agent)

        if (
            symbols
            or currencies
            or _contains_any(normalized, MARKET_TERMS)
            or _contains_any(normalized, RESEARCH_TERMS)
        ):
            selected.append(self.web_search_agent)
            reasons.append("Web search adds independently sourced context and references.")

        if not selected:
            focus_areas = ["ledger", "market", "research"]
            reasons.append("No narrow focus detected, so all specialist agents were selected.")
            selected = [
                self.ledger_agent,
                self.finnhub_agent,
                self.alphavantage_agent,
                self.web_search_agent,
            ]

        decision = RouteDecision(
            selected_agents=[agent.name for agent in selected],
            focus_areas=focus_areas,
            symbols=symbols,
            currency_codes=currencies,
            reasons=reasons,
        )
        return selected, decision


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)
