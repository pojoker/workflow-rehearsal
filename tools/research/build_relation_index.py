#!/usr/bin/env python3
"""Build a deterministic, read-only relation assertion and slot-state index.

The JSONL outputs are disposable projections. Existing CSV/YAML ledgers remain
the sources of truth.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACTS = ROOT / "contracts"
DEFAULT_ASSERTIONS = ROOT / "relation_assertions.yaml"
DEFAULT_OUTPUT = ROOT / "out"


class RelationIndexError(ValueError):
    """Raised when an input violates the relation contracts."""


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RelationIndexError(f"{path}: top level must be a mapping")
    return value


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(prefix: str, value: Any, length: int = 16) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}-{digest.upper()}"


def normalized_time(value: Any | None) -> dict[str, str | None]:
    value = value or {}
    if not isinstance(value, dict):
        raise RelationIndexError("valid_time must be a mapping")
    def normalize_boundary(boundary: Any) -> str | None:
        if boundary in (None, ""):
            return None
        if hasattr(boundary, "isoformat"):
            return boundary.isoformat()
        return str(boundary)

    return {
        "start": normalize_boundary(value.get("start")),
        "end": normalize_boundary(value.get("end")),
    }


def slot_identity(
    relation_type: str,
    subject_ref: str,
    object_ref: str,
    scope: dict[str, Any],
) -> dict[str, Any]:
    return {
        "relation_type": relation_type,
        "subject_ref": subject_ref,
        "object_ref": object_ref,
        "scope": scope,
    }


def make_assertion(
    *,
    relation_type: str,
    subject_ref: str,
    object_ref: str,
    scope: dict[str, Any],
    valid_time: dict[str, Any] | None,
    modality: str,
    polarity: str,
    epistemic_status: str,
    origin_group: str,
    adapter_version: str,
    source_refs: Iterable[str],
    assertion_key: Any,
    assertion_id: str | None = None,
    withdraws_assertion_ids: Iterable[str] = (),
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity = slot_identity(relation_type, subject_ref, object_ref, scope)
    result = {
        "assertion_id": assertion_id or stable_id("RA", assertion_key),
        "slot_id": stable_id("RS", identity),
        **identity,
        "valid_time": normalized_time(valid_time),
        "modality": modality,
        "polarity": polarity,
        "epistemic_status": epistemic_status,
        "origin_group": origin_group,
        "adapter_version": adapter_version,
        "source_refs": sorted(set(source_refs)),
    }
    withdrawn = sorted(set(withdraws_assertion_ids))
    if withdrawn:
        result["withdraws_assertion_ids"] = withdrawn
    if metadata:
        result["metadata"] = metadata
    return result


def _adapter(config: dict[str, Any], name: str) -> dict[str, Any]:
    adapters = config.get("adapters") or {}
    value = adapters.get(name)
    if not isinstance(value, dict) or not value.get("adapter_version"):
        raise RelationIndexError(f"missing adapter contract: {name}")
    return value


def adapt_points(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    adapter = _adapter(config, "points_company_capability")
    result = []
    for row in load_csv(root / adapter["input"]):
        point_id = row.get("point_id", "").strip()
        company = row.get("公司", "").strip()
        cell_id = row.get("cell_id", "").strip()
        if not point_id or not company or not cell_id:
            raise RelationIndexError(f"points.csv has incomplete identity: {row}")
        source = row.get("锚点URL", "").strip() or f"point:{point_id}"
        result.append(
            make_assertion(
                relation_type="company_has_capability_at",
                subject_ref=f"company:{company}",
                object_ref=f"capability_cell:{cell_id}",
                scope={"capability_cell_id": cell_id},
                valid_time={"start": row.get("判定会话日期") or row.get("检索日期")},
                modality="actual",
                polarity="supporting",
                epistemic_status="source_encoded",
                origin_group=f"points_source:{source}",
                adapter_version=adapter["adapter_version"],
                source_refs=[f"points.csv#{point_id}"],
                assertion_key=[adapter["adapter_version"], point_id],
                metadata={"point_status": row.get("状态") or None},
            )
        )
    return result


def adapt_route_requirements(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    adapter = _adapter(config, "route_bom_profile_requirements")
    rows = {row["route_item_id"]: row for row in load_csv(root / adapter["input"])}
    result = []
    profile_ids: set[str] = set()
    for profile in config.get("route_profiles") or []:
        profile_id = profile.get("route_profile_id")
        if not profile_id or profile_id in profile_ids:
            raise RelationIndexError(f"route_profile_id must be unique: {profile_id!r}")
        profile_ids.add(profile_id)
        for route_item_id in profile.get("capability_route_item_ids") or []:
            if route_item_id not in rows:
                raise RelationIndexError(f"{profile_id}: unknown route item {route_item_id}")
            row = rows[route_item_id]
            for cell_id in filter(None, (item.strip() for item in row.get("cell_ids", "").split(","))):
                result.append(
                    make_assertion(
                        relation_type="route_requires_capability",
                        subject_ref=f"route_profile:{profile_id}",
                        object_ref=f"capability_cell:{cell_id}",
                        scope={
                            "route_profile_id": profile_id,
                            "capability_cell_id": cell_id,
                        },
                        valid_time=None,
                        modality="actual",
                        polarity="supporting",
                        epistemic_status="source_encoded",
                        origin_group=f"route_bom:{route_item_id}",
                        adapter_version=adapter["adapter_version"],
                        source_refs=[f"route_bom.csv#{route_item_id}"],
                        assertion_key=[adapter["adapter_version"], profile_id, route_item_id, cell_id],
                        metadata={"mapping_status": row.get("mapping_status") or None},
                    )
                )
    return result


def derive_capability_matches(
    assertions: list[dict[str, Any]], config: dict[str, Any]
) -> list[dict[str, Any]]:
    adapter = _adapter(config, "capability_match_join")
    if adapter.get("relation_type") != "capability_matches_route":
        raise RelationIndexError("capability match adapter may only emit capability_matches_route")
    if "company_serves_route" not in (adapter.get("forbidden_outputs") or []):
        raise RelationIndexError("capability match contract must forbid company_serves_route")

    capabilities: dict[str, list[dict[str, Any]]] = defaultdict(list)
    requirements: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in assertions:
        cell = item["scope"].get("capability_cell_id")
        if item["relation_type"] == "company_has_capability_at" and cell:
            capabilities[cell].append(item)
        elif item["relation_type"] == "route_requires_capability" and cell:
            requirements[cell].append(item)

    result = []
    for cell_id in sorted(set(capabilities) & set(requirements)):
        for capability in capabilities[cell_id]:
            for requirement in requirements[cell_id]:
                profile_id = requirement["scope"]["route_profile_id"]
                result.append(
                    make_assertion(
                        relation_type="capability_matches_route",
                        subject_ref=capability["subject_ref"],
                        object_ref=f"route_profile:{profile_id}",
                        scope={
                            "route_profile_id": profile_id,
                            "capability_cell_id": cell_id,
                        },
                        valid_time=capability["valid_time"],
                        modality="actual",
                        polarity="supporting",
                        epistemic_status="derived_candidate",
                        origin_group=(
                            f"derived:{capability['origin_group']}|{requirement['origin_group']}"
                        ),
                        adapter_version=adapter["adapter_version"],
                        source_refs=[capability["assertion_id"], requirement["assertion_id"]],
                        assertion_key=[
                            adapter["adapter_version"],
                            capability["assertion_id"],
                            requirement["assertion_id"],
                        ],
                        metadata={"canonical_write_allowed": False},
                    )
                )
    return result


def adapt_calls(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    adapter = _adapter(config, "calls_product_lifecycle")
    events = {row["event_id"]: row for row in load_csv(root / "calls/events.csv")}
    claims = {
        row["event_claim_id"]: row for row in load_csv(root / "calls/event_claims.csv")
    }
    result = []
    for evidence in load_csv(root / "calls/event_evidence.csv"):
        event = events.get(evidence["event_id"])
        claim = claims.get(evidence["event_claim_id"])
        if event is None or claim is None:
            raise RelationIndexError(f"unresolved calls evidence {evidence.get('evidence_id')}")
        modality = "planned" if claim["statement_kind"] == "forward_looking" else "actual"
        relationship = evidence["relationship"]
        if relationship == "contradicts" or event["event_status"] == "contradicted":
            polarity = "contradicting"
        elif relationship == "withdraws" or event["event_status"] == "withdrawn":
            polarity = "withdrawn"
        elif relationship == "corrects" or event["event_status"] == "corrected":
            polarity = "limiting"
        else:
            polarity = "supporting"
        program_id = event["program_id"]
        stage = event["lifecycle_stage"]
        result.append(
            make_assertion(
                relation_type="product_has_lifecycle_stage",
                subject_ref=f"product_or_program:{program_id}",
                object_ref=f"lifecycle_stage:{stage}",
                scope={
                    "program_id": program_id,
                    "primary_subject_id": event["primary_subject_id"],
                },
                valid_time={
                    "start": event["occurred_start"] or None,
                    "end": event["occurred_end"] or None,
                },
                modality=modality,
                polarity=polarity,
                epistemic_status="source_encoded",
                origin_group=evidence["origin_group"],
                adapter_version=adapter["adapter_version"],
                source_refs=[
                    f"calls/events.csv#{event['event_id']}",
                    f"calls/event_claims.csv#{claim['event_claim_id']}",
                    f"calls/event_evidence.csv#{evidence['evidence_id']}",
                ],
                assertion_key=[adapter["adapter_version"], evidence["evidence_id"]],
                metadata={
                    "event_status": event["event_status"],
                    "statement_kind": claim["statement_kind"],
                },
            )
        )
    return result


def adapt_explicit_assertions(
    path: Path, config: dict[str, Any], known_profile_ids: set[str]
) -> list[dict[str, Any]]:
    adapter = _adapter(config, "explicit_relation_assertions")
    data = load_yaml(path)
    result = []
    seen_ids: set[str] = set()
    allowed_types = set(adapter.get("allowed_relation_types") or [])
    required = {
        "assertion_id",
        "relation_type",
        "subject_ref",
        "object_ref",
        "scope",
        "valid_time",
        "modality",
        "polarity",
        "origin_group",
        "source_refs",
    }
    for index, item in enumerate(data.get("assertions") or [], start=1):
        if not isinstance(item, dict):
            raise RelationIndexError(f"explicit assertion {index} must be a mapping")
        missing = sorted(required - set(item))
        if missing:
            raise RelationIndexError(f"explicit assertion {index} missing: {', '.join(missing)}")
        assertion_id = item["assertion_id"]
        if assertion_id in seen_ids:
            raise RelationIndexError(f"duplicate explicit assertion_id: {assertion_id}")
        seen_ids.add(assertion_id)
        relation_type = item["relation_type"]
        if relation_type not in allowed_types:
            raise RelationIndexError(f"explicit relation type not allowed: {relation_type}")
        if relation_type == "company_serves_route":
            profile_id = item["scope"].get("route_profile_id")
            expected_object = f"route_profile:{profile_id}"
            if profile_id not in known_profile_ids or item["object_ref"] != expected_object:
                raise RelationIndexError(
                    f"{assertion_id}: company_serves_route requires a frozen exact route profile"
                )
        result.append(
            make_assertion(
                relation_type=relation_type,
                subject_ref=item["subject_ref"],
                object_ref=item["object_ref"],
                scope=item["scope"],
                valid_time=item["valid_time"],
                modality=item["modality"],
                polarity=item["polarity"],
                epistemic_status="explicit_reviewed",
                origin_group=item["origin_group"],
                adapter_version=adapter["adapter_version"],
                source_refs=item["source_refs"],
                assertion_key=[adapter["adapter_version"], assertion_id],
                assertion_id=assertion_id,
                withdraws_assertion_ids=item.get("withdraws_assertion_ids") or [],
                metadata=item.get("metadata"),
            )
        )
    return result


def _time_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_start, left_end = left.get("start"), left.get("end")
    right_start, right_end = right.get("start"), right.get("end")
    if left_end and right_start and left_end < right_start:
        return False
    if right_end and left_start and right_end < left_start:
        return False
    return True


def assertions_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left["slot_id"] == right["slot_id"]
        and left["scope"] == right["scope"]
        and left["modality"] == right["modality"]
        and _time_overlap(left["valid_time"], right["valid_time"])
        and {left["polarity"], right["polarity"]}
        == {"supporting", "contradicting"}
    )


def compute_slot_states(assertions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_slot: dict[str, list[dict[str, Any]]] = defaultdict(list)
    known_ids = {item["assertion_id"] for item in assertions}
    for item in assertions:
        by_slot[item["slot_id"]].append(item)

    result = []
    for slot_id in sorted(by_slot):
        items = sorted(by_slot[slot_id], key=lambda item: item["assertion_id"])
        withdrawn_ids = {
            target
            for item in items
            if item["polarity"] == "withdrawn"
            for target in item.get("withdraws_assertion_ids") or []
            if target in known_ids
        }
        active = [
            item
            for item in items
            if item["polarity"] != "withdrawn" and item["assertion_id"] not in withdrawn_ids
        ]
        supports = [item for item in active if item["polarity"] == "supporting"]
        limits = [item for item in active if item["polarity"] == "limiting"]
        contradicts = [item for item in active if item["polarity"] == "contradicting"]
        conflict_pairs = sorted(
            [left["assertion_id"], right["assertion_id"]]
            for left in supports
            for right in contradicts
            if assertions_conflict(left, right)
        )
        if conflict_pairs:
            effective_status = "conflicted"
        elif supports and limits:
            effective_status = "limited"
        elif supports:
            effective_status = "supported"
        elif contradicts:
            effective_status = "contradicted"
        elif limits:
            effective_status = "limited"
        elif withdrawn_ids or any(item["polarity"] == "withdrawn" for item in items):
            effective_status = "withdrawn"
        else:
            effective_status = "unknown"

        identity = slot_identity(
            items[0]["relation_type"],
            items[0]["subject_ref"],
            items[0]["object_ref"],
            items[0]["scope"],
        )
        result.append(
            {
                "slot_id": slot_id,
                **identity,
                "effective_status": effective_status,
                "assertion_ids": [item["assertion_id"] for item in items],
                "active_assertion_ids": [item["assertion_id"] for item in active],
                "supporting_assertion_ids": [item["assertion_id"] for item in supports],
                "limiting_assertion_ids": [item["assertion_id"] for item in limits],
                "contradicting_assertion_ids": [item["assertion_id"] for item in contradicts],
                "withdrawal_assertion_ids": [
                    item["assertion_id"] for item in items if item["polarity"] == "withdrawn"
                ],
                "withdrawn_assertion_ids": sorted(withdrawn_ids),
                "conflict_pairs": conflict_pairs,
                "independent_origin_counts": {
                    polarity: len(
                        {
                            item["origin_group"]
                            for item in active
                            if item["polarity"] == polarity
                        }
                    )
                    for polarity in ("supporting", "limiting", "contradicting")
                },
            }
        )
    return result


def validate_assertions(
    assertions: list[dict[str, Any]], relation_contract: dict[str, Any]
) -> None:
    definitions = relation_contract.get("relation_types") or {}
    assertion_contract = relation_contract.get("assertion_contract") or {}
    required = set(assertion_contract.get("required_fields") or [])
    polarities = set(assertion_contract.get("polarity_enum") or [])
    epistemic = set(assertion_contract.get("epistemic_status_enum") or [])
    modalities = set(assertion_contract.get("modality_enum") or [])
    seen_ids: set[str] = set()
    for item in assertions:
        missing = sorted(required - set(item))
        if missing:
            raise RelationIndexError(f"{item.get('assertion_id')}: missing {missing}")
        if item["assertion_id"] in seen_ids:
            raise RelationIndexError(f"duplicate assertion ID: {item['assertion_id']}")
        seen_ids.add(item["assertion_id"])
        definition = definitions.get(item["relation_type"])
        if not isinstance(definition, dict):
            raise RelationIndexError(f"unknown relation type: {item['relation_type']}")
        if item["polarity"] not in polarities:
            raise RelationIndexError(f"invalid polarity: {item['polarity']}")
        if item["epistemic_status"] not in epistemic:
            raise RelationIndexError(f"invalid epistemic status: {item['epistemic_status']}")
        if item["modality"] not in modalities:
            raise RelationIndexError(f"invalid modality: {item['modality']}")
        if item["epistemic_status"] not in definition.get("allowed_epistemic_status", []):
            raise RelationIndexError(
                f"{item['relation_type']} does not allow {item['epistemic_status']}"
            )
        if not item["origin_group"] or not isinstance(item["source_refs"], list):
            raise RelationIndexError(f"{item['assertion_id']}: provenance is incomplete")


def build_relation_graph(
    root: Path = ROOT,
    contracts_dir: Path | None = None,
    assertions_path: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    contracts_dir = contracts_dir or root / "contracts"
    assertions_path = assertions_path or root / "relation_assertions.yaml"
    relation_contract = load_yaml(contracts_dir / "relation_types.yaml")
    adapter_contract = load_yaml(contracts_dir / "relation_adapters.yaml")
    profile_ids = {
        item["route_profile_id"] for item in adapter_contract.get("route_profiles") or []
    }

    assertions = adapt_points(root, adapter_contract)
    assertions.extend(adapt_route_requirements(root, adapter_contract))
    assertions.extend(adapt_calls(root, adapter_contract))
    assertions.extend(adapt_explicit_assertions(assertions_path, adapter_contract, profile_ids))
    assertions.extend(derive_capability_matches(assertions, adapter_contract))
    assertions.sort(key=lambda item: item["assertion_id"])
    validate_assertions(assertions, relation_contract)
    return assertions, compute_slot_states(assertions)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--contracts-dir", type=Path)
    parser.add_argument("--assertions", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    contracts = (args.contracts_dir or root / "contracts").resolve()
    assertions_path = (args.assertions or root / "relation_assertions.yaml").resolve()
    output = (args.output_dir or root / "out").resolve()
    assertions, slot_states = build_relation_graph(root, contracts, assertions_path)
    write_jsonl(output / "relation_assertion_index.jsonl", assertions)
    write_jsonl(output / "relation_slot_states.jsonl", slot_states)
    print(
        f"relation index: {len(assertions)} assertions, "
        f"{len(slot_states)} slots -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
