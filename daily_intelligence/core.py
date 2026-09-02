from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"missing: {path}"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"invalid JSON: {path}: {type(exc).__name__}: {exc}"
    if not isinstance(value, dict):
        return None, f"invalid JSON object: {path}"
    return value, None


def _read_text(path: Path) -> tuple[str | None, str | None]:
    if not path.is_file():
        return None, f"missing: {path}"
    try:
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeError) as exc:
        return None, f"unreadable: {path}: {type(exc).__name__}: {exc}"


def _count(value: Any) -> int:
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def _validate_date(run_date: str) -> None:
    try:
        parsed = date.fromisoformat(run_date)
    except ValueError as exc:
        raise ValueError(f"run_date must be YYYY-MM-DD, got {run_date!r}") from exc
    if parsed.isoformat() != run_date:
        raise ValueError(f"run_date must be YYYY-MM-DD, got {run_date!r}")


def _require_disjoint_output(output_root: Path, *input_roots: Path) -> None:
    for input_root in input_roots:
        if output_root == input_root or output_root.is_relative_to(input_root) or input_root.is_relative_to(output_root):
            raise ValueError(
                "output_root must be disjoint from domestic and overseas state roots: "
                f"output={output_root}, input={input_root}"
            )


def _load_domestic(root: Path, run_date: str) -> dict[str, Any]:
    report_path = root / "daily" / f"{run_date}.txt"
    manifest_path = root / "manifest.json"
    report, report_error = _read_text(report_path)
    manifest, manifest_error = _read_json(manifest_path)
    errors = [error for error in (report_error, manifest_error) if error]

    if manifest is not None and manifest.get("date") != run_date:
        errors.append(
            f"manifest date mismatch: expected {run_date}, got {manifest.get('date')!r}"
        )
        manifest = None

    digest = manifest.get("digest", {}) if manifest else {}
    if not isinstance(digest, dict):
        digest = {}
    summary = {
        "watched_codes": _count(manifest.get("watched_codes")) if manifest else 0,
        "ir_new": _count(digest.get("ir_new")),
        "qa_new": _count(digest.get("qa_new")),
        "announcements": _count(digest.get("ann")),
        "queue_added": _count(digest.get("q_delta_new")),
        "queue_removed": _count(digest.get("q_delta_gone")),
        "restart_hits": _count(manifest.get("restart_hits")) if manifest else 0,
        "outlier_hits": _count(manifest.get("outlier_hits")) if manifest else 0,
        "log_entries": _count(manifest.get("logs")) if manifest else 0,
    }
    summary["gate_review_suggested"] = any(
        summary[key]
        for key in (
            "ir_new",
            "qa_new",
            "announcements",
            "queue_added",
            "restart_hits",
            "outlier_hits",
        )
    )
    return {
        "available": report is not None,
        "report": report,
        "report_path": str(report_path.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "summary": summary,
        "errors": errors,
    }


def _load_overseas(root: Path, run_date: str) -> dict[str, Any]:
    report_path = root / "daily" / f"{run_date}.txt"
    summary_path = root / "staging" / run_date / "run-summary.json"
    candidates_path = root / "staging" / run_date / "candidates.json"
    report, report_error = _read_text(report_path)
    summary, summary_error = _read_json(summary_path)
    candidates, candidates_error = _read_json(candidates_path)
    errors = [error for error in (report_error, summary_error, candidates_error) if error]
    if summary is not None and summary.get("run_date") != run_date:
        errors.append(
            f"run-summary date mismatch: expected {run_date}, got {summary.get('run_date')!r}"
        )
        summary = None
    return {
        "available": report is not None,
        "report": report,
        "report_path": str(report_path.resolve()),
        "summary_path": str(summary_path.resolve()),
        "candidates_path": str(candidates_path.resolve()),
        "summary": summary or {},
        "candidates": candidates or {},
        "errors": errors,
    }


EVENT_CATEGORY_LABELS = {
    "product_stage": "产品阶段",
    "capacity_constraint": "产能与卡点",
    "commercial_adoption": "商业采用",
    "capital_relationship": "资本与关系",
    "policy_access": "政策与准入",
}

LIFECYCLE_STAGE_LABELS = {
    "announced": "已宣布",
    "demonstrated": "完成演示",
    "sampling": "送样",
    "qualifying": "验证中",
    "first_shipment": "首次出货",
    "volume_order": "批量订单",
    "scaled": "规模化",
}


def _overseas_event_line(event: dict[str, Any]) -> str:
    category = EVENT_CATEGORY_LABELS.get(str(event.get("event_category")), "其他事件")
    stage = LIFECYCLE_STAGE_LABELS.get(
        str(event.get("lifecycle_stage")), str(event.get("lifecycle_stage") or "阶段未知")
    )
    suggestion = (
        "建议交叉确认"
        if event.get("suggested_event_status") == "corroborated"
        else "待人工核验"
    )
    return (
        f"- {event.get('primary_subject_id') or '主体未解析'} | {category}·{stage} | "
        f"{event.get('occurred_start') or '时间未知'} | 已声称；{suggestion}"
    )


def _render_markdown(run_date: str, domestic: dict[str, Any], overseas: dict[str, Any]) -> str:
    overseas_summary = overseas["summary"]
    configured = _count(overseas_summary.get("configured_entity_count"))
    monitored = _count(overseas_summary.get("monitored_entity_count"))
    missing_endpoints = _count(overseas_summary.get("missing_endpoint_count"))
    if domestic["report"] is None:
        lines = [f"# 日报 {run_date}", "", f"> 国内日报未生成：`{domestic['report_path']}`"]
    else:
        lines = [domestic["report"].rstrip()]

    if not overseas["available"] or not overseas["summary"] or not overseas["candidates"]:
        lines.extend(
            ["", "## 海外事件增量 未生成", "- 缺少海外日报或候选清单，请检查海外日更任务。"]
        )
    else:
        events = overseas["candidates"].get("event_candidates", [])
        if not isinstance(events, list):
            events = []
        lines.extend(["", f"## 海外事件增量 {len(events)} 条"])
        fetch_mode = (
            overseas_summary.get("fetch_mode")
            or overseas["candidates"].get("fetch_mode")
            or "unknown"
        )
        if fetch_mode == "fixture":
            lines.append("> 海外数据模式：fixture 演练数据，不代表当日真实采集。")
        elif fetch_mode != "http":
            lines.append(f"> 海外数据模式：{fetch_mode}，来源模式未确认。")
        lines.extend(_overseas_event_line(event) for event in events)
        if not events:
            lines.append("- 无事件增量")
        lines.extend(
            [
                "",
                "### 海外采集状态",
                (
                    f"- 披露候选 {_count(overseas_summary.get('disclosure_candidates'))} 份 / "
                    f"原子主张 {_count(overseas_summary.get('claim_candidates'))} 条 / "
                    f"证据 {_count(overseas_summary.get('evidence_candidates'))} 条"
                ),
                f"- 覆盖 {configured}/{monitored} 个监控实体；缺端点 {missing_endpoints} 个；抓取失败 {_count(overseas_summary.get('endpoint_failed'))} 个",
                f"- 交叉确认建议 {_count(overseas_summary.get('corroboration_suggestions'))} 条，等待人工批准",
                "> 海外自动结果均为候选，未写入正式账本。",
            ]
        )
    for error in domestic["errors"]:
        lines.append(f"- 国内输入异常：{error}")
    for error in overseas["errors"]:
        lines.append(f"- 海外输入异常：{error}")
    lines.append("")
    return "\n".join(lines)


def combine_daily_reports(
    *,
    run_date: str,
    domestic_state_root: str | Path,
    overseas_state_root: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    _validate_date(run_date)
    domestic_state_root = Path(domestic_state_root).resolve()
    overseas_state_root = Path(overseas_state_root).resolve()
    output_root = Path(output_root).resolve()
    _require_disjoint_output(output_root, domestic_state_root, overseas_state_root)
    domestic = _load_domestic(domestic_state_root, run_date)
    overseas = _load_overseas(overseas_state_root, run_date)
    markdown_path = output_root / "daily" / f"{run_date}.md"
    json_path = output_root / "daily" / f"{run_date}.json"
    assembly_status = (
        "complete"
        if domestic["available"]
        and overseas["available"]
        and not domestic["errors"]
        and not overseas["errors"]
        else "partial"
    )

    payload = {
        "run_date": run_date,
        "assembly_status": assembly_status,
        "domestic": {key: value for key, value in domestic.items() if key != "report"},
        "overseas": {
            key: value for key, value in overseas.items() if key not in {"report", "candidates"}
        },
    }
    _atomic_write(markdown_path, _render_markdown(run_date, domestic, overseas))
    _atomic_write(
        json_path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return {
        **payload,
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
    }
