"""Orchestration for fetching, normalizing, deduplicating, and publishing."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from .adapters.base import SourceAdapter
from .config import ConfigurationError, adapters_for, load_config
from .models import FetchContext, NewsItem, RunRequest, RunResult, Scope, SourceFailure
from .storage import (
    IsolationError,
    RunLock,
    cleanup_stage,
    make_stage,
    new_run_id,
    publish,
    read_latest,
    resolve_output_root,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigurationError("date must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ConfigurationError("date must be YYYY-MM-DD")
    return value


def _normalized_url(url: str) -> str:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    split = urlsplit(url.strip())
    scheme = split.scheme.lower()
    netloc = split.netloc.lower()
    path = split.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(sorted(parse_qsl(split.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))


def _item_id(item: NewsItem) -> str:
    identity = "\x1f".join(
        [
            item.source_id,
            _normalized_url(item.url),
            item.published_time,
            item.content_hash,
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _candidate_key(item: NewsItem) -> tuple[str, str, str, str]:
    return (item.source_id, _normalized_url(item.url), item.published_time, item.content_hash)


def _with_identity(item: NewsItem, raw_reference: str) -> NewsItem:
    return NewsItem(
        item_id=_item_id(item),
        scope=item.scope,
        source_id=item.source_id,
        publisher=item.publisher,
        title=item.title,
        url=item.url,
        published_time=item.published_time,
        retrieved_time=item.retrieved_time,
        source_kind=item.source_kind,
        language=item.language,
        content_hash=item.content_hash,
        snippet=item.snippet,
        raw_payload_reference=raw_reference,
    )


def _json_line(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _write_outputs(
    stage: Path,
    *,
    date_value: str,
    scope: Scope,
    run_id: str,
    candidates: list[NewsItem],
    raw_items: list[NewsItem],
    failures: list[SourceFailure],
    source_counts: dict[str, int],
    source_total: dict[str, int],
    successful_source_count: int,
    started_at: str,
    finished_at: str,
) -> None:
    raw_dir = stage / "raw"
    raw_dir.mkdir()
    raw_path = raw_dir / "envelopes.jsonl"
    raw_lines = []
    for index, item in enumerate(raw_items, start=1):
        raw_lines.append(_json_line({"envelope_index": index, "source_id": item.source_id, "item": item.to_dict()}))
    raw_path.write_text("\n".join(raw_lines) + ("\n" if raw_lines else ""), encoding="utf-8")

    candidate_path = stage / "candidates.jsonl"
    candidate_lines = []
    for item in candidates:
        value = item.to_dict()
        value["record_type"] = "candidate"
        candidate_lines.append(_json_line(value))
    candidate_path.write_text("\n".join(candidate_lines) + ("\n" if candidate_lines else ""), encoding="utf-8")

    report_lines = [
        "Daily news candidate report",
        f"date: {date_value}",
        f"scope: {scope.value}",
        f"candidates: {len(candidates)}",
        f"sources: {len(source_total)}",
    ]
    for item in candidates:
        report_lines.append(f"- [{item.source_id}] {item.title} ({item.url})")
    for failure in sorted(failures, key=lambda value: (value.source_id, value.phase, value.error)):
        report_lines.append(f"! {failure.source_id} [{failure.phase}]: {failure.error}")
    (stage / "report.txt").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    status = "success" if not failures else ("partial" if successful_source_count else "failed")
    manifest = {
        "schema_version": "news_daily_v1",
        "run_id": run_id,
        "status": status,
        "date": date_value,
        "scope": scope.value,
        "candidate_count": len(candidates),
        "raw_envelope_count": len(raw_items),
        "counts_by_scope": {scope.value: len(candidates)},
        "counts_by_source": dict(sorted(source_counts.items())),
        "source_totals": dict(sorted(source_total.items())),
        "failures": [failure.to_dict() for failure in sorted(failures, key=lambda value: value.source_id)],
        "started_at": started_at,
        "finished_at": finished_at,
        "semantic_state": "candidate_only",
    }
    (stage / "manifest.json").write_text(_json_line(manifest) + "\n", encoding="utf-8")


def _fetch_scope(
    adapters: Iterable[SourceAdapter], context: FetchContext, scope: Scope
) -> tuple[list[NewsItem], list[NewsItem], list[SourceFailure], dict[str, int], dict[str, int], int]:
    raw_items: list[NewsItem] = []
    failures: list[SourceFailure] = []
    source_counts: dict[str, int] = {}
    source_total: dict[str, int] = {}
    successful_source_count = 0
    for adapter in adapters:
        try:
            fetched = list(adapter.fetch(context))
            normalized: list[NewsItem] = []
            for item in fetched:
                if item.scope is not scope:
                    raise ValueError(f"item scope {item.scope.value} does not match adapter scope")
                normalized.append(item)
            source_total[adapter.source_id] = len(normalized)
            successful_source_count += 1
            raw_items.extend(normalized)
        except Exception as exc:  # Source failures are deliberately isolated.
            failures.append(SourceFailure(adapter.source_id, "fetch", True, str(exc)[:240]))
            source_total[adapter.source_id] = 0

    deduplicated: dict[tuple[str, str, str, str], NewsItem] = {}
    for index, item in enumerate(raw_items, start=1):
        candidate = _with_identity(item, f"raw/envelopes.jsonl#{index}")
        key = _candidate_key(candidate)
        if key not in deduplicated:
            deduplicated[key] = candidate
    candidates = sorted(deduplicated.values(), key=lambda item: (item.source_id, _normalized_url(item.url), item.published_time, item.content_hash))
    for item in candidates:
        source_counts[item.source_id] = source_counts.get(item.source_id, 0) + 1
    return candidates, raw_items, failures, source_counts, source_total, successful_source_count


def run(request: RunRequest) -> RunResult:
    date_value = _validate_date(request.as_of_date)
    root = resolve_output_root(request.output_root)
    config = load_config(request.config_path)
    adapters = adapters_for(config, request.scopes, request.fixture_dir)
    started_at = _now()
    run_id = new_run_id(date_value, tuple(scope.value for scope in request.scopes))
    if request.dry_run:
        counts_scope: dict[str, int] = {}
        counts_source: dict[str, int] = {}
        failures: list[SourceFailure] = []
        context = FetchContext(date_value, f"{date_value}T23:59:59Z", request.fixture_dir, config.timeout_seconds, config.user_agent)
        for scope in request.scopes:
            scope_candidates, _, scope_failures, source_counts, _, _ = _fetch_scope(
                (adapter for adapter in adapters if adapter.scope is scope), context, scope
            )
            counts_scope[scope.value] = len(scope_candidates)
            for source_id, count in source_counts.items():
                counts_source[source_id] = count
            failures.extend(scope_failures)
        finished_at = _now()
        status = "dry_run"
        return RunResult(run_id, status, counts_scope, counts_source, tuple(failures), (), started_at, finished_at)

    scopes = tuple(scope.value for scope in request.scopes)
    with RunLock(root, date_value, scopes):
        context = FetchContext(date_value, f"{date_value}T23:59:59Z", request.fixture_dir, config.timeout_seconds, config.user_agent)
        results: list[tuple[Scope, list[NewsItem], list[NewsItem], list[SourceFailure], dict[str, int], dict[str, int], int, Path]] = []
        try:
            for scope in request.scopes:
                scope_adapters = tuple(adapter for adapter in adapters if adapter.scope is scope)
                candidates, raw_items, failures, source_counts, source_total, successful_source_count = _fetch_scope(
                    scope_adapters, context, scope
                )
                stage = make_stage(root, date_value, scope.value, run_id)
                results.append((scope, candidates, raw_items, failures, source_counts, source_total, successful_source_count, stage))
                _write_outputs(
                    stage,
                    date_value=date_value,
                    scope=scope,
                    run_id=run_id,
                    candidates=candidates,
                    raw_items=raw_items,
                    failures=failures,
                    source_counts=source_counts,
                    source_total=source_total,
                    successful_source_count=successful_source_count,
                    started_at=started_at,
                    finished_at=_now(),
                )
            output_paths: list[str] = []
            for scope, _, _, _, _, _, _, stage in results:
                destination = publish(stage, root, date_value, scope.value, run_id)
                output_paths.append(str(destination))
                output_paths.append(str(destination / "manifest.json"))
            counts_scope = {scope.value: len(candidates) for scope, candidates, *_ in results}
            counts_source: dict[str, int] = {}
            failures = []
            for _, _, _, scope_failures, source_counts, _, _, _ in results:
                failures.extend(scope_failures)
                for source_id, count in source_counts.items():
                    counts_source[source_id] = count
            finished_at = _now()
            successful_sources = sum(result[6] for result in results)
            status = "success" if not failures else ("partial" if successful_sources else "failed")
            return RunResult(run_id, status, counts_scope, counts_source, tuple(failures), tuple(output_paths), started_at, finished_at)
        except Exception:
            for *_, stage in results:
                cleanup_stage(stage)
            raise


def status(root_value: str | Path, date_value: str) -> dict[str, object]:
    date_value = _validate_date(date_value)
    root = resolve_output_root(root_value)
    runs = []
    for scope in (Scope.DOMESTIC.value, Scope.OVERSEAS.value):
        latest = read_latest(root, date_value, scope)
        if latest is None:
            continue
        manifest_path, manifest = latest
        runs.append({"scope": scope, "run_id": manifest.get("run_id"), "status": manifest.get("status"), "manifest": str(manifest_path)})
    if not runs:
        overall = "missing"
    elif any(run.get("status") in {"partial", "failed"} for run in runs):
        overall = "partial"
    else:
        overall = "present"
    return {"date": date_value, "status": overall, "runs": runs}


__all__ = ["run", "status", "IsolationError", "ConfigurationError"]
