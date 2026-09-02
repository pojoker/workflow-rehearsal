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


def _without_first_heading(text: str) -> str:
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


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
    report, report_error = _read_text(report_path)
    summary, summary_error = _read_json(summary_path)
    errors = [error for error in (report_error, summary_error) if error]
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
        "summary": summary or {},
        "errors": errors,
    }


def _render_markdown(run_date: str, domestic: dict[str, Any], overseas: dict[str, Any]) -> str:
    domestic_summary = domestic["summary"]
    overseas_summary = overseas["summary"]
    assembly_status = (
        "complete"
        if domestic["available"]
        and overseas["available"]
        and not domestic["errors"]
        and not overseas["errors"]
        else "partial"
    )
    configured = _count(overseas_summary.get("configured_entity_count"))
    monitored = _count(overseas_summary.get("monitored_entity_count"))
    missing_endpoints = _count(overseas_summary.get("missing_endpoint_count"))
    failure_types = overseas_summary.get("failure_types", {})
    if not isinstance(failure_types, dict):
        failure_types = {}
    failure_total = sum(value for value in failure_types.values() if isinstance(value, int))

    lines = [
        f"# 国内与海外每日情报总览 {run_date}",
        "",
        "> 本报告只汇总两个独立镜像的产物；不修改国内 canonical、海外 calls/*.csv 或正式事件状态。",
        "",
        "## 今日摘要",
        f"- 汇总状态：{assembly_status}",
        (
            "- 国内：监控 "
            f"{domestic_summary['watched_codes']} 个代码；投关表 +{domestic_summary['ir_new']}、"
            f"互动问答 +{domestic_summary['qa_new']}、公告 +{domestic_summary['announcements']}、"
            f"召回队列 +{domestic_summary['queue_added']} / -{domestic_summary['queue_removed']}"
        ),
        (
            "- 海外：披露 "
            f"{_count(overseas_summary.get('disclosure_candidates'))}、主张 "
            f"{_count(overseas_summary.get('claim_candidates'))}、事件 "
            f"{_count(overseas_summary.get('event_candidates'))}、证据 "
            f"{_count(overseas_summary.get('evidence_candidates'))}"
        ),
        (
            "- 海外覆盖："
            f"已配置 {configured}/{monitored} 个实体，缺端点 {missing_endpoints} 个；"
            f"失败/待处理记录 {failure_total} 条"
        ),
        (
            "- 海外晋级：正式账本写入 "
            f"{_count(overseas_summary.get('promoted'))} 条；corroborated 建议 "
            f"{_count(overseas_summary.get('corroboration_suggestions'))} 条，均等待人工确认"
        ),
        "",
        "## 今日需处理",
    ]
    if domestic_summary["gate_review_suggested"]:
        lines.append("- 国内存在新增或队列变化，建议进入判定闸复核。")
    else:
        lines.append("- 国内未发现需要开启判定闸的增量。")
    if missing_endpoints:
        lines.append(f"- 海外有 {missing_endpoints} 个监控实体缺少发现端点，覆盖尚不完整。")
    if _count(overseas_summary.get("endpoint_failed")):
        lines.append(
            f"- 海外有 {_count(overseas_summary.get('endpoint_failed'))} 个端点抓取失败，需查看 failures.csv。"
        )
    if _count(overseas_summary.get("corroboration_suggestions")):
        lines.append(
            f"- 海外有 {_count(overseas_summary.get('corroboration_suggestions'))} 条独立佐证建议待人工批准。"
        )
    for source_name, source in (("国内", domestic), ("海外", overseas)):
        for error in source["errors"]:
            lines.append(f"- {source_name}输入异常：{error}")

    lines.extend(["", "## 国内完整日报", ""])
    if domestic["report"] is None:
        lines.append(f"未生成：`{domestic['report_path']}`")
    else:
        lines.append(_without_first_heading(domestic["report"]))

    lines.extend(["", "## 海外完整日报", ""])
    if overseas["report"] is None:
        lines.append(f"未生成：`{overseas['report_path']}`")
    else:
        lines.append(_without_first_heading(overseas["report"]))

    lines.extend(
        [
            "",
            "## 输入与权限边界",
            f"- 国内日报：`{domestic['report_path']}`",
            f"- 海外日报：`{overseas['report_path']}`",
            "- 本总览只做读取与拼装，不执行 promote，不安装或修改定时任务。",
            "",
        ]
    )
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
        "overseas": {key: value for key, value in overseas.items() if key != "report"},
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
