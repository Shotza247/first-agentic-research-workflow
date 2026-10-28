from __future__ import annotations

import re

SUPPORTED_CURRENCIES = {
    "AUD",
    "CAD",
    "CHF",
    "CNY",
    "EUR",
    "GBP",
    "HKD",
    "INR",
    "JPY",
    "NZD",
    "SEK",
    "SGD",
    "USD",
    "ZAR",
}

CURRENCY_RE = re.compile(r"\b[A-Z]{3}\b")
CURRENCY_ALIASES = {
    r"\b(?:us|u\.s\.) dollars?\b": "USD",
    r"\bcanadian dollars?\b": "CAD",
    r"\baustralian dollars?\b": "AUD",
    r"\bnew zealand dollars?\b": "NZD",
    r"\beuros?\b": "EUR",
    r"\b(?:british )?pounds?\b": "GBP",
    r"\bsterling\b": "GBP",
    r"\byen\b": "JPY",
    r"\bfrancs?\b": "CHF",
}


def extract_currency_codes(text: str) -> list[str]:
    """Extract supported uppercase ISO currency codes from a question."""
    codes = [code for code in CURRENCY_RE.findall(text) if code in SUPPORTED_CURRENCIES]
    normalized = text.lower()
    specific_dollar = False
    for pattern, code in CURRENCY_ALIASES.items():
        if re.search(pattern, normalized):
            codes.append(code)
            if "dollar" in pattern:
                specific_dollar = True
    if not specific_dollar and re.search(r"\bdollars?\b", normalized):
        codes.append("USD")
    return list(dict.fromkeys(codes))
