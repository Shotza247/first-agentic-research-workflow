from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def _csv_env(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes"}


def _int_env(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if not value:
        return None
    return value


def _upper_env(name: str, default: str) -> str:
    value = os.getenv(name)
    if not value:
        return default
    return value.upper()


def _decimal_env(name: str, default: str) -> Decimal:
    value = os.getenv(name, default)
    try:
        return Decimal(value)
    except InvalidOperation:
        return Decimal(default)


def _mapping_env(name: str) -> dict[str, str]:
    value = os.getenv(name)
    if not value:
        return {}

    pairs: dict[str, str] = {}
    for item in value.split(","):
        if "=" in item:
            key, mapped_value = item.split("=", 1)
        elif ":" in item:
            key, mapped_value = item.split(":", 1)
        else:
            continue
        key = key.strip().upper()
        mapped_value = mapped_value.strip()
        if key and mapped_value:
            pairs[key] = mapped_value
    return pairs


@dataclass(frozen=True)
class Settings:
    app_name: str = field(
        default_factory=lambda: os.getenv("APP_NAME", "Investment Agentic Analytics")
    )
    environment: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    model_id: str = field(
        default_factory=lambda: os.getenv("HF_MODEL_ID", "HuggingFaceTB/SmolLM2-360M-Instruct")
    )
    llm_provider: str = field(default_factory=lambda: _upper_env("LLM_PROVIDER", "template").lower())
    openai_api_key: str | None = field(default_factory=lambda: _optional_env("OPENAI_API_KEY"))
    openai_model: str | None = field(default_factory=lambda: _optional_env("OPENAI_MODEL"))
    llm_max_output_tokens: int = field(default_factory=lambda: _int_env("LLM_MAX_OUTPUT_TOKENS", "700"))
    agent_api_url: str = field(default_factory=lambda: os.getenv("AGENT_API_URL", "http://localhost:8001"))
    cors_origins: list[str] | None = None
    finnhub_api_key: str | None = field(default_factory=lambda: _optional_env("FINNHUB_API_KEY"))
    alphavantage_api_key: str | None = field(default_factory=lambda: _optional_env("ALPHAVANTAGE_API_KEY"))
    google_ledger_sheet_id: str | None = field(default_factory=lambda: _optional_env("GOOGLE_LEDGER_SHEET_ID"))
    google_ledger_range: str = field(default_factory=lambda: os.getenv("GOOGLE_LEDGER_RANGE", "Ledger!A:Z"))
    google_watchlist_range: str | None = field(default_factory=lambda: _optional_env("GOOGLE_WATCHLIST_RANGE"))
    google_service_account_file: str | None = field(default_factory=lambda: _optional_env("GOOGLE_SERVICE_ACCOUNT_FILE"))
    observability_enabled: bool = field(default_factory=lambda: _bool_env("OBSERVABILITY_ENABLED", True))
    observability_log_path: str | None = field(default_factory=lambda: _optional_env("OBSERVABILITY_LOG_PATH"))
    observability_max_events: int = field(
        default_factory=lambda: _int_env("OBSERVABILITY_MAX_EVENTS", "500")
    )
    observability_max_bytes: int = field(
        default_factory=lambda: max(1, _int_env("OBSERVABILITY_MAX_BYTES", "10485760"))
    )
    observability_backup_count: int = field(
        default_factory=lambda: max(0, _int_env("OBSERVABILITY_BACKUP_COUNT", "5"))
    )
    storage_db_path: str = field(
        default_factory=lambda: os.getenv("STORAGE_DB_PATH", "data/investment_agents.duckdb")
    )
    market_cache_ttl_seconds: int = field(
        default_factory=lambda: _int_env("MARKET_CACHE_TTL_SECONDS", "900")
    )
    provider_request_timeout_seconds: int = field(
        default_factory=lambda: _int_env("PROVIDER_REQUEST_TIMEOUT_SECONDS", "10")
    )
    reporting_currency: str = field(default_factory=lambda: _upper_env("REPORTING_CURRENCY", "USD"))
    static_fx_rates: dict[str, str] | None = None
    max_enrichment_symbols: int = field(
        default_factory=lambda: _int_env("MAX_ENRICHMENT_SYMBOLS", "3")
    )
    concentration_alert_threshold: Decimal = field(
        default_factory=lambda: _decimal_env("CONCENTRATION_ALERT_THRESHOLD", "0.40")
    )
    loss_alert_threshold: Decimal = field(
        default_factory=lambda: _decimal_env("LOSS_ALERT_THRESHOLD", "0.10")
    )
    finnhub_symbol_aliases: dict[str, str] | None = None
    alphavantage_symbol_aliases: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.cors_origins is None:
            object.__setattr__(
                self,
                "cors_origins",
                _csv_env(
                    "CORS_ORIGINS",
                    [
                        "http://localhost:3000",
                        "http://127.0.0.1:3000",
                        "http://localhost:5173",
                        "http://127.0.0.1:5173",
                        "http://localhost:8501",
                        "http://127.0.0.1:8501",
                    ],
                ),
            )
        if self.static_fx_rates is None:
            object.__setattr__(self, "static_fx_rates", _mapping_env("STATIC_FX_RATES"))
        if self.finnhub_symbol_aliases is None:
            object.__setattr__(self, "finnhub_symbol_aliases", _mapping_env("FINNHUB_SYMBOL_ALIASES"))
        if self.alphavantage_symbol_aliases is None:
            object.__setattr__(
                self,
                "alphavantage_symbol_aliases",
                _mapping_env("ALPHAVANTAGE_SYMBOL_ALIASES"),
            )


def load_environment() -> None:
    cwd_dotenv = Path.cwd() / ".env"
    if cwd_dotenv.exists():
        load_dotenv(dotenv_path=cwd_dotenv)

    discovered_dotenv = find_dotenv(usecwd=True)
    if discovered_dotenv:
        load_dotenv(dotenv_path=discovered_dotenv)


def get_settings() -> Settings:
    load_environment()
    return Settings()
