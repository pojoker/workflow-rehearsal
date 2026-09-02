"""Public data contracts for the daily news core."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class Scope(str, Enum):
    DOMESTIC = "domestic"
    OVERSEAS = "overseas"


@dataclass(frozen=True)
class NewsItem:
    item_id: str
    scope: Scope
    source_id: str
    publisher: str
    title: str
    url: str
    published_time: str
    retrieved_time: str
    source_kind: str
    language: str
    content_hash: str
    snippet: str | None = None
    raw_payload_reference: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["scope"] = self.scope.value
        return value


@dataclass(frozen=True)
class SourceFailure:
    source_id: str
    phase: str
    retryable: bool
    error: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunRequest:
    scopes: tuple[Scope, ...]
    as_of_date: str
    config_path: Path
    output_root: Path
    dry_run: bool = False
    fixture_dir: Path | None = None


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    counts_by_scope: dict[str, int]
    counts_by_source: dict[str, int]
    failures: tuple[SourceFailure, ...]
    output_paths: tuple[str, ...]
    started_at: str
    finished_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "counts_by_scope": dict(sorted(self.counts_by_scope.items())),
            "counts_by_source": dict(sorted(self.counts_by_source.items())),
            "failures": [failure.to_dict() for failure in self.failures],
            "output_paths": list(self.output_paths),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass(frozen=True)
class FetchContext:
    as_of_date: str
    retrieved_at: str
    fixture_dir: Path | None
    timeout_seconds: float
    user_agent: str
