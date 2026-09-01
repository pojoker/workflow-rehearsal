#!/usr/bin/env python3
"""Generate diagnostic question candidates and recompute their resolution state."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.research.build_relation_index import (
    ROOT,
    canonical_json,
    load_yaml,
    slot_identity,
    stable_id,
    write_jsonl,
)


DEFAULT_ASSERTION_INDEX = ROOT / "out/relation_assertion_index.jsonl"
DEFAULT_SLOT_STATES = ROOT / "out/relation_slot_states.jsonl"
DEFAULT_RULES = ROOT / "contracts/question_generation_rules.yaml"
DEFAULT_ADAPTERS = ROOT / "contracts/relation_adapters.yaml"
DEFAULT_OUTPUT = ROOT / "out/generated_diagnostic_questions.jsonl"


class QuestionStateError(ValueError):
    """Raised when a generated question cannot satisfy its contract."""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise QuestionStateError(f"{path}:{line_number} must be a JSON object")
            rows.append(value)
    return rows


def question_fingerprint(rule_id: str, subject_ref: str, route_profile_id: str) -> str:
    return canonical_json(
        {
            "rule_id": rule_id,
            "subject_ref": subject_ref,
            "target_relation_type": "company_serves_route",
            "route_profile_id": route_profile_id,
        }
    )


def _qualified_supports(
    assertions: list[dict[str, Any]],
    active_ids: set[str],
    acceptance: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        item
        for item in assertions
        if item["assertion_id"] in active_ids
        and item["relation_type"] == acceptance["relation_type"]
        and item["epistemic_status"] == acceptance["epistemic_status"]
        and item["polarity"] == acceptance["polarity"]
        and item["modality"] == acceptance["modality"]
    ]


def compute_resolution(
    target_assertions: list[dict[str, Any]],
    slot_state: dict[str, Any] | None,
    acceptance: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if slot_state is None:
        return "open", {"qualified_origin_groups": [], "qualified_assertion_ids": []}

    active_ids = set(slot_state.get("active_assertion_ids") or [])
    qualified = _qualified_supports(target_assertions, active_ids, acceptance)
    origin_groups = sorted({item["origin_group"] for item in qualified})
    minimum = int(acceptance.get("minimum_independent_origin_groups", 1))
    basis = {
        "qualified_origin_groups": origin_groups,
        "qualified_assertion_ids": sorted(item["assertion_id"] for item in qualified),
        "independent_support_count": len(origin_groups),
        "target_slot_effective_status": slot_state.get("effective_status"),
        "conflict_pairs": slot_state.get("conflict_pairs") or [],
        "withdrawn_assertion_ids": slot_state.get("withdrawn_assertion_ids") or [],
    }
    if slot_state.get("effective_status") == "conflicted":
        return "conflicted", basis
    if qualified and slot_state.get("limiting_assertion_ids"):
        return "partial", basis
    if len(origin_groups) >= minimum:
        return "satisfied", basis

    by_id = {item["assertion_id"]: item for item in target_assertions}
    withdrawn_qualified = [
        by_id[item_id]
        for item_id in slot_state.get("withdrawn_assertion_ids") or []
        if item_id in by_id
        and by_id[item_id]["epistemic_status"] == acceptance["epistemic_status"]
        and by_id[item_id]["polarity"] == acceptance["polarity"]
        and by_id[item_id]["modality"] == acceptance["modality"]
    ]
    if withdrawn_qualified:
        basis["withdrawn_qualified_assertion_ids"] = sorted(
            item["assertion_id"] for item in withdrawn_qualified
        )
        return "reopened", basis
    if slot_state.get("limiting_assertion_ids"):
        return "partial", basis
    if slot_state.get("contradicting_assertion_ids"):
        return "blocked", basis
    return "open", basis


def generate_diagnostic_questions(
    assertions: list[dict[str, Any]],
    slot_states: list[dict[str, Any]],
    rules_contract: dict[str, Any],
    adapters_contract: dict[str, Any],
) -> list[dict[str, Any]]:
    profiles = {
        item["route_profile_id"]: item
        for item in adapters_contract.get("route_profiles") or []
    }
    states_by_id = {item["slot_id"]: item for item in slot_states}
    assertions_by_slot: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in assertions:
        assertions_by_slot[item["slot_id"]].append(item)

    matches: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in assertions:
        if (
            item["relation_type"] == "capability_matches_route"
            and item["epistemic_status"] == "derived_candidate"
            and item["polarity"] == "supporting"
        ):
            profile_id = item["scope"].get("route_profile_id")
            if profile_id:
                matches[(item["subject_ref"], profile_id)].append(item)

    questions: dict[str, dict[str, Any]] = {}
    for rule in rules_contract.get("rules") or []:
        if rule.get("trigger_relation_type") != "capability_matches_route":
            continue
        for (subject_ref, profile_id), trigger_items in sorted(matches.items()):
            if profile_id not in set(rule.get("route_profile_ids") or []):
                continue
            profile = profiles.get(profile_id)
            if profile is None:
                raise QuestionStateError(f"rule targets unknown route profile: {profile_id}")
            target_identity = slot_identity(
                rule["target_relation_type"],
                subject_ref,
                f"route_profile:{profile_id}",
                {"route_profile_id": profile_id},
            )
            target_slot_id = stable_id("RS", target_identity)
            target_assertions = assertions_by_slot.get(target_slot_id, [])
            resolution_status, basis = compute_resolution(
                target_assertions,
                states_by_id.get(target_slot_id),
                rule["acceptance"],
            )
            fingerprint = question_fingerprint(rule["rule_id"], subject_ref, profile_id)
            question_id = stable_id("GQ", fingerprint, length=12)
            company = subject_ref.split(":", 1)[-1]
            question = {
                "question_id": question_id,
                "question_class": rule["question_class"],
                "question_text": rule["question_template"].format(
                    company=company, route_label=profile["label"]
                ),
                "display_parent": rule["display_parent"],
                "depends_on": list(rule.get("depends_on") or []),
                "generated_by": {
                    "rule_id": rule["rule_id"],
                    "reason": rule["generated_by_reason"],
                },
                "trigger_refs": sorted(item["assertion_id"] for item in trigger_items),
                "target": {"slot_id": target_slot_id, **target_identity},
                "acceptance": rule["acceptance"],
                "reopen_on": list(rule.get("reopen_on") or []),
                "workflow_status": rule["initial_workflow_status"],
                "resolution_status": resolution_status,
                "dedupe_fingerprint": fingerprint,
                "state_basis": basis,
            }
            if fingerprint in questions and questions[fingerprint] != question:
                raise QuestionStateError(f"non-deterministic duplicate question: {fingerprint}")
            questions[fingerprint] = question

    result = sorted(questions.values(), key=lambda item: item["question_id"])
    allowed_workflow = set(rules_contract.get("workflow_status_enum") or [])
    allowed_resolution = set(rules_contract.get("resolution_status_enum") or [])
    for item in result:
        if item["workflow_status"] not in allowed_workflow:
            raise QuestionStateError(f"invalid workflow status: {item['workflow_status']}")
        if item["resolution_status"] not in allowed_resolution:
            raise QuestionStateError(f"invalid resolution status: {item['resolution_status']}")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assertion-index", type=Path, default=DEFAULT_ASSERTION_INDEX)
    parser.add_argument("--slot-states", type=Path, default=DEFAULT_SLOT_STATES)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--adapters", type=Path, default=DEFAULT_ADAPTERS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    questions = generate_diagnostic_questions(
        read_jsonl(args.assertion_index),
        read_jsonl(args.slot_states),
        load_yaml(args.rules),
        load_yaml(args.adapters),
    )
    write_jsonl(args.output, questions)
    counts: dict[str, int] = defaultdict(int)
    for item in questions:
        counts[item["resolution_status"]] += 1
    print(f"diagnostic questions: {len(questions)} -> {args.output} ({dict(sorted(counts.items()))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
