from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

AnalysisFocus = Literal["ledger", "market", "research"]


@dataclass(frozen=True)
class RouteDecision:
    """Explains how the orchestrator interpreted and routed a user request."""

    selected_agents: list[str]
    focus_areas: list[AnalysisFocus]
    symbols: list[str] = field(default_factory=list)
    currency_codes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
