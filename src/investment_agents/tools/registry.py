from __future__ import annotations

from dataclasses import asdict, dataclass

from investment_agents.core.config import Settings, get_settings
from investment_agents.tools.alphavantage import AlphaVantageResearchTool
from investment_agents.tools.base import ToolReadiness
from investment_agents.tools.finnhub import FinnhubInvestmentTool
from investment_agents.tools.google_sheets_ledger import GoogleSheetsLedgerTool
from investment_agents.tools.web_search import WebSearchTool
from investment_agents.storage.market_cache import MarketDataCache


@dataclass
class ToolRegistry:
    """Central wiring point for external resources used by specialist agents."""

    ledger: GoogleSheetsLedgerTool
    finnhub: FinnhubInvestmentTool
    alphavantage: AlphaVantageResearchTool
    web_search: WebSearchTool
    cache: MarketDataCache
    settings: Settings

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ToolRegistry":
        settings = settings or get_settings()
        cache = MarketDataCache(settings.storage_db_path)
        _seed_static_fx_rates(cache, settings)
        return cls(
            ledger=GoogleSheetsLedgerTool(settings, cache=cache),
            finnhub=FinnhubInvestmentTool(settings, cache=cache),
            alphavantage=AlphaVantageResearchTool(settings, cache=cache),
            web_search=WebSearchTool(
                timeout_seconds=settings.provider_request_timeout_seconds,
            ),
            cache=cache,
            settings=settings,
        )

    def readiness(self) -> list[ToolReadiness]:
        return [
            self.ledger.readiness(),
            self.finnhub.readiness(),
            self.alphavantage.readiness(),
            self.web_search.readiness(),
        ]

    def readiness_dicts(self) -> list[dict]:
        return [asdict(item) for item in self.readiness()]

    def storage_status(self) -> dict:
        return self.cache.status()


def _seed_static_fx_rates(cache: MarketDataCache, settings: Settings) -> None:
    if not settings.static_fx_rates:
        return

    reporting_currency = settings.reporting_currency.upper()
    for base_currency, rate in settings.static_fx_rates.items():
        cache.store_fx_rate(
            base_currency=base_currency,
            quote_currency=reporting_currency,
            rate=rate,
            source="settings",
        )
