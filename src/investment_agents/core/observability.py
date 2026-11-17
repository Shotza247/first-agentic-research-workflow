from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Iterable
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceEvent:
    event_type: str
    agent_name: str
    message: str
    trace_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now_iso)


class EventRecorder:
    """Recorder for agent routing/tool events, with optional JSONL persistence."""

    def __init__(
        self,
        max_events: int = 500,
        enabled: bool = True,
        log_path: str | Path | None = None,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        self.max_events = max(1, max_events)
        self.enabled = enabled
        self.log_path = Path(log_path) if log_path else None
        self.max_bytes = max(1, max_bytes)
        self.backup_count = max(0, backup_count)
        self._events: list[TraceEvent] = []
        self._lock = Lock()

    def configure(
        self,
        enabled: bool = True,
        log_path: str | Path | None = None,
        max_events: int | None = None,
        max_bytes: int | None = None,
        backup_count: int | None = None,
    ) -> None:
        with self._lock:
            self.enabled = enabled
            self.log_path = Path(log_path) if log_path else None
            if max_events is not None:
                self.max_events = max(1, max_events)
                self._events = self._events[-self.max_events :]
            if max_bytes is not None:
                self.max_bytes = max(1, max_bytes)
            if backup_count is not None:
                self.backup_count = max(0, backup_count)

    def new_trace_id(self) -> str:
        return str(uuid4())

    def record(
        self,
        event_type: str,
        agent_name: str,
        message: str,
        trace_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            event_type=event_type,
            agent_name=agent_name,
            message=message,
            trace_id=trace_id,
            metadata=metadata or {},
        )
        if not self.enabled:
            return event

        with self._lock:
            self._events.append(event)
            self._events = self._events[-self.max_events :]
            self._append_event(event)
        return event

    def list_events(self, trace_id: str | None = None) -> list[dict[str, Any]]:
        if not self.enabled:
            return []

        with self._lock:
            if self.log_path:
                return self._read_persisted_events(trace_id=trace_id)
            else:
                event_dicts = [asdict(event) for event in self._events]

        if trace_id:
            event_dicts = [event for event in event_dicts if event.get("trace_id") == trace_id]
        return event_dicts[-self.max_events :]

    def status(self) -> dict[str, Any]:
        with self._lock:
            event_count = self._count_persisted_events() if self.log_path else len(self._events)
            return {
                "enabled": self.enabled,
                "persistent": self.log_path is not None,
                "log_path": str(self.log_path) if self.log_path else None,
                "max_events": self.max_events,
                "event_count": event_count,
            }

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            for path in self._persisted_paths():
                if path.exists():
                    path.unlink()

    def _append_event(self, event: TraceEvent) -> None:
        if not self.log_path:
            return

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = (json.dumps(asdict(event), default=str) + "\n").encode("utf-8")
        current_size = self.log_path.stat().st_size if self.log_path.exists() else 0
        if current_size and current_size + len(line) > self.max_bytes:
            self._rotate_logs()
        with self.log_path.open("ab") as handle:
            handle.write(line)

    def _rotated_path(self, index: int) -> Path | None:
        if not self.log_path:
            return None
        return self.log_path.with_name(f"{self.log_path.name}.{index}")

    def _persisted_paths(self) -> list[Path]:
        if not self.log_path:
            return []
        rotated_paths = [
            self.log_path.with_name(f"{self.log_path.name}.{index}")
            for index in range(self.backup_count, 0, -1)
        ]
        return rotated_paths + [self.log_path]

    def _rotate_logs(self) -> None:
        if not self.log_path:
            return
        oldest = self._rotated_path(self.backup_count) if self.backup_count else None
        if oldest and oldest.exists():
            oldest.unlink()
        for index in range(self.backup_count - 1, 0, -1):
            source = self._rotated_path(index)
            destination = self._rotated_path(index + 1)
            if source and destination and source.exists():
                os.replace(source, destination)
        if self.log_path.exists() and self.backup_count > 0:
            destination = self._rotated_path(1)
            if destination:
                os.replace(self.log_path, destination)
        elif self.log_path.exists():
            self.log_path.unlink()

    def _read_persisted_events(self, trace_id: str | None = None) -> list[dict[str, Any]]:
        paths = self._persisted_paths()
        if trace_id:
            events: list[dict[str, Any]] = []
            for path in paths:
                events.extend(
                    event
                    for event in self._read_lines(path)
                    if event.get("trace_id") == trace_id
                )
            return events[-self.max_events :]

        recent_events: deque[dict[str, Any]] = deque(maxlen=self.max_events)
        for path in reversed(paths):
            for event in reversed(self._read_lines(path, limit=self.max_events)):
                recent_events.append(event)
                if len(recent_events) == self.max_events:
                    return list(reversed(recent_events))
        return list(reversed(recent_events))

    def _read_lines(self, path: Path, limit: int | None = None) -> list[dict[str, Any]]:
        if not path.exists():
            return []

        if limit is None:
            with path.open("r", encoding="utf-8") as handle:
                return self._parse_lines(handle)

        raw_lines = self._tail_lines(path, limit)
        return self._parse_lines(line.decode("utf-8", errors="replace") for line in raw_lines)

    def _tail_lines(self, path: Path, limit: int) -> list[bytes]:
        if limit <= 0:
            return []

        block_size = 8192
        chunks: list[bytes] = []
        newline_count = 0
        with path.open("rb") as handle:
            position = handle.seek(0, os.SEEK_END)
            while position > 0 and newline_count <= limit:
                read_size = min(block_size, position)
                position -= read_size
                handle.seek(position)
                chunk = handle.read(read_size)
                chunks.append(chunk)
                newline_count += chunk.count(b"\n")

        lines = b"".join(reversed(chunks)).splitlines()
        return lines[-limit:]

    @staticmethod
    def _parse_lines(lines: Iterable[str]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
        return events

    def _count_persisted_events(self) -> int:
        count = 0
        for path in self._persisted_paths():
            if path.exists():
                with path.open("r", encoding="utf-8") as handle:
                    count += sum(1 for line in handle if line.strip())
        return count


event_recorder = EventRecorder()
