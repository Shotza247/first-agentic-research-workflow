from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass
class AgentResult:
    agent_name: str
    task: str
    summary: str
    observations: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AnalysisAgent(Protocol):
    name: str
    description: str

    def analyze(
        self,
        question: str,
        trace_id: str,
        symbols: list[str] | None = None,
        currencies: list[str] | None = None,
    ) -> AgentResult:
        ...
