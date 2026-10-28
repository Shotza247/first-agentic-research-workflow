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


class FinnhubInvestmentTool:
    """Finnhub market-data adapter for quote and investment analyst workflows."""

    name = "finnhub_investment_data"
    base_url = "https://finnhub.io/api/v1"

    def __init__(self, settings: Settings, cache: MarketDataCache | None = None) -> None:
        self.settings = settings
        self.cache = cache

    def readiness(self) -> ToolReadiness:
        missing = [] if self.settings.finnhub_api_key else ["FINNHUB_API_KEY"]
        return ToolReadiness(
            tool_name=self.name,
            configured=not missing,
            status="ready" if not missing else "needs_configuration",
            missing_settings=missing,
            capabilities=[
                "ticker_quote",
                "price_action",
                "market_snapshot",
                "investment_signal_context",
                "provider_error_degradation",
                "stale_cache_fallback",
            ],
        )

    def analyze_symbol(self, symbol: str) -> ToolResult:
        requested_symbol = symbol.upper()
        provider_symbol = self._provider_symbol(requested_symbol)
        readiness = self.readiness()
        if not readiness.configured:
            return ToolResult(
                tool_name=self.name,
                status=readiness.status,
                summary=(
                    "Finnhub access is not configured yet. Missing settings: "
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
                endpoint="quote",
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
                    f"{self.base_url}/quote",
                    params={"symbol": provider_symbol, "token": self.settings.finnhub_api_key},
                    timeout=(3.05, self.settings.provider_request_timeout_seconds),
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                error_result = ToolResult(
                    **provider_request_error(
                        tool_name=self.name,
                        provider_name="Finnhub",
                        symbol=requested_symbol,
                        provider_symbol=provider_symbol,
                        exc=exc,
                    )
                )
                return self._stale_quote_result_or_error(
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
                        provider_name="Finnhub",
                        symbol=requested_symbol,
                        provider_symbol=provider_symbol,
                        exc=exc,
                    )
                )
                return self._stale_quote_result_or_error(
                    error_result,
                    requested_symbol,
                    provider_symbol,
                    cache_key,
                )
            if not isinstance(payload, dict):
                error_result = ToolResult(
                    **provider_payload_error(
                        tool_name=self.name,
                        provider_name="Finnhub",
                        symbol=requested_symbol,
                        provider_symbol=provider_symbol,
                        exc=ValueError("Expected a JSON object."),
                    )
                )
                return self._stale_quote_result_or_error(
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
                        provider_name="Finnhub",
                        symbol=requested_symbol,
                        provider_symbol=provider_symbol,
                        message=limit_message,
                    )
                )
                return self._stale_quote_result_or_error(
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
                    "quote",
                    cache_key,
                    payload,
                    fetched_at=fetched_at,
                )
                fetched_at = stored.fetched_at
                self.cache.store_curated_snapshot(
                    self.name,
                    "quote",
                    cache_key,
                    {
                        "symbol": requested_symbol,
                        "provider_symbol": provider_symbol,
                        "quote": payload,
                        "fetched_at": fetched_at,
                    },
                )

        if not isinstance(payload, dict):
            error_result = ToolResult(
                **provider_payload_error(
                    tool_name=self.name,
                    provider_name="Finnhub",
                    symbol=requested_symbol,
                    provider_symbol=provider_symbol,
                    exc=ValueError("Expected a JSON object."),
                )
            )
            return self._stale_quote_result_or_error(
                error_result,
                requested_symbol,
                provider_symbol,
                cache_key,
            )
        symbol_text = (
            f"{requested_symbol} ({provider_symbol})"
            if requested_symbol != provider_symbol
            else requested_symbol
        )
        quote_labels = {
            "c": "current",
            "o": "open",
            "h": "high",
            "l": "low",
            "dp": "change percent",
        }
        citations = [
            {
                "title": f"Finnhub {symbol_text} quote",
                "url": "https://finnhub.io/docs/api/quote",
                "source": "Finnhub",
                "claim": f"{label} {symbol_text} quote: {payload[key]}",
                "retrieved_at": fetched_at,
            }
            for key, label in quote_labels.items()
            if payload.get(key) is not None
        ]
        return ToolResult(
            tool_name=self.name,
            summary=(
                f"Finnhub quote for {symbol_text}: current={payload.get('c')}, "
                f"open={payload.get('o')}, high={payload.get('h')}, low={payload.get('l')}."
            ),
            data={
                "symbol": requested_symbol,
                "provider_symbol": provider_symbol,
                "quote": payload,
                "cache_status": cache_status,
                "fetched_at": fetched_at,
                "citations": citations,
            },
        )

    def analyze_currency(self, base_currency: str) -> ToolResult:
        base = base_currency.upper()
        readiness = self.readiness()
        if not readiness.configured:
            return ToolResult(
                tool_name=self.name,
                status=readiness.status,
                summary=(
                    "Finnhub access is not configured yet. Missing settings: "
                    f"{', '.join(readiness.missing_settings)}."
                ),
                data={"base_currency": base, "missing_settings": readiness.missing_settings},
            )

        endpoint = "forex_rates"
        cached = (
            self.cache.get_fresh_raw_payload(
                source=self.name,
                endpoint=endpoint,
                cache_key=base,
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
                    f"{self.base_url}/forex/rates",
                    params={"base": base, "token": self.settings.finnhub_api_key},
                    timeout=(3.05, self.settings.provider_request_timeout_seconds),
                )
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException as exc:
                return self._stale_currency_result_or_error(
                    ToolResult(
                        **provider_request_error(
                            tool_name=self.name,
                            provider_name="Finnhub",
                            symbol=base,
                            provider_symbol=base,
                            exc=exc,
                        )
                    ),
                    base,
                )
            except ValueError as exc:
                return self._stale_currency_result_or_error(
                    ToolResult(
                        **provider_payload_error(
                            tool_name=self.name,
                            provider_name="Finnhub",
                            symbol=base,
                            provider_symbol=base,
                            exc=exc,
                        )
                    ),
                    base,
                )

            if not isinstance(payload, dict) or not isinstance(payload.get("quote"), dict):
                return self._stale_currency_result_or_error(
                    ToolResult(
                        **provider_payload_error(
                            tool_name=self.name,
                            provider_name="Finnhub",
                            symbol=base,
                            provider_symbol=base,
                            exc=ValueError("Expected a forex quote object."),
                        )
                    ),
                    base,
                )
            cache_status = "miss"
            fetched_at = utc_now_iso()
            if self.cache:
                stored = self.cache.store_raw_payload(
                    self.name,
                    endpoint,
                    base,
                    payload,
                    fetched_at=fetched_at,
                )
                fetched_at = stored.fetched_at

        quote = payload.get("quote") if isinstance(payload, dict) else None
        if not isinstance(quote, dict):
            return self._stale_currency_result_or_error(
                ToolResult(
                    **provider_payload_error(
                        tool_name=self.name,
                        provider_name="Finnhub",
                        symbol=base,
                        provider_symbol=base,
                        exc=ValueError("Expected a forex quote object."),
                    )
                ),
                base,
            )
        rates = {
            currency: rate
            for currency, rate in quote.items()
            if currency != base and rate is not None
        }
        citations = [
            {
                "title": f"Finnhub {base}/{currency} exchange rate",
                "url": "https://finnhub.io/docs/api/forex-rates",
                "source": "Finnhub",
                "claim": f"1 {base} = {rate} {currency}",
                "retrieved_at": fetched_at,
            }
            for currency, rate in rates.items()
        ]
        summary = (
            f"Finnhub returned {len(rates)} exchange rates for {base} "
            f"(retrieved {fetched_at})."
        )
        return ToolResult(
            tool_name=self.name,
            summary=summary,
            data={
                "base_currency": base,
                "rates": rates,
                "cache_status": cache_status,
                "fetched_at": fetched_at,
                "citations": citations,
            },
        )

    def _provider_symbol(self, symbol: str) -> str:
        return (self.settings.finnhub_symbol_aliases or {}).get(symbol, symbol)

    def _stale_currency_result_or_error(
        self,
        error_result: ToolResult,
        base_currency: str,
    ) -> ToolResult:
        if not self.cache:
            return error_result

        cached = self.cache.get_latest_raw_payload(
            source=self.name,
            endpoint="forex_rates",
            cache_key=base_currency,
        )
        if not cached or not isinstance(cached.payload, dict):
            return error_result
        quote = cached.payload.get("quote")
        if not isinstance(quote, dict):
            return error_result
        rates = {
            currency: rate
            for currency, rate in quote.items()
            if currency != base_currency and rate is not None
        }
        citations = [
            {
                "title": f"Finnhub {base_currency}/{currency} exchange rate",
                "url": "https://finnhub.io/docs/api/forex-rates",
                "source": "Finnhub",
                "claim": f"1 {base_currency} = {rate} {currency}",
                "retrieved_at": cached.fetched_at,
            }
            for currency, rate in rates.items()
        ]
        return ToolResult(
            tool_name=self.name,
            status="stale_cache",
            summary=(
                f"Finnhub is unavailable; using {len(rates)} stale exchange rates for "
                f"{base_currency} from {cached.fetched_at}."
            ),
            data={
                "base_currency": base_currency,
                "rates": rates,
                "cache_status": "stale",
                "fetched_at": cached.fetched_at,
                "stale_fetched_at": cached.fetched_at,
                "citations": citations,
                "degraded_from": {
                    "status": error_result.status,
                    "summary": error_result.summary,
                    "data": error_result.data,
                },
            },
        )

    def _stale_quote_result_or_error(
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
            endpoint="quote",
            cache_key=cache_key,
        )
        if not cached or not isinstance(cached.payload, dict):
            return error_result

        symbol_text = (
            f"{requested_symbol} ({provider_symbol})"
            if requested_symbol != provider_symbol
            else requested_symbol
        )
        quote_labels = {
            "c": "current",
            "o": "open",
            "h": "high",
            "l": "low",
            "dp": "change percent",
        }
        citations = [
            {
                "title": f"Finnhub {symbol_text} quote",
                "url": "https://finnhub.io/docs/api/quote",
                "source": "Finnhub",
                "claim": f"{label} {symbol_text} quote: {cached.payload[key]}",
                "retrieved_at": cached.fetched_at,
            }
            for key, label in quote_labels.items()
            if cached.payload.get(key) is not None
        ]
        return ToolResult(
            tool_name=self.name,
            status="stale_cache",
            summary=(
                f"Finnhub is currently unavailable for {symbol_text}; using stale cached quote "
                f"from {cached.fetched_at}: current={cached.payload.get('c')}, "
                f"open={cached.payload.get('o')}, high={cached.payload.get('h')}, "
                f"low={cached.payload.get('l')}."
            ),
            data={
                "symbol": requested_symbol,
                "provider_symbol": provider_symbol,
                "quote": cached.payload,
                "cache_status": "stale",
                "fetched_at": cached.fetched_at,
                "stale_fetched_at": cached.fetched_at,
                "citations": citations,
                "degraded_from": {
                    "status": error_result.status,
                    "summary": error_result.summary,
                    "data": error_result.data,
                },
            },
        )
