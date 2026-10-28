from __future__ import annotations

import re

from investment_agents.domain.currencies import SUPPORTED_CURRENCIES

SYMBOL_RE = re.compile(r"\b[A-Z]{1,5}\b")
IGNORED_SYMBOLS = {"A", "I", "THE", "AND", "FOR", "P", "L"}


def extract_ticker_symbols(text: str) -> list[str]:
    """Extract uppercase ticker-like symbols without turning normal words into tickers."""
    symbols: list[str] = []
    for match in SYMBOL_RE.findall(text):
        if match in IGNORED_SYMBOLS or match in SUPPORTED_CURRENCIES:
            continue
        if match not in symbols:
            symbols.append(match)
    return symbols
