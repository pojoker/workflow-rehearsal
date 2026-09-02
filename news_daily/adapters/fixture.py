"""Deterministic offline adapter used by tests and the initial CLI."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterable

from ..models import FetchContext, NewsItem, Scope


class FixtureAdapterError(Exception):
    """A concise, source-local fixture failure."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _content_hash(record: dict[str, Any]) -> str:
    supplied = record.get("content_hash")
    if supplied:
        return str(supplied)
    content = record.get("content")
    if content is None:
        content = {
            "title": record.get("title", ""),
            "snippet": record.get("snippet", ""),
            "content": record.get("content", ""),
        }
    return hashlib.sha256(_canonical_json(content).encode("utf-8")).hexdigest()


def _timestamp(value: Any, fallback: str) -> str:
    if value is None or value == "":
        return fallback
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).replace(" ", "T", 1) if " " in str(value) else str(value)


class FixtureAdapter:
    """Read one JSON or JSONL source file without network or side effects."""

    def __init__(
        self,
        *,
        source_id: str,
        scope: Scope,
        fixture_dir: Path | None,
        file_name: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.source_id = source_id
        self.scope = scope
        self.fixture_dir = fixture_dir
        self.file_name = file_name
        self.options = options or {}

    def _path(self) -> Path:
        if self.fixture_dir is None:
            raise FixtureAdapterError("fixture directory was not provided")
        name = self.file_name or f"{self.scope.value}.jsonl"
        path = (self.fixture_dir / name).resolve()
        try:
            path.relative_to(self.fixture_dir.resolve())
        except ValueError as exc:
            raise FixtureAdapterError("fixture file escapes fixture directory") from exc
        return path

    def _read_records(self) -> list[dict[str, Any]]:
        path = self._path()
        if not path.is_file():
            raise FixtureAdapterError(f"fixture file not found: {path.name}")
        try:
            if path.suffix.lower() == ".jsonl":
                records = [
                    json.loads(line)
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            else:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    records = payload
                elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
                    if payload.get("error"):
                        raise FixtureAdapterError(str(payload["error"]))
                    records = payload["items"]
                elif isinstance(payload, dict) and payload.get("error"):
                    raise FixtureAdapterError(str(payload["error"]))
                else:
                    records = [payload]
        except FixtureAdapterError:
            raise
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise FixtureAdapterError(f"cannot read fixture: {exc}") from exc
        if not all(isinstance(record, dict) for record in records):
            raise FixtureAdapterError("fixture records must be JSON objects")
        return records

    def fetch(self, context: FetchContext) -> Iterable[NewsItem]:
        if self.options.get("fail"):
            raise FixtureAdapterError(str(self.options.get("error") or "configured fixture failure"))
        delay = float(self.options.get("delay_seconds", 0) or 0)
        if delay > 0:
            time.sleep(delay)
        records = self._read_records()
        for index, record in enumerate(records):
            if record.get("error"):
                raise FixtureAdapterError(str(record["error"]))
            title = str(record.get("title", "")).strip()
            url = str(record.get("url", "")).strip()
            if not title or not url:
                raise FixtureAdapterError(f"record {index + 1} requires title and url")
            source_id = str(record.get("source_id") or self.source_id)
            published = _timestamp(
                record.get("published_time", record.get("published_at", record.get("published"))),
                f"{context.as_of_date}T00:00:00Z",
            )
            yield NewsItem(
                item_id="",
                scope=self.scope,
                source_id=source_id,
                publisher=str(record.get("publisher") or source_id),
                title=title,
                url=url,
                published_time=published,
                retrieved_time=_timestamp(record.get("retrieved_time"), context.retrieved_at),
                source_kind=str(record.get("source_kind") or "fixture"),
                language=str(record.get("language") or ("zh" if self.scope is Scope.DOMESTIC else "en")),
                content_hash=_content_hash(record),
                snippet=(str(record["snippet"]) if record.get("snippet") is not None else None),
            )
