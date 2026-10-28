from __future__ import annotations

import requests

from investment_agents.core.config import Settings
from investment_agents.storage.market_cache import MarketDataCache, utc_now_iso
from investment_agents.tools.base import ToolReadiness, ToolResult
from investment_agents.tools.provider_errors import (
    provider_payload_error,
    provider_rate_limit,
    provider_request_error,
    rate_limit_message,
)


class AlphaVantageResearchTool:
    """Alpha Vantage adapter for financial news, sentiment, and macro research."""

    name = "alphavantage_research"
    base_url = "https://www.alphavantage.co/query"

    def __init__(self, settings: Settings, cache: MarketDataCache | None = None) -> None:
        self.settings = settings
        self.cache = cache

    def readiness(self) -> ToolReadiness:
        missing = [] if self.settings.alphavantage_api_key else ["ALPHAVANTAGE_API_KEY"]
        return ToolReadiness(
            tool_name=self.name,
            configured=not missing,
            status="ready" if not missing else "needs_configuration",
            missing_settings=missing,
            capabilities=[
                "news_sentiment",
                "research_headlines",
                "macro_context",
                "event_risk",
                "rate_limit_detection",
                "provider_error_degradation",
                "stale_cache_fallback",
            ],
        )

    def research_symbol(self, symbol: str) -> ToolResult:
        requested_symbol = symbol.upper()
        provider_symbol = self._provider_symbol(requested_symbol)
        readiness = self.readiness()
        if not readiness.configured:
            return ToolResult(
                tool_name=self.name,
                status=readiness.status,
                summary=(
                    "Alpha Vantage access is not configured yet. Missing settings: "
                    f"{', '.join(readiness.missing_settings)}."
                ),
                data={
                    "symbol": requested_symbol,
                    "provider_symbol": provider_symbol,
                    "missing_settings": readiness.missing_settings,
                },
            )

        cache_key = provider_symbol.upper()
        cached = None
        if self.cache:
            cached = self.cache.get_fresh_raw_payload(
                source=self.name,
                endpoint="news_sentiment",
                cache_key=cache_key,
                ttl_seconds=self.settings.market_cache_ttl_seconds,
            )

        if cached:
            payload = cached.payload
            cache_status = "hit"
            fetched_at = cached.fetched_at
        else:
            try:
                response = requests.get(
                    self.base_url,
                    params={
                        "function": "NEWS_SENTIMENT",
                        "tickers": provider_symbol,
                        "apikey": self.settings.alphavantage_api_key,
                    },
                    timeout=(3.05, self.settings.provider_request_timeout_seconds),
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                error_result = ToolResult(
                    **provider_request_error(
                        tool_name=self.name,
                        provider_name="Alpha Vantage",
                        symbol=requested_symbol,
                        provider_symbol=provider_symbol,
                        exc=exc,
                    )
                )
                return self._stale_research_result_or_error(
                    error_result,
                    requested_symbol,
                    provider_symbol,
                    cache_key,
                )

            try:
                payload = response.json()
            except ValueError as exc:
                error_result = ToolResult(
                    **provider_payload_error(
                        tool_name=self.name,
                        provider_name="Alpha Vantage",
                        symbol=requested_symbol,
                        provider_symbol=provider_symbol,
                        exc=exc,
                    )
                )
                return self._stale_research_result_or_error(
                    error_result,
                    requested_symbol,
                    provider_symbol,
                    cache_key,
                )
            if not isinstance(payload, dict):
                error_result = ToolResult(
                    **provider_payload_error(
                        tool_name=self.name,
                        provider_name="Alpha Vantage",
                        symbol=requested_symbol,
                        provider_symbol=provider_symbol,
                        exc=ValueError("Expected a JSON object."),
                    )
                )
                return self._stale_research_result_or_error(
                    error_result,
                    requested_symbol,
                    provider_symbol,
                    cache_key,
                )
            limit_message = rate_limit_message(payload)
            if limit_message:
                error_result = ToolResult(
                    **provider_rate_limit(
                        tool_name=self.name,
                        provider_name="Alpha Vantage",
                        symbol=requested_symbol,
                        provider_symbol=provider_symbol,
                        message=limit_message,
                    )
                )
                return self._stale_research_result_or_error(
                    error_result,
                    requested_symbol,
                    provider_symbol,
                    cache_key,
                )
            cache_status = "miss"
            fetched_at = utc_now_iso()
            if self.cache:
                stored = self.cache.store_raw_payload(
                    self.name,
                    "news_sentiment",
                    cache_key,
                    payload,
                    fetched_at=fetched_at,
                )
                fetched_at = stored.fetched_at

        if not isinstance(payload, dict):
            error_result = ToolResult(
                **provider_payload_error(
                    tool_name=self.name,
                    provider_name="Alpha Vantage",
                    symbol=requested_symbol,
                    provider_symbol=provider_symbol,
                    exc=ValueError("Expected a JSON object."),
                )
            )
            return self._stale_research_result_or_error(
                error_result,
                requested_symbol,
                provider_symbol,
                cache_key,
            )
        feed_payload = payload.get("feed", [])
        if not isinstance(feed_payload, list):
            error_result = ToolResult(
                **provider_payload_error(
                    tool_name=self.name,
                    provider_name="Alpha Vantage",
                    symbol=requested_symbol,
                    provider_symbol=provider_symbol,
                    exc=ValueError("Expected feed to be a list."),
                )
            )
            return self._stale_research_result_or_error(
                error_result,
                requested_symbol,
                provider_symbol,
                cache_key,
            )
        feed = feed_payload[:5]
        titles = [
            item.get("title", "Untitled") if isinstance(item, dict) else "Untitled"
            for item in feed
        ]
        citations = _article_citations(feed, fetched_at)
        if self.cache:
            self.cache.store_curated_snapshot(
                self.name,
                "news_sentiment",
                cache_key,
                {
                    "symbol": requested_symbol,
                    "provider_symbol": provider_symbol,
                    "headlines": titles,
                    "fetched_at": fetched_at,
                },
            )
        symbol_text = (
            f"{requested_symbol} ({provider_symbol})"
            if requested_symbol != provider_symbol
            else requested_symbol
        )
        return ToolResult(
            tool_name=self.name,
            summary=f"Alpha Vantage returned {len(feed)} recent research/news items for {symbol_text}.",
            data={
                "symbol": requested_symbol,
                "provider_symbol": provider_symbol,
                "headlines": titles,
                "citations": citations,
                "raw": payload,
                "cache_status": cache_status,
                "fetched_at": fetched_at,
            },
        )

    def research_macro(self, query: str) -> ToolResult:
        readiness = self.readiness()
        if not readiness.configured:
            return ToolResult(
                tool_name=self.name,
                status=readiness.status,
                summary=(
                    "Alpha Vantage access is not configured yet. Missing settings: "
                    f"{', '.join(readiness.missing_settings)}."
                ),
                data={"query": query, "missing_settings": readiness.missing_settings},
            )

        cache_key = "macro"
        cached = (
            self.cache.get_fresh_raw_payload(
                source=self.name,
                endpoint="macro_news",
                cache_key=cache_key,
                ttl_seconds=self.settings.market_cache_ttl_seconds,
            )
            if self.cache
            else None
        )
        if cached:
            payload = cached.payload
            cache_status = "hit"
            fetched_at = cached.fetched_at
        else:
            try:
                response = requests.get(
                    self.base_url,
                    params={
                        "function": "NEWS_SENTIMENT",
                        "topics": (
                            "financial_markets,economy_monetary,"
                            "economy_macro,economy_fiscal"
                        ),
                        "apikey": self.settings.alphavantage_api_key,
                    },
                    timeout=(3.05, self.settings.provider_request_timeout_seconds),
                )
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException as exc:
                return self._stale_macro_result_or_error(
                    ToolResult(
                        **provider_request_error(
                            tool_name=self.name,
                            provider_name="Alpha Vantage",
                            symbol="macro",
                            provider_symbol="macro",
                            exc=exc,
                        )
                    ),
                    query,
                )
            except ValueError as exc:
                return self._stale_macro_result_or_error(
                    ToolResult(
                        **provider_payload_error(
                            tool_name=self.name,
                            provider_name="Alpha Vantage",
                            symbol="macro",
                            provider_symbol="macro",
                            exc=exc,
                        )
                    ),
                    query,
                )

            if not isinstance(payload, dict):
                return self._stale_macro_result_or_error(
                    ToolResult(
                        **provider_payload_error(
                            tool_name=self.name,
                            provider_name="Alpha Vantage",
                            symbol="macro",
                            provider_symbol="macro",
                            exc=ValueError("Expected a JSON object."),
                        )
                    ),
                    query,
                )
            limit_message = rate_limit_message(payload)
            if limit_message:
                return self._stale_macro_result_or_error(
                    ToolResult(
                        **provider_rate_limit(
                            tool_name=self.name,
                            provider_name="Alpha Vantage",
                            symbol="macro",
                            provider_symbol="macro",
                            message=limit_message,
                        )
                    ),
                    query,
                )
            if "Error Message" in payload:
                return self._stale_macro_result_or_error(
                    ToolResult(
                        **provider_payload_error(
                            tool_name=self.name,
                            provider_name="Alpha Vantage",
                            symbol="macro",
                            provider_symbol="macro",
                            exc=ValueError("Provider returned an error message."),
                        )
                    ),
                    query,
                )
            cache_status = "miss"
            fetched_at = utc_now_iso()
            if self.cache:
                stored = self.cache.store_raw_payload(
                    self.name,
                    "macro_news",
                    cache_key,
                    payload,
                    fetched_at=fetched_at,
                )
                fetched_at = stored.fetched_at

        return self._macro_result(payload, query, cache_status, fetched_at)

    def _macro_result(
        self,
        payload: dict,
        query: str,
        cache_status: str,
        fetched_at: str,
        status: str = "ok",
    ) -> ToolResult:
        feed = payload.get("feed", [])
        if not isinstance(feed, list):
            return ToolResult(
                tool_name=self.name,
                status="malformed_response",
                summary="Alpha Vantage returned an unreadable macro-news feed.",
                data={"query": query, "error_type": "ValueError"},
            )
        feed = [item for item in feed if isinstance(item, dict)][:5]
        citations = _article_citations(feed, fetched_at)
        headlines = [item.get("title", "Untitled") for item in feed]
        summary = (
            f"Alpha Vantage returned {len(feed)} macro news items "
            f"(retrieved {fetched_at})."
        )
        if not feed:
            summary = "Alpha Vantage returned no macro news items."
            if status == "ok":
                status = "no_results"
        if self.cache:
            self.cache.store_curated_snapshot(
                self.name,
                "macro_news",
                "macro",
                {"query": query, "headlines": headlines, "fetched_at": fetched_at},
            )
        return ToolResult(
            tool_name=self.name,
            status=status,
            summary=summary,
            data={
                "query": query,
                "headlines": headlines,
                "citations": citations,
                "raw": payload,
                "cache_status": cache_status,
                "fetched_at": fetched_at,
            },
        )

    def _stale_macro_result_or_error(
        self,
        error_result: ToolResult,
        query: str,
    ) -> ToolResult:
        if not self.cache:
            return error_result
        cached = self.cache.get_latest_raw_payload(
            source=self.name,
            endpoint="macro_news",
            cache_key="macro",
        )
        if not cached or not isinstance(cached.payload, dict):
            return error_result
        result = self._macro_result(
            cached.payload,
            query,
            "stale",
            cached.fetched_at,
            status="stale_cache",
        )
        result.data["stale_fetched_at"] = cached.fetched_at
        result.data["degraded_from"] = {
            "status": error_result.status,
            "summary": error_result.summary,
            "data": error_result.data,
        }
        return result

    def _provider_symbol(self, symbol: str) -> str:
        return (self.settings.alphavantage_symbol_aliases or {}).get(symbol, symbol)

    def _stale_research_result_or_error(
        self,
        error_result: ToolResult,
        requested_symbol: str,
        provider_symbol: str,
        cache_key: str,
    ) -> ToolResult:
        if not self.cache:
            return error_result

        cached = self.cache.get_latest_raw_payload(
            source=self.name,
            endpoint="news_sentiment",
            cache_key=cache_key,
        )
        if not cached or not isinstance(cached.payload, dict):
            return error_result

        feed_payload = cached.payload.get("feed", [])
        if not isinstance(feed_payload, list):
            return error_result

        feed = feed_payload[:5]
        titles = [
            item.get("title", "Untitled") if isinstance(item, dict) else "Untitled"
            for item in feed
        ]
        symbol_text = (
            f"{requested_symbol} ({provider_symbol})"
            if requested_symbol != provider_symbol
            else requested_symbol
        )
        return ToolResult(
            tool_name=self.name,
            status="stale_cache",
            summary=(
                f"Alpha Vantage is currently unavailable for {symbol_text}; using "
                f"{len(feed)} stale cached research/news items from {cached.fetched_at}."
            ),
            data={
                "symbol": requested_symbol,
                "provider_symbol": provider_symbol,
                "headlines": titles,
                "citations": _article_citations(feed, cached.fetched_at),
                "raw": cached.payload,
                "cache_status": "stale",
                "fetched_at": cached.fetched_at,
                "stale_fetched_at": cached.fetched_at,
                "degraded_from": {
                    "status": error_result.status,
                    "summary": error_result.summary,
                    "data": error_result.data,
                },
            },
        )


def _article_citations(feed: list, retrieved_at: str) -> list[dict[str, str]]:
    citations = []
    for item in feed:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        title = str(item.get("title", "Untitled"))
        source = str(item.get("source", "Alpha Vantage"))
        published_at = str(item.get("time_published", ""))
        sentiment = str(item.get("overall_sentiment_label", ""))
        claim = title
        if sentiment:
            claim = f"{title} (reported sentiment: {sentiment})"
        sentiment_score = item.get("overall_sentiment_score")
        if sentiment_score is not None:
            claim = f"{claim}, score {sentiment_score}"
        citations.append(
            {
                "title": title,
                "url": str(item["url"]),
                "source": source,
                "claim": claim,
                "published_at": published_at,
                "retrieved_at": retrieved_at,
            }
        )
    return citations
