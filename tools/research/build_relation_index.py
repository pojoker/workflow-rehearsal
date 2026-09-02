#!/usr/bin/env python3
"""Build a deterministic, read-only relation assertion and slot-state index.

The JSONL outputs are disposable projections. Existing CSV/YAML ledgers remain
the sources of truth.

This module implements the CodeBuddy hy3 reducer-pilot fixes:
  A. explicit_reviewed write gate (reference registry + provenance fields)
  B. route identity / requirement-group semantics
  C. point-status -> capability modality mapping
  D. relation-specific slot identity (identity scope vs assertion context)
  E. strict ISO time + as_of / modality state merge
  F. withdrawal / revision integrity
  G. company_serves_route product+service_kind narrowing
  H. build manifest (assertion index <-> slot states binding)
  I. calls adapter event-category isolation
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import date as _date
from datetime import datetime as _dt
from pathlib import Path
from typing import Any, Iterable

import yaml


# When this file is invoked as ``python tools/research/build_relation_index.py``
# Python puts ``tools/research`` (rather than the repository root) on
# ``sys.path``.  The lead projection is intentionally kept in the question
# reducer module, so make the script entry point behave like ``python -m``
# without requiring callers to set PYTHONPATH.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_CONTRACTS = ROOT / "contracts"
DEFAULT_ASSERTIONS = ROOT / "relation_assertions.yaml"
DEFAULT_OUTPUT = ROOT / "out"

BUILD_MANIFEST_KEY = "__build_manifest__"

# C. point status -> capability modality mapping
POINT_STATUS_ACTUAL = {"生产中"}
POINT_STATUS_PLANNED = {"在建"}

# G. controlled service_kind vocabulary
SERVICE_KIND_ENUM = {"demonstrated", "listed", "qualifying", "shipping", "deployed"}

# F. revision kinds are deliberately narrower than arbitrary event labels.  A
# correction patch is not implemented by this pilot and therefore must fail at
# the adapter boundary instead of being downgraded to a limiting assertion.
REVISION_KIND_ENUM = {"withdraws", "supersedes", "corrects"}
UNSUPPORTED_REVISION_KINDS = {"corrects"}

# A. kinds accepted for an evidence_claim_ref (a bare source ref is not evidence)
EVIDENCE_REF_KINDS = {"claim", "disclosure", "event"}
# A. kinds accepted for a source_ref (a citation back to a ledger object)
SOURCE_REF_KINDS = {"source", "point", "claim", "disclosure", "event"}
REFERENCE_KIND_ENUM = SOURCE_REF_KINDS | {"product"}

# ISO date / datetime: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS (strict, zero-padded)
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?$")


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


def parse_iso_datetime(value: Any) -> str:
    """Strict ISO parse. Rejects 2026-9-1, FY2026Q3, etc. Returns canonical str."""
    if value in (None, ""):
        raise RelationIndexError(f"empty time is not a parseable ISO value: {value!r}")
    text = str(value).strip()
    if not _ISO_RE.match(text):
        raise RelationIndexError(f"non-ISO time rejected: {value!r}")
    if "T" in text:
        parsed = _dt.strptime(text, "%Y-%m-%dT%H:%M:%S")
    else:
        parsed = _dt.strptime(text, "%Y-%m-%d")
    return parsed.strftime("%Y-%m-%dT%H:%M:%S" if "T" in text else "%Y-%m-%d")


def normalized_time(value: Any | None) -> dict[str, str | None]:
    """Normalize valid_time. None boundary => unknown time (no boundary)."""
    if value is None:
        value = {}
    elif not isinstance(value, dict):
        raise RelationIndexError("valid_time must be a mapping")
    def normalize_boundary(boundary: Any) -> str | None:
        if boundary in (None, ""):
            return None
        if isinstance(boundary, (_dt, _date)):
            boundary = boundary.isoformat()
        return parse_iso_datetime(boundary)

    normalized = {
        "start": normalize_boundary(value.get("start")),
        "end": normalize_boundary(value.get("end")),
    }
    if normalized["start"] and normalized["end"] and normalized["end"] < normalized["start"]:
        raise RelationIndexError(
            f"valid_time end {normalized['end']!r} precedes start {normalized['start']!r}"
        )
    return normalized


def relation_slot_identity(
    relation_type: str,
    subject_ref: str,
    object_ref: str,
    scope: dict[str, Any],
    relation_contract: dict[str, Any],
) -> dict[str, Any]:
    """D. slot identity uses only the contract-declared slot_identity_fields.

    Context fields (geography/customer/etc.) are intentionally excluded so that
    adding context does NOT mint a brand-new, unrelated slot unless an explicit
    roll-up policy says so.
    """
    definition = (relation_contract.get("relation_types") or {}).get(relation_type) or {}
    id_fields = definition.get("slot_identity_fields") or ["subject_ref", "object_ref"]
    parts: dict[str, Any] = {"relation_type": relation_type}
    for field in id_fields:
        if field == "subject_ref":
            parts[field] = subject_ref
        elif field == "object_ref":
            parts[field] = object_ref
        else:
            parts[field] = scope.get(field)
    return parts


def slot_identity(
    relation_type: str,
    subject_ref: str,
    object_ref: str,
    scope: dict[str, Any],
) -> dict[str, Any]:
    # Backwards-compatible shallow identity (used by recompute/question target).
    return {
        "relation_type": relation_type,
        "subject_ref": subject_ref,
        "object_ref": object_ref,
        "scope": scope,
    }


def _field_value(field: str, item: dict[str, Any] | None = None, **values: Any) -> Any:
    if field in values:
        return values[field]
    if item is not None and field in ("subject_ref", "object_ref", "modality", "polarity"):
        return item.get(field)
    return (item or {}).get("scope", {}).get(field)


def comparison_values(
    item: dict[str, Any], relation_contract: dict[str, Any]
) -> dict[str, Any]:
    """8. the contract-declared comparison surface of one assertion.

    Two assertions are only comparable (conflict / limit / withdraw) when their
    comparison fields agree. Identity fields are always a subset of the
    comparison fields, so a comparison can never be looser than the identity.
    """
    definition = (relation_contract.get("relation_types") or {}).get(
        item["relation_type"]
    ) or {}
    fields = definition.get("comparison_fields") or ["subject_ref", "object_ref"]
    return {field: _field_value(field, item) for field in fields}


def validate_relation_contract(relation_contract: dict[str, Any]) -> None:
    """D/8. every relation must declare the three field groups, coherently."""
    if not isinstance(relation_contract, dict):
        raise RelationIndexError("relation contract must be a mapping")
    relation_types = relation_contract.get("relation_types")
    if not isinstance(relation_types, dict) or not relation_types:
        raise RelationIndexError("relation contract must declare relation_types")
    identity_contract = relation_contract.get("identity_contract") or {}
    required = identity_contract.get("required_declarations") or [
        "slot_identity_fields",
        "comparison_fields",
        "context_fields",
    ]
    for name, definition in relation_types.items():
        if not isinstance(definition, dict):
            raise RelationIndexError(f"{name}: relation definition must be a mapping")
        for key in required:
            if not isinstance(definition.get(key), list):
                raise RelationIndexError(f"{name}: contract must declare {key} as a list")
            # context_fields may legitimately be empty (the relation has no
            # context); identity and comparison must actually say something.
            if not definition[key] and key != "context_fields":
                raise RelationIndexError(f"{name}: contract must declare a non-empty {key}")
        for key in required:
            values = definition[key]
            if any(not isinstance(value, str) or not value for value in values):
                raise RelationIndexError(
                    f"{name}: {key} entries must be non-empty strings"
                )
            if len(values) != len(set(values)):
                raise RelationIndexError(f"{name}: {key} contains duplicate fields")
        identity = set(definition["slot_identity_fields"])
        comparison = set(definition["comparison_fields"])
        if identity_contract.get("slot_identity_subset_of_comparison", True):
            missing = sorted(identity - comparison)
            if missing:
                raise RelationIndexError(
                    f"{name}: slot_identity_fields {missing} are not part of "
                    f"comparison_fields (comparison must not be looser than identity)"
                )
        overlap = set(definition["context_fields"]) & identity
        if overlap:
            raise RelationIndexError(
                f"{name}: {sorted(overlap)} declared both as identity and as context"
            )
        non_comparable_context = set(definition.get("non_comparable_context_fields") or [])
        if not non_comparable_context <= set(definition["context_fields"]):
            raise RelationIndexError(
                f"{name}: non_comparable_context_fields must be context fields"
            )
        missing_context = (
            set(definition["context_fields"])
            - non_comparable_context
            - comparison
        )
        if missing_context:
            raise RelationIndexError(
                f"{name}: comparable context fields {sorted(missing_context)} "
                "must be part of comparison_fields"
            )
    assertion_contract = relation_contract.get("assertion_contract") or {}
    # These declarations are the security boundary, not optional documentation.
    # Keep a malformed contract from weakening the checks below by omission.
    expected_gate_fields = {
        "review_receipt_id",
        "review_receipt_kind",
        "reviewer",
        "reviewed_at",
        "evidence_claim_refs",
        "source_refs",
        "supports",
        "does_not_support",
    }
    gate_fields = assertion_contract.get("reviewed_write_gate_fields")
    if set(gate_fields or []) != expected_gate_fields:
        raise RelationIndexError(
            "assertion_contract.reviewed_write_gate_fields must declare the complete "
            "review receipt/evidence/support gate"
        )
    if assertion_contract.get("review_receipt_registry_required") is not True:
        raise RelationIndexError(
            "assertion_contract.review_receipt_registry_required must be true"
        )
    evidence_kinds = assertion_contract.get("evidence_claim_ref_kinds")
    if set(evidence_kinds or []) != EVIDENCE_REF_KINDS:
        raise RelationIndexError(
            "assertion_contract.evidence_claim_ref_kinds must declare claim/disclosure/event"
        )
    revision_enum = assertion_contract.get("revision_kind_enum")
    if revision_enum is not None and set(revision_enum) != REVISION_KIND_ENUM:
        raise RelationIndexError(
            "assertion_contract.revision_kind_enum must exactly declare "
            "withdraws/supersedes/corrects"
        )
    unsupported_revision = assertion_contract.get("unsupported_revision_kinds")
    if unsupported_revision is not None and set(unsupported_revision) != UNSUPPORTED_REVISION_KINDS:
        raise RelationIndexError(
            "assertion_contract.unsupported_revision_kinds must exactly declare corrects"
        )
    query_policy = assertion_contract.get("query_modality_policy")
    if (
        not isinstance(query_policy, dict)
        or query_policy.get("null_means_all_declared_modalities") is not True
        or query_policy.get("cross_modality_effects") != "forbidden"
    ):
        raise RelationIndexError(
            "assertion_contract.query_modality_policy must isolate cross-modality effects"
        )
    service_kinds = relation_contract.get("service_kind_enum")
    if set(service_kinds or []) != SERVICE_KIND_ENUM:
        raise RelationIndexError(
            "service_kind_enum must exactly declare demonstrated/listed/qualifying/"
            "shipping/deployed"
        )


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
    revises_assertion_ids: Iterable[str] = (),
    withdraws_assertion_ids: Iterable[str] | None = None,
    metadata: dict[str, Any] | None = None,
    relation_contract: dict[str, Any] | None = None,
    # A/F. reviewed-write-gate + revision provenance, preserved on the index.
    review_receipt_id: str | None = None,
    review_receipt_kind: str | None = None,
    reviewer: str | None = None,
    reviewed_at: str | None = None,
    evidence_claim_refs: Iterable[str] | None = None,
    supports: list[str] | None = None,
    does_not_support: list[str] | None = None,
    revision_kind: str | None = None,
    effective_at: str | None = None,
    retroactive: bool | None = None,
) -> dict[str, Any]:
    # Keep the pre-pilot keyword as a compatibility alias.  New projections use
    # ``revises_assertion_ids``; callers still using ``withdraws_assertion_ids``
    # receive the same normalized revision target instead of a TypeError.
    revises = set(revises_assertion_ids)
    if withdraws_assertion_ids is not None:
        legacy_revises = set(withdraws_assertion_ids)
        if revises and revises != legacy_revises:
            raise RelationIndexError(
                "revises_assertion_ids and withdraws_assertion_ids disagree"
            )
        revises = legacy_revises

    contract_supplied = relation_contract is not None
    relation_contract = relation_contract or {}
    # With no contract, preserve the original helper's whole-scope identity for
    # third-party callers.  Production adapters always pass the validated
    # relation contract and therefore use relation-specific identity fields.
    identity = (
        relation_slot_identity(relation_type, subject_ref, object_ref, scope, relation_contract)
        if contract_supplied
        else slot_identity(relation_type, subject_ref, object_ref, scope)
    )
    # D. separate identity scope (slot-identity fields) from assertion context
    # (everything else in scope). The assertion index must expose both.
    definition = (relation_contract.get("relation_types") or {}).get(relation_type) or {}
    id_fields = definition.get("slot_identity_fields") or ["subject_ref", "object_ref"]
    identity_scope = (
        {field: scope[field] for field in id_fields if field in scope}
        if contract_supplied
        else dict(scope)
    )
    assertion_context = (
        {k: v for k, v in scope.items() if k not in id_fields}
        if contract_supplied
        else {}
    )
    result = {
        "assertion_id": assertion_id or stable_id("RA", assertion_key),
        "slot_id": stable_id("RS", identity),
        **slot_identity(relation_type, subject_ref, object_ref, scope),
        "identity_scope": identity_scope,
        "assertion_context": assertion_context,
        "valid_time": normalized_time(valid_time),
        "modality": modality,
        "polarity": polarity,
        "epistemic_status": epistemic_status,
        "origin_group": origin_group,
        "adapter_version": adapter_version,
        "source_refs": sorted(set(source_refs)),
    }
    revises_sorted = sorted(revises)
    if revises_sorted:
        result["revises_assertion_ids"] = revises_sorted
        if withdraws_assertion_ids is not None:
            # Preserve the legacy output spelling when that spelling was used
            # at the API boundary; validators accept and cross-check both.
            result["withdraws_assertion_ids"] = revises_sorted
    if metadata:
        result["metadata"] = metadata
    # A. reviewed-write-gate provenance (only meaningful for explicit_reviewed).
    if review_receipt_id is not None:
        result["review_receipt_id"] = review_receipt_id
    if review_receipt_kind is not None:
        result["review_receipt_kind"] = review_receipt_kind
    if reviewer is not None:
        result["reviewer"] = reviewer
    if reviewed_at is not None:
        result["reviewed_at"] = reviewed_at
    if evidence_claim_refs is not None:
        result["evidence_claim_refs"] = sorted(set(evidence_claim_refs))
    if supports is not None:
        result["supports"] = supports
    if does_not_support is not None:
        result["does_not_support"] = does_not_support
    # F. revision provenance (withdrawal / correction / supersession integrity).
    if revision_kind is not None:
        result["revision_kind"] = revision_kind
    if effective_at is not None:
        result["effective_at"] = effective_at
    if retroactive is not None:
        result["retroactive"] = retroactive
    return result


# ---------------------------------------------------------------------------
# A. reference registry
# ---------------------------------------------------------------------------
def _canonical_company(
    entity_id: str | None,
    universe: dict[str, str],
    watch_entities: dict[str, str],
) -> str | None:
    """Resolve a ledger entity to the canonical company identity used by slots.

    ``claims.csv`` deliberately has no ``claimant_entity_id`` column.  Its
    company is the company that owns the linked source row, not an empty
    placeholder.  For entities that are only an observation/watch item we keep
    an ``entity:`` identity unless the ledger explicitly promotes it to a
    universe company; this prevents a named counterparty from becoming the
    subject of a company relation by accident.
    """
    value = str(entity_id or "").strip()
    if not value:
        return None
    if value.startswith(("company:", "entity:")):
        return value
    if value in universe:
        return f"company:{universe[value]}"
    if value in watch_entities:
        return watch_entities[value]
    # Unknown issuer codes are retained as an explicit company identity.  They
    # are never silently mapped to another issuer, and a reviewed gate can only
    # pass when this identity agrees with the assertion subject.
    return f"company:{value}"


def _load_extra_registry(path: Path) -> dict[str, Any]:
    """Load and validate an additional registry before it can affect a build.

    Extra registries are test/fixture inputs, not an arbitrary override hook.
    They therefore have a version, an id, typed references, canonical company
    identities, and (for products) source links.  The manifest records the
    registry file hash so a later consumer cannot inject an unbound product.
    """
    data = load_yaml(path)
    if data.get("schema_version") != "research_reference_registry_v1":
        raise RelationIndexError(
            f"{path}: extra registry must declare schema_version "
            "research_reference_registry_v1"
        )
    registry_id = data.get("registry_id")
    if not isinstance(registry_id, str) or not registry_id.strip():
        raise RelationIndexError(f"{path}: extra registry_id is required")
    references = data.get("references")
    if not isinstance(references, list):
        raise RelationIndexError(f"{path}: references must be a list")
    seen: set[str] = set()
    for index, entry in enumerate(references, start=1):
        if not isinstance(entry, dict):
            raise RelationIndexError(f"{path}: reference {index} must be a mapping")
        ref = entry.get("ref")
        kind = entry.get("kind")
        company = entry.get("company")
        origin = entry.get("origin_group") or entry.get("origin")
        if not isinstance(ref, str) or not ref.strip():
            raise RelationIndexError(f"{path}: reference {index} has no ref")
        if ref in seen:
            raise RelationIndexError(f"{path}: duplicate reference {ref!r}")
        seen.add(ref)
        if kind not in REFERENCE_KIND_ENUM:
            raise RelationIndexError(
                f"{path}: reference {ref!r} has unsupported kind {kind!r}"
            )
        if kind == "product" and not ref.startswith("product:"):
            raise RelationIndexError(
                f"{path}: product reference {ref!r} must use the canonical product:<id> form"
            )
        if not isinstance(company, str) or not company.startswith("company:"):
            raise RelationIndexError(
                f"{path}: reference {ref!r} must carry a canonical company: identity"
            )
        if not isinstance(origin, str) or not origin.strip():
            raise RelationIndexError(f"{path}: reference {ref!r} needs origin_group")
        if kind == "product":
            source_refs = entry.get("source_refs")
            if not isinstance(source_refs, list) or not source_refs:
                raise RelationIndexError(
                    f"{path}: product {ref!r} must declare non-empty source_refs"
                )
            if any(not isinstance(source_ref, str) or not source_ref for source_ref in source_refs):
                raise RelationIndexError(
                    f"{path}: product {ref!r} has an invalid source_refs entry"
                )
        for key in ("linked_refs", "source_refs", "evidence_claim_refs"):
            if key in entry and not isinstance(entry[key], list):
                raise RelationIndexError(f"{path}: {ref!r}.{key} must be a list")

    receipts = data.get("review_receipts") or []
    if not isinstance(receipts, list):
        raise RelationIndexError(f"{path}: review_receipts must be a list")
    receipt_ids: set[str] = set()
    for index, receipt in enumerate(receipts, start=1):
        if not isinstance(receipt, dict):
            raise RelationIndexError(f"{path}: review receipt {index} must be a mapping")
        receipt_id = receipt.get("receipt_id")
        if not isinstance(receipt_id, str) or not receipt_id.strip():
            raise RelationIndexError(f"{path}: review receipt {index} has no receipt_id")
        if receipt_id in receipt_ids:
            raise RelationIndexError(f"{path}: duplicate receipt_id {receipt_id!r}")
        receipt_ids.add(receipt_id)
        reviewer = receipt.get("reviewer")
        subject_ref = receipt.get("subject_ref")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise RelationIndexError(f"{path}: receipt {receipt_id!r} needs reviewer")
        if not isinstance(subject_ref, str) or not subject_ref.startswith("company:"):
            raise RelationIndexError(
                f"{path}: receipt {receipt_id!r} needs canonical company subject_ref"
            )
        receipt_kind = receipt.get("receipt_kind")
        if not isinstance(receipt_kind, str) or not receipt_kind.strip():
            raise RelationIndexError(
                f"{path}: receipt {receipt_id!r} needs receipt_kind"
            )
    return data


class ReferenceRegistry(dict[str, dict[str, Any]]):
    """Reference map carrying the provenance of any extra registry inputs.

    A plain caller-created dictionary must not be able to mint a product target
    merely by adding ``kind=product`` and a guessed ``registry_id``.  The
    builder marks registry ids only after parsing a contract-bound extra file;
    consumers can then distinguish that safe map from an untrusted ad-hoc dict
    while keeping the historical mapping API intact.
    """

    def __init__(self) -> None:
        super().__init__()
        self.bound_registry_ids: set[str] = set()
        self.bound_registry_refs: list[dict[str, str]] = []


def build_reference_registry(
    root: Path, extra_registries: Iterable[Path] = ()
) -> dict[str, dict[str, Any]]:
    """Collect every resolvable claim/source/disclosure/point/event object.

    An explicit_reviewed assertion may only cite references that resolve here.
    `kind` and (where known) `company` are recorded so the write gate can enforce
    reference-kind and semantic-linkage checks conservatively.
    """
    registry: ReferenceRegistry = ReferenceRegistry()
    extra_registries = tuple(Path(path) for path in extra_registries)

    universe = {
        row.get("company_id", "").strip(): row.get("company_name", "").strip()
        for row in load_csv(root / "calls/universe.csv")
        if row.get("company_id") and row.get("company_name")
    }
    watch_entities = {}
    for row in load_csv(root / "calls/watch_entities.csv"):
        entity_id = row.get("entity_id", "").strip()
        promoted = row.get("promoted_company_id", "").strip()
        if entity_id and promoted and promoted in universe:
            watch_entities[entity_id] = f"company:{universe[promoted]}"
        elif entity_id:
            watch_entities[entity_id] = f"entity:{entity_id}"

    def add(
        ref: str,
        kind: str,
        origin: str | None,
        company: str | None = None,
        **metadata: Any,
    ) -> None:
        if not ref:
            return
        if ref in registry:
            existing = registry[ref]
            if existing.get("kind") != kind or (
                company and existing.get("company") and existing.get("company") != company
            ):
                raise RelationIndexError(f"reference {ref!r} is defined with conflicting identities")
            if origin and not existing.get("origin"):
                existing["origin"] = origin
            if company and not existing.get("company"):
                existing["company"] = company
            for key, value in metadata.items():
                if value in (None, "", []):
                    continue
                if isinstance(value, list):
                    existing[key] = sorted(set(existing.get(key) or []) | set(value))
                else:
                    existing.setdefault(key, value)
            return
        registry[ref] = {
            "kind": kind,
            "origin": origin,
            "company": company,
            **{key: value for key, value in metadata.items() if value not in (None, "", [])},
        }

    def link(left: str, right: str) -> None:
        if left not in registry or right not in registry or left == right:
            return
        for source, target in ((left, right), (right, left)):
            links = set(registry[source].get("linked_refs") or [])
            links.add(target)
            registry[source]["linked_refs"] = sorted(links)

    point_rows = load_csv(root / "points.csv")
    source_rows = load_csv(root / "calls/sources.csv")
    claim_rows = load_csv(root / "calls/claims.csv")
    disclosure_rows = load_csv(root / "calls/disclosures.csv")
    event_claim_rows = load_csv(root / "calls/event_claims.csv")
    event_rows = load_csv(root / "calls/events.csv")
    event_evidence_rows = load_csv(root / "calls/event_evidence.csv")

    source_company: dict[str, str | None] = {}
    for row in source_rows:
        source_id = row.get("source_id", "").strip()
        company = _canonical_company(row.get("company_id"), universe, watch_entities)
        source_company[source_id] = company
        add(
            f"source:{source_id}",
            "source",
            f"source:{source_id}" if source_id else None,
            company,
            source_id=source_id,
        )

    for row in point_rows:
        point_id = row.get("point_id", "").strip()
        company_name = row.get("公司", "").strip()
        company = f"company:{company_name}" if company_name else None
        point_origin = f"point:{point_id}" if point_id else None
        add(f"point:{point_id}", "point", point_origin, company, point_id=point_id)
        # The index adapter uses points.csv#Pxxx as its source ref; register
        # that spelling too so a reviewed sidecar cannot bypass the same gate.
        add(f"points.csv#{point_id}", "point", point_origin, company, point_id=point_id)
        link(f"point:{point_id}", f"points.csv#{point_id}")

    claim_source: dict[str, str] = {}
    for row in claim_rows:
        claim_id = row.get("claim_id", "").strip()
        source_id = row.get("source_id", "").strip()
        claim_source[claim_id] = source_id
        company = source_company.get(source_id)
        add(
            f"claim:{claim_id}",
            "claim",
            registry.get(f"source:{source_id}", {}).get("origin") or f"claim:{claim_id}",
            company,
            claim_id=claim_id,
            source_id=source_id,
        )
        link(f"claim:{claim_id}", f"source:{source_id}")

    disclosure_source: dict[str, str] = {}
    for row in disclosure_rows:
        disclosure_id = row.get("disclosure_id", "").strip()
        source_id = row.get("legacy_source_id", "").strip()
        disclosure_source[disclosure_id] = source_id
        company = _canonical_company(row.get("publisher_entity_id"), universe, watch_entities)
        add(
            f"disclosure:{disclosure_id}",
            "disclosure",
            row.get("origin_group", "").strip() or f"disclosure:{disclosure_id}",
            company,
            disclosure_id=disclosure_id,
            source_id=source_id,
        )
        link(f"disclosure:{disclosure_id}", f"source:{source_id}")

    # A source row has no independent-origin field in the calls schema.  When a
    # disclosure anchors that source, inherit the disclosure's canonical origin
    # so citing ``source:S`` plus ``disclosure:D`` does not look like two
    # unrelated origins merely because the source id was used as a placeholder.
    for source_ref, source_entry in registry.items():
        if source_entry.get("kind") != "source":
            continue
        disclosure_origins = sorted(
            {
                registry[linked]["origin"]
                for linked in source_entry.get("linked_refs") or []
                if linked in registry
                and registry[linked].get("kind") == "disclosure"
                and registry[linked].get("origin")
            }
        )
        if len(disclosure_origins) == 1:
            source_entry["origin"] = disclosure_origins[0]
            source_id = source_entry.get("source_id")
            for claim_entry in registry.values():
                if claim_entry.get("kind") == "claim" and claim_entry.get("source_id") == source_id:
                    claim_entry["origin"] = disclosure_origins[0]

    event_claim_disclosure: dict[str, str] = {}
    for row in event_claim_rows:
        claim_id = row.get("event_claim_id", "").strip()
        disclosure_id = row.get("disclosure_id", "").strip()
        event_claim_disclosure[claim_id] = disclosure_id
        company = _canonical_company(row.get("claimant_entity_id"), universe, watch_entities)
        disclosure = registry.get(f"disclosure:{disclosure_id}") or {}
        add(
            f"claim:{claim_id}",
            "claim",
            disclosure.get("origin") or f"claim:{claim_id}",
            company,
            claim_id=claim_id,
            disclosure_id=disclosure_id,
        )
        link(f"claim:{claim_id}", f"disclosure:{disclosure_id}")
        link(f"claim:{claim_id}", f"claim:{row.get('legacy_claim_id', '').strip()}")

    event_company: dict[str, str | None] = {}
    for row in event_rows:
        event_id = row.get("event_id", "").strip()
        company = _canonical_company(row.get("primary_subject_id"), universe, watch_entities)
        event_company[event_id] = company
        add(
            f"event:{event_id}",
            "event",
            f"program:{row.get('program_id', '').strip()}" if row.get("program_id") else f"event:{event_id}",
            company,
            event_id=event_id,
            program_id=row.get("program_id", "").strip(),
        )

    for row in event_evidence_rows:
        event_ref = f"event:{row.get('event_id', '').strip()}"
        claim_ref = f"claim:{row.get('event_claim_id', '').strip()}"
        event_entry = registry.get(event_ref)
        claim_entry = registry.get(claim_ref)
        if event_entry and row.get("origin_group") and not event_entry.get("origin"):
            event_entry["origin"] = row["origin_group"].strip()
        link(event_ref, claim_ref)

    # A fixture registry is accepted only after its own schema has passed and
    # never overwrites a production ledger identity.
    for path in extra_registries:
        data = _load_extra_registry(Path(path))
        registry_id = data["registry_id"]
        if registry_id in registry.bound_registry_ids:
            raise RelationIndexError(
                f"duplicate extra registry_id {registry_id!r}; registry identity must be unique"
            )
        registry.bound_registry_ids.add(registry_id)
        resolved_path = Path(path).resolve()
        try:
            relative_path = resolved_path.relative_to(Path(root).resolve())
        except ValueError:
            # External fixtures are identified by basename in manifests; the
            # build rejects duplicate basenames before writing the projection.
            relative_path = Path(resolved_path.name)
        registry_ref = {
            "path": relative_path.as_posix(),
            "sha256": hashlib.sha256(resolved_path.read_bytes()).hexdigest(),
        }
        if any(item["path"] == registry_ref["path"] for item in registry.bound_registry_refs):
            raise RelationIndexError(
                f"extra registry paths must have unique manifest-relative paths: "
                f"{registry_ref['path']!r}"
            )
        registry.bound_registry_refs.append(registry_ref)
        for entry in data.get("references") or []:
            ref = entry["ref"]
            if ref in registry:
                raise RelationIndexError(
                    f"extra registry {registry_id!r} attempts to override existing reference {ref!r}"
                )
            registry[ref] = {
                "kind": entry["kind"],
                "origin": entry.get("origin_group") or entry.get("origin"),
                "company": entry["company"],
                "registry_id": registry_id,
                "linked_refs": sorted(
                    set(entry.get("linked_refs") or [])
                    | set(entry.get("source_refs") or [])
                    | set(entry.get("evidence_claim_refs") or [])
                ),
                **{
                    key: entry[key]
                    for key in ("source_refs", "claim_id", "source_id", "disclosure_id", "event_id")
                    if key in entry
                },
            }
        # Product and evidence links are made bidirectional only when both
        # endpoints exist; the gate then rejects a dangling link.
        for entry in data.get("references") or []:
            for linked in (
                set(entry.get("linked_refs") or [])
                | set(entry.get("source_refs") or [])
                | set(entry.get("evidence_claim_refs") or [])
            ):
                link(entry["ref"], linked)
    return registry


def build_receipt_registry(
    adapter_contract: dict[str, Any], extra_registries: Iterable[Path] = ()
) -> dict[str, dict[str, Any]]:
    """A. build the safe review receipt registry.

    A reviewed assertion's `review_receipt_id` must resolve here and its
    `reviewer` must match the registered reviewer; the registered `subject_ref`
    must match the assertion's subject (semantic linkage: the receipt is for the
    reviewed company). Invalid/fake receipts are rejected by the gate.
    """
    registry: dict[str, dict[str, Any]] = {}
    production_receipts = adapter_contract.get("review_receipts")
    if not isinstance(production_receipts, list):
        raise RelationIndexError(
            "relation_adapters.yaml must declare review_receipts as a list"
        )
    for index, entry in enumerate(production_receipts, start=1):
        if not isinstance(entry, dict):
            raise RelationIndexError(f"review receipt {index} must be a mapping")
        receipt_id = entry.get("receipt_id")
        if receipt_id:
            if receipt_id in registry:
                raise RelationIndexError(f"duplicate review receipt_id: {receipt_id}")
            if (
                not isinstance(entry.get("reviewer"), str)
                or not entry.get("reviewer").strip()
                or not isinstance(entry.get("subject_ref"), str)
                or not entry.get("subject_ref").startswith("company:")
                or not isinstance(entry.get("receipt_kind"), str)
                or not entry.get("receipt_kind").strip()
            ):
                raise RelationIndexError(f"review receipt {receipt_id!r} is incomplete")
            registry[receipt_id] = {
                "reviewer": entry.get("reviewer"),
                "subject_ref": entry.get("subject_ref"),
                "receipt_kind": entry.get("receipt_kind"),
            }
    for path in extra_registries:
        data = _load_extra_registry(Path(path))
        for entry in data.get("review_receipts") or []:
            receipt_id = entry.get("receipt_id")
            if receipt_id:
                if receipt_id in registry:
                    raise RelationIndexError(f"duplicate review receipt_id: {receipt_id}")
                if (
                    not isinstance(entry.get("reviewer"), str)
                    or not entry.get("reviewer").strip()
                    or not isinstance(entry.get("subject_ref"), str)
                    or not entry.get("subject_ref").startswith("company:")
                    or not isinstance(entry.get("receipt_kind"), str)
                    or not entry.get("receipt_kind").strip()
                ):
                    raise RelationIndexError(f"review receipt {receipt_id!r} is incomplete")
                registry[receipt_id] = {
                    "reviewer": entry.get("reviewer"),
                    "subject_ref": entry.get("subject_ref"),
                    "receipt_kind": entry.get("receipt_kind"),
                }
    return registry


def derive_origin_group(source_refs: Iterable[str], registry: dict[str, dict[str, Any]]) -> str | None:
    """Canonical origin derived from resolved references (A/F)."""
    origins = sorted(
        {
            entry["origin"]
            for ref in source_refs
            if (entry := registry.get(ref)) and entry.get("origin")
        }
    )
    return origins[0] if origins else None


def derive_origin_groups(
    refs: Iterable[str], registry: dict[str, dict[str, Any]]
) -> set[str]:
    return {
        entry["origin"]
        for ref in refs
        if (entry := registry.get(ref)) and entry.get("origin")
    }


# ---------------------------------------------------------------------------
# B. route profile identity + requirement-group semantics
# ---------------------------------------------------------------------------
def route_profile_identity_hash(profile: dict[str, Any]) -> str:
    axes = profile.get("identity_axes") or {}
    return hashlib.sha256(canonical_json(axes).encode("utf-8")).hexdigest()


def validate_route_profiles(adapter_contract: dict[str, Any], route_bom_rows: dict[str, dict[str, str]]) -> None:
    """B/2. versioned identity; axes change must change identity_hash; source ids exist.

    Requirement semantics are profile-scoped and honest:
      * `requirement_semantics: UNKNOWN` -> the profile must declare NO exact
        requirement group, so no exact requirement / match / question is emitted
        for it. We stay UNKNOWN instead of guessing a difference.
      * a profile with declared groups must state a non-canonical
        `requirement_group_policy` (broad route_bom -> exact profile is a
        derived candidate and must never be source_encoded).
    """
    # 2. broad route_bom -> exact profile requirement projection is never canonical.
    adapter = _adapter(adapter_contract, "route_bom_profile_requirements")
    if adapter.get("epistemic_status") == "source_encoded":
        raise RelationIndexError(
            "broad route_bom -> exact profile requirement must never be source_encoded"
        )
    allowed_status = set(adapter.get("allowed_epistemic_status") or [])
    if "source_encoded" in allowed_status:
        raise RelationIndexError(
            "route_bom_profile_requirements must not allow source_encoded exact requirements"
        )

    seen_profile_ids: set[str] = set()
    for profile in adapter_contract.get("route_profiles") or []:
        profile_id = profile.get("route_profile_id")
        if not isinstance(profile_id, str) or not profile_id or profile_id in seen_profile_ids:
            raise RelationIndexError(f"route_profile_id must be unique and non-empty: {profile_id!r}")
        seen_profile_ids.add(profile_id)
        # Profile identity is a versioned contract, not optional annotation.
        # Missing fields used to let a hand-edited profile silently acquire a
        # different requirement meaning.
        if (
            not isinstance(profile.get("revision"), int)
            or isinstance(profile.get("revision"), bool)
            or profile["revision"] < 1
        ):
            raise RelationIndexError(f"{profile_id}: revision must be a positive integer")
        if not isinstance(profile.get("requirement_contract_version"), str) or not profile["requirement_contract_version"].strip():
            raise RelationIndexError(f"{profile_id}: requirement_contract_version is required")
        if not isinstance(profile.get("identity_axes"), dict) or not profile["identity_axes"]:
            raise RelationIndexError(f"{profile_id}: identity_axes must be a non-empty mapping")
        computed = route_profile_identity_hash(profile)
        declared = profile.get("identity_hash")
        if not isinstance(declared, str) or not declared:
            raise RelationIndexError(f"{profile_id}: identity_hash is required")
        if declared != computed:
            raise RelationIndexError(
                f"{profile_id}: identity_hash does not match frozen axes; "
                f"axes changed without updating the hash"
            )
        source_items = profile.get("source_route_item_ids")
        capability_items = profile.get("capability_route_item_ids")
        if not isinstance(source_items, list) or not source_items:
            raise RelationIndexError(f"{profile_id}: source_route_item_ids is required")
        if not isinstance(capability_items, list) or not capability_items:
            raise RelationIndexError(f"{profile_id}: capability_route_item_ids is required")
        if any(not isinstance(item, str) or not item for item in source_items):
            raise RelationIndexError(f"{profile_id}: source_route_item_ids must be non-empty strings")
        if any(not isinstance(item, str) or not item for item in capability_items):
            raise RelationIndexError(f"{profile_id}: capability_route_item_ids must be non-empty strings")
        if len(set(source_items)) != len(source_items) or len(set(capability_items)) != len(capability_items):
            raise RelationIndexError(f"{profile_id}: route item ids must be unique")
        for item_id in source_items:
            if item_id not in route_bom_rows:
                raise RelationIndexError(f"{profile_id}: source_route_item_id {item_id} not in route_bom.csv")
        if not set(capability_items) <= set(source_items):
            raise RelationIndexError(f"{profile_id}: capability_route_item_ids must be a subset of source_route_item_ids")
        if "requirement_group_policy" not in profile:
            raise RelationIndexError(
                f"{profile_id}: requirement_group_policy must explicitly be "
                "derived_candidate"
            )
        policy = profile.get("requirement_group_policy")
        if policy != "derived_candidate":
            raise RelationIndexError(
                f"{profile_id}: requirement_group_policy {policy!r} would make the "
                "broad route_bom projection canonical; only derived_candidate is allowed"
            )
        groups = profile.get("requirement_groups") or []
        semantics = profile.get("requirement_semantics")
        if semantics not in {"UNKNOWN", "declared_groups"}:
            raise RelationIndexError(
                f"{profile_id}: requirement_semantics {semantics!r} is not controlled"
            )
        if semantics == "UNKNOWN":
            # 2. UNKNOWN exact semantics: no exact requirement may be declared.
            if groups:
                raise RelationIndexError(
                    f"{profile_id}: requirement_semantics is UNKNOWN but "
                    f"{len(groups)} exact requirement group(s) are declared; an "
                    f"UNKNOWN profile must emit no exact requirements"
                )
            continue
        if not groups:
            raise RelationIndexError(f"{profile_id}: missing requirement_groups (all_of/one_of)")
        # B. groups declare direct capability cells plus the BOM rows that
        # substantiate the declaration.  A row id is not itself a capability
        # cell (RB002's C1/C4/P1/D12 are distinct semantics).
        seen_group_ids: set[str] = set()
        available_cells = {
            cell.strip()
            for item_id in capability_items
            for cell in (route_bom_rows[item_id].get("cell_ids") or "").split(",")
            if cell.strip()
        }
        for group in groups:
            group_id = group.get("group_id")
            if not isinstance(group_id, str) or not group_id or group_id in seen_group_ids:
                raise RelationIndexError(f"{profile_id}: requirement group_id must be unique and non-empty")
            seen_group_ids.add(group_id)
            if group.get("kind") not in ("all_of", "one_of"):
                raise RelationIndexError(
                    f"{profile_id}: requirement group {group_id} has "
                    f"invalid kind {group.get('kind')!r} (expected all_of/one_of)"
                )
            source_group_items = group.get("source_route_item_ids")
            cells = group.get("capability_cell_ids")
            if not isinstance(source_group_items, list) or not source_group_items:
                raise RelationIndexError(f"{profile_id}: requirement group {group_id} needs source_route_item_ids")
            if not isinstance(cells, list) or not cells:
                raise RelationIndexError(
                    f"{profile_id}: requirement group {group_id} is empty"
                )
            if any(not isinstance(item, str) or not item for item in source_group_items):
                raise RelationIndexError(
                    f"{profile_id}: requirement group {group_id} source ids must be non-empty strings"
                )
            if any(not isinstance(cell, str) or not cell for cell in cells):
                raise RelationIndexError(
                    f"{profile_id}: requirement group {group_id} cells must be non-empty strings"
                )
            if len(set(source_group_items)) != len(source_group_items):
                raise RelationIndexError(f"{profile_id}: requirement group {group_id} source ids must be unique")
            if not set(source_group_items) <= set(source_items):
                raise RelationIndexError(f"{profile_id}: requirement group {group_id} references route item outside source_route_item_ids")
            if not set(cells) <= available_cells:
                unknown = sorted(set(cells) - available_cells)
                raise RelationIndexError(f"{profile_id}: requirement group {group_id} references unknown capability cells {unknown}")
            substantiating_cells = {
                cell.strip()
                for item_id in source_group_items
                for cell in (route_bom_rows[item_id].get("cell_ids") or "").split(",")
                if cell.strip()
            }
            if not set(cells) <= substantiating_cells:
                unknown = sorted(set(cells) - substantiating_cells)
                raise RelationIndexError(f"{profile_id}: requirement group {group_id} cells {unknown} are not substantiated by its source route items")


def evaluate_requirement_group(group: dict[str, Any], matched_cell_ids: set[str]) -> bool:
    """B. all_of requires every cell; one_of requires at least one."""
    cells = set(group.get("capability_cell_ids") or [])
    if group.get("kind") == "one_of":
        return bool(cells & matched_cell_ids)
    if group.get("kind") == "all_of":
        return cells and cells.issubset(matched_cell_ids)
    raise RelationIndexError(f"unknown requirement group kind: {group.get('kind')}")


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
        status = row.get("状态") or ""
        # C. point status -> capability modality mapping
        if status in POINT_STATUS_ACTUAL:
            modality = "actual"
        elif status in POINT_STATUS_PLANNED:
            modality = "planned"
        else:
            modality = "unknown"
        source = row.get("锚点URL", "").strip() or f"point:{point_id}"
        result.append(
            make_assertion(
                relation_type="company_has_capability_at",
                subject_ref=f"company:{company}",
                object_ref=f"capability_cell:{cell_id}",
                scope={"capability_cell_id": cell_id},
                valid_time={"start": row.get("判定会话日期") or row.get("检索日期")},
                modality=modality,
                polarity="supporting",
                epistemic_status="source_encoded",
                origin_group=f"points_source:{source}",
                adapter_version=adapter["adapter_version"],
                source_refs=[f"points.csv#{point_id}"],
                assertion_key=[adapter["adapter_version"], point_id],
                metadata={"point_status": status, "actual_capability": modality == "actual"},
                relation_contract=config.get("relation_contract") or load_yaml(ROOT / "contracts/relation_types.yaml"),
            )
        )
    return result


def adapt_route_requirements(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    """B. exact-profile requirements are derived_candidate, NOT canonical source_encoded.

    The required capability cells are taken explicitly from the profile's
    `requirement_groups` (all_of / one_of), not blindly from every
    `capability_route_item_ids` row. A profile whose `requirement_semantics` is
    UNKNOWN emits NO exact requirements (and therefore no matches / questions):
    the ledger cannot prove a difference, so we stay UNKNOWN rather than guess.
    """
    adapter = _adapter(config, "route_bom_profile_requirements")
    rows = {row["route_item_id"]: row for row in load_csv(root / adapter["input"])}
    result = []
    profile_ids: set[str] = set()
    for profile in config.get("route_profiles") or []:
        profile_id = profile.get("route_profile_id")
        if not profile_id or profile_id in profile_ids:
            raise RelationIndexError(f"route_profile_id must be unique: {profile_id!r}")
        profile_ids.add(profile_id)
        if profile.get("requirement_semantics") == "UNKNOWN":
            # B. UNKNOWN exact-semantics profile: emit no exact requirements.
            continue
        policy = profile.get("requirement_group_policy") or "derived_candidate"
        if policy != "derived_candidate":
            raise RelationIndexError(
                f"{profile_id}: broad route_bom -> exact profile requirement must be "
                f"derived_candidate, got {policy!r}"
            )
        # Each declared cell is projected exactly as declared.  In particular,
        # the four cells in RB002 are not expanded into one giant all_of group.
        for group in profile.get("requirement_groups") or []:
            group_id = group["group_id"]
            source_items = group["source_route_item_ids"]
            cells = group["capability_cell_ids"]
            for cell_id in cells:
                substantiating = [
                    rb_id
                    for rb_id in source_items
                    if rb_id in rows
                    if cell_id in {
                        item.strip()
                        for item in (rows[rb_id].get("cell_ids", "").split(","))
                        if item.strip()
                    }
                ]
                if not substantiating:
                    raise RelationIndexError(
                        f"{profile_id}: requirement group {group_id} cell {cell_id} has no source route item"
                    )
                rb_id = substantiating[0]
                row = rows[rb_id]
                result.append(
                    make_assertion(
                        relation_type="route_requires_capability",
                        subject_ref=f"route_profile:{profile_id}",
                        object_ref=f"capability_cell:{cell_id}",
                        scope={
                            "route_profile_id": profile_id,
                            "capability_cell_id": cell_id,
                            "requirement_source_rb_item": rb_id,
                        },
                        valid_time=None,
                        modality="actual",
                        polarity="supporting",
                        epistemic_status=policy,
                        origin_group=f"route_bom:{rb_id}",
                        adapter_version=adapter["adapter_version"],
                        source_refs=[f"route_bom.csv#{rb_id}"],
                        assertion_key=[adapter["adapter_version"], profile_id, group.get("group_id"), rb_id, cell_id],
                        metadata={
                            "mapping_status": row.get("mapping_status") or None,
                            "requirement_group_id": group.get("group_id"),
                            "requirement_group_kind": group.get("kind"),
                            "requirement_contract_version": profile.get("requirement_contract_version"),
                            "requirement_source_route_item_ids": list(source_items),
                            # 2. provenance of the projection, not a canonical fact.
                            "derived_from_broad_route_bom": True,
                        },
                        relation_contract=config.get("relation_contract") or load_yaml(ROOT / "contracts/relation_types.yaml"),
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
                # C. derived match inherits the capability modality (planned for 在建)
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
                        modality=capability["modality"],
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
                        relation_contract=config.get("relation_contract") or load_yaml(ROOT / "contracts/relation_types.yaml"),
                    )
                )
    return result


def adapt_calls(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    adapter = _adapter(config, "calls_product_lifecycle")
    allowed_categories = set(adapter.get("allowed_event_category") or [])
    events = {row["event_id"]: row for row in load_csv(root / "calls/events.csv")}
    claims = {
        row["event_claim_id"]: row for row in load_csv(root / "calls/event_claims.csv")
    }
    evidence_rows = load_csv(root / "calls/event_evidence.csv")
    # One event normally has one projected evidence row.  Keep all IDs rather
    # than letting a dict silently select the last duplicate: a
    # previous_event_id with zero or multiple eligible targets is not a
    # reliable revision chain and must stay unprojected.
    event_assertion_ids: dict[str, list[str]] = defaultdict(list)
    for row in evidence_rows:
        event = events.get(row.get("event_id", ""))
        if (
            event is not None
            and row.get("event_id")
            and row.get("evidence_id")
            and (not allowed_categories or event.get("event_category") in allowed_categories)
        ):
            event_assertion_ids[row["event_id"]].append(
                stable_id("RA", [adapter["adapter_version"], row["evidence_id"]])
            )
    result = []
    for evidence in evidence_rows:
        event = events.get(evidence["event_id"])
        claim = claims.get(evidence["event_claim_id"])
        if event is None or claim is None:
            raise RelationIndexError(f"unresolved calls evidence {evidence.get('evidence_id')}")
        # I. only true product_stage events may enter product_has_lifecycle_stage
        category = event["event_category"]
        if allowed_categories and category not in allowed_categories:
            continue
        modality = "planned" if claim["statement_kind"] == "forward_looking" else "actual"
        relationship = evidence["relationship"]
        revision_kind = None
        effective_at = None
        retroactive = None
        if relationship == "corrects" or event["event_status"] == "corrected":
            # F. corrects cannot be safely implemented in this pilot: refuse it
            # via the actual adapter path rather than silently coercing it to
            # limiting (or hiding it as a contradiction).
            raise RelationIndexError(
                f"{evidence.get('evidence_id')}: revision_kind 'corrects' is not "
                "supported by the calls adapter in this pilot; refused rather "
                "than coerced to another polarity"
            )
        if relationship == "withdraws" or event["event_status"] == "withdrawn":
            polarity = "withdrawn"
            # 7. the revision kind is preserved, never silently downgraded.
            revision_kind = "withdraws"
            effective_at = event.get("occurred_start") or None
            retroactive = False
            previous_targets = event_assertion_ids.get(event.get("previous_event_id", ""), [])
            if len(previous_targets) != 1:
                # F. A calls previous_event_id can point at a filtered,
                # missing, or ambiguous event.  Do not invent a revision target
                # or coerce the row into a limiting assertion; leave this event
                # unprojected for manual handling.
                continue
        elif relationship == "contradicts" or event["event_status"] == "contradicted":
            polarity = "contradicting"
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
                    "lifecycle_stage": stage,
                },
                # A product-stage event records when the program reached the
                # stage; it is not a point-in-time fact that expires at the
                # end of the event row.  Keep the reached stage active from
                # occurred_start onward.  Revisions still carry their own
                # effective_at and are applied by the temporal reducer.
                valid_time={
                    "start": event["occurred_start"] or None,
                    "end": None,
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
                revises_assertion_ids=(
                    previous_targets
                    if polarity == "withdrawn"
                    else []
                ),
                revision_kind=revision_kind,
                effective_at=effective_at,
                retroactive=retroactive,
                metadata={
                    "event_status": event["event_status"],
                    "statement_kind": claim["statement_kind"],
                    "event_category": category,
                    # F. calls/events.csv.previous_event_id cannot be reliably
                    # adapted into a revision chain; it stays unprojected rather
                    # than being invented.
                    "previous_event_id_unprojected": bool(event.get("previous_event_id")),
                },
                relation_contract=config.get("relation_contract") or load_yaml(ROOT / "contracts/relation_types.yaml"),
            )
        )
    return result


def validate_explicit_reviewed(
    item: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    relation_contract: dict[str, Any],
    receipt_registry: dict[str, dict[str, Any]] | None = None,
) -> None:
    """A. reviewed assertion write gate. Empty/unresolvable refs can never close.

    References are validated by KIND (a source ref cannot stand in for an
    evidence claim) and by SEMANTIC LINKAGE (the evidence must belong to the
    same company named in the assertion's subject_ref). The review receipt must
    resolve in the safe receipt registry and its reviewer must match.
    """
    assertion_id = item.get("assertion_id")
    receipt_registry = receipt_registry or {}
    relation_type = item.get("relation_type")
    relation_definition = (relation_contract.get("relation_types") or {}).get(
        relation_type
    )
    if not isinstance(relation_definition, dict):
        raise RelationIndexError(
            f"{assertion_id}: reviewed assertion has unknown relation_type {relation_type!r}"
        )
    subject_ref = item.get("subject_ref")
    if not isinstance(subject_ref, str) or not subject_ref:
        raise RelationIndexError(f"{assertion_id}: reviewed assertion needs a subject_ref")
    if relation_type == "company_serves_route" and not subject_ref.startswith("company:"):
        raise RelationIndexError(
            f"{assertion_id}: company_serves_route subject must use canonical company:<name> identity"
        )
    if not isinstance(item.get("object_ref"), str) or not item["object_ref"]:
        raise RelationIndexError(f"{assertion_id}: reviewed assertion needs an object_ref")
    if not isinstance(item.get("scope"), dict):
        raise RelationIndexError(f"{assertion_id}: reviewed assertion scope must be a mapping")

    # A. review receipt must resolve in the safe receipt registry (no fake receipt).
    receipt_id = item.get("review_receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id.strip():
        raise RelationIndexError(f"{assertion_id}: review_receipt_id is required")
    receipt = receipt_registry.get(receipt_id)
    if receipt is None:
        raise RelationIndexError(f"{assertion_id}: review_receipt_id {receipt_id!r} does not resolve in the receipt registry")
    if not receipt.get("reviewer") or not receipt.get("subject_ref"):
        raise RelationIndexError(f"{assertion_id}: registered receipt {receipt_id!r} is incomplete")
    if relation_type == "company_serves_route" and not str(receipt["subject_ref"]).startswith("company:"):
        raise RelationIndexError(
            f"{assertion_id}: registered receipt {receipt_id!r} has a non-canonical company subject"
        )
    if not item.get("reviewer") or item.get("reviewer") != receipt.get("reviewer"):
        raise RelationIndexError(
            f"{assertion_id}: reviewer {item.get('reviewer')!r} does not match the "
            f"registered reviewer for receipt {receipt_id!r}"
        )
    # A. semantic linkage: the receipt is issued for the reviewed company.
    if subject_ref != receipt["subject_ref"]:
        raise RelationIndexError(
            f"{assertion_id}: assertion subject {subject_ref!r} does not match the "
            f"receipt's reviewed company {receipt['subject_ref']!r}"
        )
    receipt_kind = item.get("review_receipt_kind")
    if not isinstance(receipt_kind, str) or not receipt_kind:
        raise RelationIndexError(f"{assertion_id}: review_receipt_kind is required")
    if not isinstance(receipt.get("receipt_kind"), str) or not receipt["receipt_kind"]:
        raise RelationIndexError(
            f"{assertion_id}: registered receipt {receipt_id!r} has no receipt_kind"
        )
    if receipt_kind != receipt["receipt_kind"]:
        raise RelationIndexError(
            f"{assertion_id}: review_receipt_kind {receipt_kind!r} does not match "
            f"registered receipt kind {receipt['receipt_kind']!r}"
        )

    # A. strict ISO reviewed_at
    value = item.get("reviewed_at")
    if not value:
        raise RelationIndexError(f"{assertion_id}: reviewed_at is required")
    parse_iso_datetime(value)  # raises on non-ISO

    kinds = set(
        (relation_contract.get("assertion_contract") or {}).get(
            "evidence_claim_ref_kinds"
        )
        or EVIDENCE_REF_KINDS
    )

    # A. source_refs: non-empty, every ref resolves, kind must be a citation kind.
    source_refs = item.get("source_refs") or []
    if not source_refs:
        raise RelationIndexError(f"{assertion_id}: source_refs must be non-empty")
    if not isinstance(source_refs, list) or any(not isinstance(ref, str) or not ref for ref in source_refs):
        raise RelationIndexError(f"{assertion_id}: source_refs must be a non-empty list of strings")
    if len(source_refs) != len(set(source_refs)):
        raise RelationIndexError(f"{assertion_id}: source_refs must not contain duplicates")
    for ref in source_refs:
        entry = registry.get(ref)
        if entry is None:
            raise RelationIndexError(f"{assertion_id}: source_ref {ref!r} does not resolve")
        if entry.get("kind") not in SOURCE_REF_KINDS:
            raise RelationIndexError(f"{assertion_id}: source_ref {ref!r} has unexpected kind {entry.get('kind')!r}")
        if entry.get("company") != subject_ref:
            raise RelationIndexError(
                f"{assertion_id}: source_ref {ref!r} belongs to {entry.get('company')!r}, "
                f"not the assertion subject {subject_ref!r}"
            )

    # A. evidence_claim_refs: non-empty, claim/disclosure/event kind only (NOT a
    # bare source ref), and provably related to the assertion subject.
    evidence_refs = item.get("evidence_claim_refs") or []
    if not isinstance(evidence_refs, list) or any(not isinstance(ref, str) or not ref for ref in evidence_refs):
        raise RelationIndexError(f"{assertion_id}: evidence_claim_refs must be non-empty")
    if len(evidence_refs) != len(set(evidence_refs)):
        raise RelationIndexError(
            f"{assertion_id}: evidence_claim_refs must not contain duplicates"
        )
    evidence_entries: dict[str, dict[str, Any]] = {}
    for ref in evidence_refs:
        entry = registry.get(ref)
        if entry is None:
            raise RelationIndexError(f"{assertion_id}: evidence_claim_ref {ref!r} does not resolve")
        if entry.get("kind") not in kinds:
            raise RelationIndexError(
                f"{assertion_id}: evidence_claim_ref {ref!r} has kind {entry.get('kind')!r}; "
                f"expected one of {sorted(kinds)} - a source ref cannot stand in for "
                f"an evidence claim"
            )
        # 1. semantic linkage: evidence about another company is unrelated to the
        # subject and must not be allowed to close the question.
        linked = entry.get("company")
        if linked != subject_ref:
            raise RelationIndexError(
                f"{assertion_id}: evidence {ref!r} belongs to {linked!r}, "
                f"not the assertion subject {subject_ref!r} (semantically unrelated)"
            )
        evidence_entries[ref] = entry

    def linked(source_ref: str, source_entry: dict[str, Any], evidence_ref: str, evidence_entry: dict[str, Any]) -> bool:
        """Require a real ledger edge between each citation and evidence.

        Same-company is necessary but not sufficient: without this check a
        Lumentum claim plus an unrelated Coherent (or unrelated Lumentum) source
        could be presented as one review.  The real CSV adapter supplies links
        through source_id/legacy_source_id/disclosure/event evidence; fixture
        registries carry the same links explicitly.
        """
        if source_ref == evidence_ref:
            return True
        source_links = set(source_entry.get("linked_refs") or [])
        evidence_links = set(evidence_entry.get("linked_refs") or [])
        if evidence_ref in source_links or source_ref in evidence_links:
            return True
        # A source and an evidence claim can be joined through the same
        # disclosure/event anchor without having a direct edge in the normalized
        # registry (for example source:S -> disclosure:D and event-claim:E ->
        # disclosure:D).  A common, real ledger link is sufficient; arbitrary
        # same-company refs still fail because they have no shared anchor.
        if source_links & evidence_links:
            return True
        # Be tolerant of callers passing a registry built by an older adapter:
        # use the normalized source/disclosure identifiers as a direct edge.
        if source_entry.get("source_id") and evidence_entry.get("source_id"):
            if source_entry["source_id"] == evidence_entry["source_id"]:
                return True
        if source_entry.get("disclosure_id") and evidence_entry.get("disclosure_id"):
            if source_entry["disclosure_id"] == evidence_entry["disclosure_id"]:
                return True
        return False

    for source_ref in source_refs:
        source_entry = registry[source_ref]
        if not any(linked(source_ref, source_entry, ref, evidence_entries[ref]) for ref in evidence_refs):
            raise RelationIndexError(
                f"{assertion_id}: source_ref {source_ref!r} has no linked evidence_claim_ref; "
                f"source/evidence association is unverified"
            )
    for evidence_ref, evidence_entry in evidence_entries.items():
        if not any(linked(source_ref, registry[source_ref], evidence_ref, evidence_entry) for source_ref in source_refs):
            raise RelationIndexError(
                f"{assertion_id}: evidence_claim_ref {evidence_ref!r} has no linked source_ref"
            )

    # A. supports / does_not_support: both lists, at least one entry, and every
    # entry must be one of the cited evidence refs (no free-text verdicts).
    supports = item.get("supports")
    does_not_support = item.get("does_not_support")
    if not isinstance(supports, list) or not isinstance(does_not_support, list):
        raise RelationIndexError(f"{assertion_id}: supports and does_not_support must both be lists")
    if not supports and not does_not_support:
        raise RelationIndexError(f"{assertion_id}: supports and does_not_support cannot both be empty")
    if item.get("polarity") == "supporting" and not supports:
        raise RelationIndexError(f"{assertion_id}: a supporting reviewed assertion needs non-empty supports")
    if item.get("polarity") in {"limiting", "contradicting"} and not does_not_support:
        raise RelationIndexError(
            f"{assertion_id}: a non-supporting reviewed assertion needs non-empty does_not_support"
        )
    cited = set(evidence_refs)
    for label, values in (("supports", supports), ("does_not_support", does_not_support)):
        for ref in values:
            if not isinstance(ref, str) or not ref:
                raise RelationIndexError(f"{assertion_id}: {label} contains an empty entry")
            if ref not in cited:
                raise RelationIndexError(
                    f"{assertion_id}: {label} entry {ref!r} is not one of the cited "
                    f"evidence_claim_refs"
                )
    overlap = set(supports) & set(does_not_support)
    if overlap:
        raise RelationIndexError(
            f"{assertion_id}: {sorted(overlap)} appear in both supports and does_not_support"
        )

    # A. origin_group must not be an arbitrary hand-filled independence basis:
    # it must be consistent with the canonical origin derived from resolved sources.
    origin_group = item.get("origin_group")
    if not isinstance(origin_group, str) or not origin_group:
        raise RelationIndexError(f"{assertion_id}: origin_group is required")
    if origin_group:
        derived_origins = derive_origin_groups(item.get("source_refs") or [], registry)
        if len(derived_origins) > 1:
            raise RelationIndexError(
                f"{assertion_id}: source_refs span multiple canonical origins "
                f"{sorted(derived_origins)}"
            )
        derived = next(iter(derived_origins), None)
        if derived and origin_group != derived:
            raise RelationIndexError(
                f"{assertion_id}: origin_group {origin_group!r} is inconsistent "
                f"with derived canonical origin {derived!r}"
            )

    # G. company_serves_route identity scope must force exact product + service_kind
    if item.get("relation_type") == "company_serves_route":
        scope = item.get("scope") or {}
        route_profile_id = scope.get("route_profile_id")
        if not isinstance(route_profile_id, str) or not route_profile_id:
            raise RelationIndexError(
                f"{assertion_id}: company_serves_route requires route_profile_id"
            )
        if item.get("object_ref") != f"route_profile:{route_profile_id}":
            raise RelationIndexError(
                f"{assertion_id}: route profile object_ref does not match route_profile_id"
            )
        product_ref = scope.get("product_ref")
        service_kind = scope.get("service_kind")
        if not isinstance(product_ref, str) or not product_ref.startswith("product:"):
            raise RelationIndexError(f"{assertion_id}: company_serves_route requires exact product_ref")
        product = registry.get(product_ref)
        if not product or product.get("kind") != "product":
            raise RelationIndexError(
                f"{assertion_id}: product_ref {product_ref!r} does not resolve to a registered product"
            )
        if product.get("company") != subject_ref:
            raise RelationIndexError(
                f"{assertion_id}: product_ref {product_ref!r} belongs to {product.get('company')!r}, "
                f"not subject {subject_ref!r}"
            )
        if not product.get("registry_id"):
            raise RelationIndexError(
                f"{assertion_id}: product_ref {product_ref!r} is not bound to a validated product registry"
            )
        product_source_refs = product.get("source_refs") or []
        if not product_source_refs or any(
            not registry.get(product_source)
            or registry[product_source].get("kind") not in SOURCE_REF_KINDS
            or registry[product_source].get("company") != subject_ref
            for product_source in product_source_refs
        ):
            raise RelationIndexError(
                f"{assertion_id}: product_ref {product_ref!r} lacks resolvable "
                "same-company product evidence"
            )
        if service_kind not in SERVICE_KIND_ENUM:
            raise RelationIndexError(
                f"{assertion_id}: service_kind {service_kind!r} not in controlled enum"
            )


def adapt_explicit_assertions(
    path: Path,
    config: dict[str, Any],
    known_profile_ids: set[str],
    registry: dict[str, dict[str, Any]],
    relation_contract: dict[str, Any],
    receipt_registry: dict[str, dict[str, Any]] | None = None,
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
        if not isinstance(item.get("scope"), dict):
            raise RelationIndexError(f"explicit assertion {index} scope must be a mapping")
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
        # F. reject unsupported/ill-formed revision metadata through the actual
        # adapter path, before any assertion can reach the reducer.
        revision_kind = item.get("revision_kind")
        revises_assertion_ids = _validate_revision_fields(item, relation_contract)
        validate_explicit_reviewed(item, registry, relation_contract, receipt_registry)
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
                revises_assertion_ids=revises_assertion_ids,
                metadata=item.get("metadata"),
                relation_contract=relation_contract,
                # A. preserve the full reviewed-write-gate provenance on the index.
                review_receipt_id=item.get("review_receipt_id"),
                review_receipt_kind=item.get("review_receipt_kind"),
                reviewer=item.get("reviewer"),
                reviewed_at=item.get("reviewed_at"),
                evidence_claim_refs=item.get("evidence_claim_refs"),
                supports=item.get("supports"),
                does_not_support=item.get("does_not_support"),
                # F. preserve revision provenance on the index.
                revision_kind=revision_kind,
                effective_at=item.get("effective_at"),
                retroactive=item.get("retroactive"),
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


def is_active_at_as_of(assertion: dict[str, Any], as_of: str | None) -> bool:
    """E. time filtering for an as_of query. Unknown time is always active.

    E/6. a revision (withdrawal / supersession / correction) additionally carries
    `effective_at`. A revision that is not yet effective at the query instant
    cannot change the state: a 2027 withdrawal or superseder must not remove or
    replace a 2026 assertion. The pilot retains `retroactive` as provenance but
    deliberately does not perform bitemporal historical writeback.
    """
    if as_of is None:
        return True
    as_of = parse_iso_datetime(as_of)
    vt = assertion.get("valid_time") or {}
    start, end = vt.get("start"), vt.get("end")
    if start is None and end is None:
        pass  # unknown time: always active at any as_of
    elif start and start > as_of:
        return False
    elif end and end < as_of:
        return False
    if assertion.get("revision_kind") in {"withdraws", "supersedes", "corrects"}:
        effective_at = assertion.get("effective_at")
        if effective_at and parse_iso_datetime(effective_at) > as_of:
            return False
    return True


def assertions_conflict(
    left: dict[str, Any],
    right: dict[str, Any],
    relation_contract: dict[str, Any] | None = None,
) -> bool:
    """8. conflicts are decided on the contract-declared comparison surface.

    The comparison fields always include the slot identity fields, so a wider
    context can never be compared more loosely than the identity allows.
    """
    if left["slot_id"] != right["slot_id"]:
        return False
    if relation_contract is not None:
        left_surface = comparison_values(left, relation_contract)
        right_surface = comparison_values(right, relation_contract)
        left_surface.pop("modality", None)
        right_surface.pop("modality", None)
        if left_surface != right_surface:
            return False
        if left.get("modality") != right.get("modality"):
            return False
    elif left["modality"] != right["modality"]:
        return False
    return _time_overlap(left["valid_time"], right["valid_time"]) and {
        left["polarity"],
        right["polarity"],
    } == {"supporting", "contradicting"}


def _same_comparison_surface(
    left: dict[str, Any],
    right: dict[str, Any],
    relation_contract: dict[str, Any] | None,
) -> bool:
    """Return whether two assertions can affect one another.

    A revision or contradiction must agree on the complete relation identity
    and comparison surface.  With the production contract this includes
    declared context such as geography/customer/program and modality; the
    legacy no-contract path retains the historical slot-id + modality rule.
    """
    if (
        left.get("relation_type") != right.get("relation_type")
        or left.get("subject_ref") != right.get("subject_ref")
        or left.get("object_ref") != right.get("object_ref")
    ):
        return False
    if relation_contract is None:
        return (
            left.get("slot_id") == right.get("slot_id")
            and left.get("modality") == right.get("modality")
        )
    left_identity = relation_slot_identity(
        left["relation_type"],
        left["subject_ref"],
        left["object_ref"],
        left.get("scope") or {},
        relation_contract,
    )
    right_identity = relation_slot_identity(
        right["relation_type"],
        right["subject_ref"],
        right["object_ref"],
        right.get("scope") or {},
        relation_contract,
    )
    return (
        left_identity == right_identity
        and comparison_values(left, relation_contract)
        == comparison_values(right, relation_contract)
    )


def compute_slot_states(
    assertions: list[dict[str, Any]],
    as_of: str | None = None,
    modality: str | None = None,
    relation_contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """E. compute slot states at a strict `as_of` query time and optional query
    `modality`.

    Withdrawals and supersessions affect an assertion only when both revision
    and target are active at `as_of`, on the same relation/identity/comparison
    surface and modality.  A superseder remains in the active state with its
    own polarity; only its ``revises_assertion_ids`` are retired.  The pilot
    keeps ``retroactive`` as provenance but does not perform historical
    bitemporal writeback.
    """
    if as_of is not None:
        as_of = parse_iso_datetime(as_of)
    if modality is not None and modality not in {"actual", "planned", "conditional", "unknown"}:
        raise RelationIndexError(f"invalid query modality: {modality!r}")
    by_slot: dict[str, list[dict[str, Any]]] = defaultdict(list)
    known_ids = {item["assertion_id"] for item in assertions}
    for item in assertions:
        # Projected assertions normally carry slot_id.  Deriving it here as a
        # fallback keeps this reducer safe for raw test inputs while retaining
        # the same identity contract used by scan.py.
        slot_id = (
            _computed_slot_id(item, relation_contract)[0]
            if relation_contract is not None
            else item.get("slot_id")
        )
        if not slot_id:
            raise RelationIndexError(f"{item.get('assertion_id')}: slot_id is required")
        by_slot[slot_id].append(item)

    def passes_modality(item: dict[str, Any]) -> bool:
        return modality is None or item["modality"] == modality

    result = []
    for slot_id in sorted(by_slot):
        items = sorted(by_slot[slot_id], key=lambda item: item["assertion_id"])
        # E/6. filter FIRST, then apply effects: withdrawals, limits and
        # contradictions are all subject to the same as_of + modality policy as
        # the support they would act on. Nothing that is inactive at the query
        # instant (e.g. a 2027 withdrawal) may change the 2026 state.
        active_by_id = {
            item["assertion_id"]: item
            for item in items
            if item["polarity"] != "withdrawn"
            and passes_modality(item)
            and is_active_at_as_of(item, as_of)
        }
        active_withdrawals = [
            item
            for item in items
            if item["polarity"] == "withdrawn"
            and passes_modality(item)
            and is_active_at_as_of(item, as_of)
        ]
        active_superseders = [
            item
            for item in items
            if item["polarity"] != "withdrawn"
            and item.get("revision_kind") == "supersedes"
            and item["assertion_id"] in active_by_id
        ]
        withdrawn_ids: set[str] = set()
        for item in active_withdrawals:
            for target in item.get("revises_assertion_ids") or []:
                if target in known_ids and target in active_by_id:
                    # With modality=None the comparison surface is otherwise
                    # mixed.  A planned withdrawal must never silently remove
                    # actual support; explicit modality queries already filter
                    # both sides to the same surface.
                    if not _same_comparison_surface(
                        item, active_by_id[target], relation_contract
                    ):
                        continue
                    withdrawn_ids.add(target)

        # A superseder is a real assertion, not a withdrawal row.  Once its
        # effective_at is reached, retire only compatible targets while keeping
        # the superseder itself in the active set.  Applying withdrawals first
        # prevents a withdrawn superseder from still retiring its predecessor.
        superseded_ids: set[str] = set()
        for item in active_superseders:
            if item["assertion_id"] in withdrawn_ids:
                continue
            for target in item.get("revises_assertion_ids") or []:
                if target in active_by_id and target not in withdrawn_ids:
                    if not _same_comparison_surface(
                        item, active_by_id[target], relation_contract
                    ):
                        continue
                    superseded_ids.add(target)

        active = [
            active_by_id[i]
            for i in sorted(active_by_id)
            if i not in withdrawn_ids and i not in superseded_ids
        ]
        supports = [item for item in active if item["polarity"] == "supporting"]
        limits = [item for item in active if item["polarity"] == "limiting"]
        contradicts = [item for item in active if item["polarity"] == "contradicting"]
        # Context fields such as geography/customer are deliberately excluded
        # from slot identity, but they remain on the comparison surface.  A
        # limiting assertion in EU must not limit a US support assertion merely
        # because both belong to the same aggregate slot.
        comparable_limits = (
            [
                item
                for item in limits
                if any(
                    _same_comparison_surface(item, support, relation_contract)
                    for support in supports
                )
            ]
            if relation_contract is not None and supports
            else limits
        )
        if relation_contract is not None and supports:
            comparable_contradicts = [
                item
                for item in contradicts
                if any(
                    _same_comparison_surface(item, support, relation_contract)
                    for support in supports
                )
            ]
            non_comparable_contradicts = [
                item for item in contradicts if item not in comparable_contradicts
            ]
        else:
            # Without a support there is no narrower comparison surface to
            # anchor.  Preserve the historical contradicted state and expose
            # no non-comparable subset; once a support exists, the branch above
            # makes context/modal mismatch auditable and non-blocking.
            comparable_contradicts = contradicts
            non_comparable_contradicts = []
        conflict_pairs = sorted(
            [left["assertion_id"], right["assertion_id"]]
            for left in supports
            for right in comparable_contradicts
            if assertions_conflict(left, right, relation_contract)
        )
        if conflict_pairs:
            effective_status = "conflicted"
        elif supports and comparable_limits:
            effective_status = "limited"
        elif supports:
            effective_status = "supported"
        elif comparable_contradicts:
            effective_status = "contradicted"
        elif limits:
            effective_status = "limited"
        elif withdrawn_ids:
            effective_status = "withdrawn"
        elif superseded_ids:
            effective_status = "superseded"
        else:
            effective_status = "unknown"

        identity = relation_slot_identity(
            items[0]["relation_type"],
            items[0]["subject_ref"],
            items[0]["object_ref"],
            items[0]["scope"],
            relation_contract or {},
        )
        # 8. identity scope vs assertion context are exposed on the slot too.
        definition = (relation_contract or {}).get("relation_types", {}).get(
            items[0]["relation_type"]
        ) or {}
        id_fields = definition.get("slot_identity_fields") or ["subject_ref", "object_ref"]
        scope = items[0].get("scope") or {}
        result.append(
            {
                "slot_id": slot_id,
                **slot_identity(
                    items[0]["relation_type"],
                    items[0]["subject_ref"],
                    items[0]["object_ref"],
                    items[0]["scope"],
                ),
                "identity_scope": {f: scope.get(f) for f in id_fields if f in scope},
                "assertion_context": {
                    k: v for k, v in scope.items() if k not in id_fields
                },
                "effective_status": effective_status,
                "assertion_ids": [item["assertion_id"] for item in items],
                "active_assertion_ids": [item["assertion_id"] for item in active],
                "supporting_assertion_ids": [item["assertion_id"] for item in supports],
                "limiting_assertion_ids": [
                    item["assertion_id"] for item in comparable_limits
                ],
                "contradicting_assertion_ids": [
                    item["assertion_id"] for item in comparable_contradicts
                ],
                "non_comparable_contradicting_assertion_ids": [
                    item["assertion_id"] for item in non_comparable_contradicts
                ],
                "withdrawal_assertion_ids": [
                    item["assertion_id"] for item in active_withdrawals
                ],
                "withdrawn_assertion_ids": sorted(withdrawn_ids),
                "superseded_assertion_ids": sorted(superseded_ids),
                "conflict_pairs": conflict_pairs,
                # A/F. independent evidence counted by derived canonical origin, not
                # by a hand-filled origin_group.
                "independent_origin_counts": {
                    polarity: _independent_origin_count(
                        [
                            item
                            for item in (
                                supports
                                if polarity == "supporting"
                                else comparable_limits
                                if polarity == "limiting"
                                else comparable_contradicts
                            )
                        ],
                        relation_contract,
                    )
                    for polarity in ("supporting", "limiting", "contradicting")
                },
            }
        )
    return result


def _independent_origin_count(
    items: list[dict[str, Any]], relation_contract: dict[str, Any] | None
) -> int:
    origins: set[str] = set()
    for item in items:
        # prefer the derived canonical origin; fall back to the declared group
        derived = item.get("derived_origin_group")
        origins.add(derived or item["origin_group"])
    return len(origins)


def _computed_slot_id(
    item: dict[str, Any], relation_contract: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Compute a slot identity from raw assertion fields.

    Validators are also used directly by ``scan.py`` on the source sidecar,
    before the projection has added ``slot_id``.  Requiring the generated field
    here made every valid raw withdrawal fail; computing it from the declared
    identity fields keeps the raw and projected paths on one contract.
    """
    relation_type = item.get("relation_type")
    subject_ref = item.get("subject_ref")
    object_ref = item.get("object_ref")
    scope = item.get("scope")
    if not isinstance(relation_type, str) or not relation_type:
        raise RelationIndexError(f"{item.get('assertion_id')}: relation_type is required")
    if not isinstance(subject_ref, str) or not subject_ref:
        raise RelationIndexError(f"{item.get('assertion_id')}: subject_ref is required")
    if not isinstance(object_ref, str) or not object_ref:
        raise RelationIndexError(f"{item.get('assertion_id')}: object_ref is required")
    if not isinstance(scope, dict):
        raise RelationIndexError(f"{item.get('assertion_id')}: scope must be a mapping")
    definition = (relation_contract.get("relation_types") or {}).get(relation_type)
    if not isinstance(definition, dict):
        raise RelationIndexError(f"{item.get('assertion_id')}: unknown relation type {relation_type!r}")
    allowed_scope_fields = set(definition.get("slot_identity_fields") or ()) | set(
        definition.get("context_fields") or ()
    )
    unknown_scope_fields = sorted(set(scope) - allowed_scope_fields)
    if unknown_scope_fields:
        raise RelationIndexError(
            f"{item.get('assertion_id')}: scope contains fields not declared by "
            f"{relation_type} contract: {unknown_scope_fields}"
        )
    if relation_type == "product_has_lifecycle_stage":
        lifecycle_stage = scope.get("lifecycle_stage")
        if object_ref != f"lifecycle_stage:{lifecycle_stage}":
            raise RelationIndexError(
                f"{item.get('assertion_id')}: lifecycle object_ref and lifecycle_stage "
                "must identify the same exact stage"
            )
        program_id = scope.get("program_id")
        if subject_ref != f"product_or_program:{program_id}":
            raise RelationIndexError(
                f"{item.get('assertion_id')}: lifecycle subject_ref and program_id "
                "must identify the same exact program"
            )
    for field in definition.get("slot_identity_fields") or ("subject_ref", "object_ref"):
        if field in ("subject_ref", "object_ref"):
            value = subject_ref if field == "subject_ref" else object_ref
        else:
            value = scope.get(field)
        if value in (None, ""):
            raise RelationIndexError(
                f"{item.get('assertion_id')}: slot identity field {field!r} is missing"
            )
    identity = relation_slot_identity(
        relation_type, subject_ref, object_ref, scope, relation_contract
    )
    computed = stable_id("RS", identity)
    declared = item.get("slot_id")
    if declared is not None and declared != computed:
        raise RelationIndexError(
            f"{item.get('assertion_id')}: slot_id {declared!r} does not match "
            f"the declared identity {computed!r}"
        )
    return computed, identity


def _validate_revision_fields(item: dict[str, Any], relation_contract: dict[str, Any]) -> list[str]:
    """F/7. Strictly validate revision enum and provenance fields."""
    contract = relation_contract.get("assertion_contract") or {}
    allowed = set(contract.get("revision_kind_enum") or REVISION_KIND_ENUM)
    unsupported = set(contract.get("unsupported_revision_kinds") or UNSUPPORTED_REVISION_KINDS)
    if not allowed <= REVISION_KIND_ENUM:
        raise RelationIndexError(
            f"{item.get('assertion_id')}: relation contract exposes unsupported "
            f"revision kinds {sorted(allowed - REVISION_KIND_ENUM)}"
        )
    if not unsupported <= allowed:
        raise RelationIndexError(
            f"{item.get('assertion_id')}: unsupported revision kinds must be in the "
            "revision_kind enum"
        )
    revision_kind = item.get("revision_kind")
    revises = item.get("revises_assertion_ids")
    legacy_revises = item.get("withdraws_assertion_ids")
    if revises is None and legacy_revises is not None:
        revises = legacy_revises
    if revises is None:
        revises = []
    if not isinstance(revises, list) or any(not isinstance(value, str) or not value for value in revises):
        raise RelationIndexError(f"{item.get('assertion_id')}: revises_assertion_ids must be a list of ids")
    if len(revises) != len(set(revises)):
        raise RelationIndexError(
            f"{item.get('assertion_id')}: revises_assertion_ids must not contain duplicates"
        )
    if revises and legacy_revises is not None and set(revises) != set(legacy_revises):
        raise RelationIndexError(f"{item.get('assertion_id')}: revision target aliases disagree")
    has_revision_fields = revision_kind is not None or bool(revises) or "effective_at" in item or "retroactive" in item
    if not has_revision_fields:
        return list(revises)
    if not isinstance(revision_kind, str) or revision_kind not in allowed:
        raise RelationIndexError(
            f"{item.get('assertion_id')}: revision_kind {revision_kind!r} is not in the controlled enum"
        )
    if revision_kind in unsupported:
        raise RelationIndexError(
            f"{item.get('assertion_id')}: revision_kind {revision_kind!r} is unsupported; "
            f"refused rather than coerced to limiting"
        )
    if not revises:
        raise RelationIndexError(
            f"{item.get('assertion_id')}: {revision_kind} requires revises_assertion_ids"
        )
    effective_at = item.get("effective_at")
    if not effective_at:
        raise RelationIndexError(f"{item.get('assertion_id')}: revision requires effective_at")
    parse_iso_datetime(effective_at)
    if not isinstance(item.get("retroactive"), bool):
        raise RelationIndexError(
            f"{item.get('assertion_id')}: revision requires boolean retroactive"
        )
    if item.get("polarity") == "withdrawn" and revision_kind not in {"withdraws", "supersedes"}:
        raise RelationIndexError(
            f"{item.get('assertion_id')}: withdrawn polarity requires withdraws/supersedes revision_kind"
        )
    if item.get("polarity") != "withdrawn" and revision_kind == "withdraws":
        raise RelationIndexError(
            f"{item.get('assertion_id')}: withdraws revision_kind requires withdrawn polarity"
        )
    return list(revises)


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
        if item["epistemic_status"] == "explicit_reviewed":
            gate_fields = set(assertion_contract.get("reviewed_write_gate_fields") or [])
            missing_gate = sorted(gate_fields - set(item))
            if missing_gate:
                raise RelationIndexError(
                    f"{item['assertion_id']}: explicit_reviewed missing gate fields {missing_gate}"
                )
        if not item["origin_group"] or not isinstance(item["source_refs"], list):
            raise RelationIndexError(f"{item['assertion_id']}: provenance is incomplete")
        _computed_slot_id(item, relation_contract)
        expected_identity = relation_slot_identity(
            item["relation_type"],
            item["subject_ref"],
            item["object_ref"],
            item["scope"],
            relation_contract,
        )
        if item.get("identity_scope") is not None:
            definition_fields = definition.get("slot_identity_fields") or ["subject_ref", "object_ref"]
            expected_scope = {
                field: item["scope"][field]
                for field in definition_fields
                if field not in ("subject_ref", "object_ref") and field in item["scope"]
            }
            if item["identity_scope"] != expected_scope:
                raise RelationIndexError(f"{item['assertion_id']}: identity_scope does not match contract identity")
        if item.get("assertion_context") is not None:
            id_fields = set(definition.get("slot_identity_fields") or [])
            expected_context = {key: value for key, value in item["scope"].items() if key not in id_fields}
            if item["assertion_context"] != expected_context:
                raise RelationIndexError(f"{item['assertion_id']}: assertion_context does not match scope")
        if item.get("slot_id") != stable_id("RS", expected_identity):
            raise RelationIndexError(f"{item['assertion_id']}: slot_id is not derived from relation identity")
        _validate_revision_fields(item, relation_contract)


def validate_withdrawals(
    assertions: list[dict[str, Any]], relation_contract: dict[str, Any]
) -> None:
    """F. withdrawal / revision integrity.

    9. the raw YAML sidecar (as read by scan.py) does not carry projected fields
    such as `slot_id`. Compute identity from raw subject/relation/object/scope,
    then validate it against any supplied projected value. Missing projections
    are therefore valid input, while malformed identities still fail with a
    diagnosable RelationIndexError rather than a KeyError.
    """
    unsupported = set(
        (relation_contract.get("assertion_contract") or {}).get(
            "unsupported_revision_kinds"
        )
        or ["corrects"]
    )
    by_id: dict[str, dict[str, Any]] = {}
    computed_ids: dict[str, str] = {}
    for index, item in enumerate(assertions, start=1):
        if not isinstance(item, dict):
            raise RelationIndexError(f"withdrawal check: assertion {index} must be a mapping")
        assertion_id = item.get("assertion_id") or f"assertion {index}"
        if assertion_id in by_id:
            raise RelationIndexError(f"duplicate assertion_id in withdrawal check: {assertion_id}")
        by_id[assertion_id] = item
        computed_ids[assertion_id], _ = _computed_slot_id(item, relation_contract)
    for index, item in enumerate(assertions, start=1):
        if not isinstance(item, dict):
            raise RelationIndexError(f"withdrawal check: assertion {index} must be a mapping")
        assertion_id = item.get("assertion_id") or f"assertion {index}"
        polarity = item.get("polarity")
        if polarity is None:
            raise RelationIndexError(f"{assertion_id}: missing polarity")
        revises = _validate_revision_fields(item, relation_contract)
        if polarity != "withdrawn" and not revises:
            continue
        if polarity == "withdrawn" and not revises:
            raise RelationIndexError(f"{assertion_id}: withdrawn polarity requires revises_assertion_ids")
        for target in revises:
            if target == assertion_id:
                raise RelationIndexError(
                    f"{assertion_id}: a revision cannot target itself"
                )
            target_assertion = by_id.get(target)
            if target_assertion is None:
                raise RelationIndexError(
                    f"{assertion_id}: withdrawal targets unknown assertion {target!r}"
                )
            if target_assertion.get("polarity") == "withdrawn":
                raise RelationIndexError(
                    f"{assertion_id}: a revision cannot target another withdrawn assertion "
                    f"{target!r}"
                )
            if computed_ids[target] != computed_ids[assertion_id]:
                raise RelationIndexError(
                    f"{assertion_id}: withdrawal crosses relation/subject/object/"
                    f"identity scope (target {target!r})"
                )
            if target_assertion.get("modality") != item.get("modality"):
                raise RelationIndexError(
                    f"{assertion_id}: withdrawal target {target!r} has a different modality"
                )
            if relation_contract:
                left_surface = comparison_values(item, relation_contract)
                right_surface = comparison_values(target_assertion, relation_contract)
                if left_surface != right_surface:
                    raise RelationIndexError(
                        f"{assertion_id}: withdrawal target {target!r} crosses the comparison surface"
                    )


def build_relation_graph(
    root: Path = ROOT,
    contracts_dir: Path | None = None,
    assertions_path: Path | None = None,
    extra_registries: Iterable[Path] = (),
    as_of: str | None = None,
    modality: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    # Both registry builders consume the extra paths.  Materialize an
    # arbitrary iterable once so a one-shot generator cannot make the second
    # validation see a different registry set.
    extra_registries = tuple(Path(path) for path in extra_registries)
    contracts_dir = contracts_dir or root / "contracts"
    assertions_path = assertions_path or root / "relation_assertions.yaml"
    relation_contract = load_yaml(contracts_dir / "relation_types.yaml")
    # D/8. the relation contract must declare identity/comparison/context fields.
    validate_relation_contract(relation_contract)
    adapter_contract = load_yaml(contracts_dir / "relation_adapters.yaml")
    # wire relation_contract into adapters for slot-identity lookups
    adapter_contract["relation_contract"] = relation_contract

    route_bom_rows = {row["route_item_id"]: row for row in load_csv(root / "route_bom.csv")}
    validate_route_profiles(adapter_contract, route_bom_rows)

    registry = build_reference_registry(root, extra_registries)
    receipt_registry = build_receipt_registry(adapter_contract, extra_registries)
    profile_ids = {
        item["route_profile_id"] for item in adapter_contract.get("route_profiles") or []
    }

    assertions = adapt_points(root, adapter_contract)
    assertions.extend(adapt_route_requirements(root, adapter_contract))
    assertions.extend(adapt_calls(root, adapter_contract))
    assertions.extend(
        adapt_explicit_assertions(
            assertions_path, adapter_contract, profile_ids, registry, relation_contract, receipt_registry
        )
    )
    assertions.extend(derive_capability_matches(assertions, adapter_contract))

    # attach derived canonical origin for evidence-counting (A/F)
    for item in assertions:
        if item.get("source_refs"):
            derived = derive_origin_group(item["source_refs"], registry)
            if derived:
                item["derived_origin_group"] = derived

    assertions.sort(key=lambda item: item["assertion_id"])
    validate_assertions(assertions, relation_contract)
    validate_withdrawals(assertions, relation_contract)
    return assertions, compute_slot_states(
        assertions, as_of=as_of, modality=modality, relation_contract=relation_contract
    )


PILOT_RULE_IDS = (
    "QGR-CAPABILITY-WITHOUT-EXACT-SERVICE-V1",
    "QGR-PRODUCT-STAGE-AS-OF-V1",
)


def reducer_contract_compatibility(
    relation_contract: dict[str, Any],
    adapters_contract: dict[str, Any],
    rules_contract: dict[str, Any],
) -> dict[str, Any]:
    """Compute the semantic contract consumed by the reducer pilot.

    A schema version or rule version is only a label.  The reducer's meaning
    also changes when an identity, acceptance, trigger, lifecycle, or admission
    field changes without a version bump.  Keep the full canonical definitions
    in this digest so the consumer can recompute it from the files rather than
    trusting a builder-authored compatibility value.
    """
    lifecycle_definition = (
        relation_contract.get("relation_types", {}).get("product_has_lifecycle_stage")
        or {}
    )
    lifecycle_adapter = (
        adapters_contract.get("adapters", {}).get("calls_product_lifecycle") or {}
    )
    rules_by_id = {
        rule.get("rule_id"): rule
        for rule in rules_contract.get("rules") or []
        if rule.get("rule_id")
    }
    missing = [rule_id for rule_id in PILOT_RULE_IDS if rule_id not in rules_by_id]
    if missing:
        raise RelationIndexError(
            f"question rules missing reducer pilot rule(s): {', '.join(missing)}"
        )
    return {
        "relation_types_schema_version": relation_contract.get("schema_version"),
        "relation_product_lifecycle_hash": hashlib.sha256(
            canonical_json(lifecycle_definition).encode("utf-8")
        ).hexdigest(),
        "adapter_calls_product_lifecycle_version": lifecycle_adapter.get("adapter_version"),
        "adapter_calls_product_lifecycle_hash": hashlib.sha256(
            canonical_json(lifecycle_adapter).encode("utf-8")
        ).hexdigest(),
        "question_rules_schema_version": rules_contract.get("schema_version"),
        "question_rule_versions": {
            rule_id: rules_by_id[rule_id].get("rule_version")
            for rule_id in PILOT_RULE_IDS
        },
        "question_rule_semantic_hashes": {
            rule_id: hashlib.sha256(
                canonical_json(rules_by_id[rule_id]).encode("utf-8")
            ).hexdigest()
            for rule_id in PILOT_RULE_IDS
        },
    }


def compute_build_manifest(
    assertions: list[dict[str, Any]],
    states: list[dict[str, Any]],
    contracts_dir: Path,
    rules_path: Path,
    adapters_path: Path,
    as_of: str | None = None,
    modality: str | None = None,
    extra_registry_paths: Iterable[Path] = (),
) -> dict[str, Any]:
    """H/10. bind assertion index + slot states + contract/rules hashes.

    The manifest records the query parameters (as_of / modality) as well as the
    content hashes, so a consumer can revalidate CONTENT, not just equality of a
    build id. No absolute path is ever written into the manifest.
    """
    def file_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    projection_root = contracts_dir.resolve().parent

    def ref(path: Path) -> dict[str, str]:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(projection_root)
        except ValueError:
            # An external fixture is still content-addressed, but never leak an
            # absolute path into generated output.
            relative = Path(resolved.name)
        return {"path": relative.as_posix(), "sha256": file_hash(resolved)}

    assertion_data_hash = hashlib.sha256(canonical_json(assertions).encode("utf-8")).hexdigest()
    slot_data_hash = hashlib.sha256(canonical_json(states).encode("utf-8")).hexdigest()
    data_hash = hashlib.sha256(
        (canonical_json(assertions) + canonical_json(states)).encode("utf-8")
    ).hexdigest()
    registry_refs = [ref(Path(path)) for path in extra_registry_paths]
    registry_names = [item["path"] for item in registry_refs]
    if len(registry_names) != len(set(registry_names)):
        raise RelationIndexError(
            "extra registry paths must have unique manifest-relative paths"
        )
    registries = sorted(registry_refs, key=lambda item: item["path"])
    relation_types_contract = load_yaml(contracts_dir / "relation_types.yaml")
    adapters_contract = load_yaml(adapters_path)
    rules_contract = load_yaml(rules_path)
    manifest = {
        "build_id": data_hash[:24].upper(),
        "assertion_count": len(assertions),
        "slot_count": len(states),
        "as_of": as_of,
        "modality": modality,
        "contracts": {
            "relation_types.yaml": ref(contracts_dir / "relation_types.yaml"),
            "relation_adapters.yaml": ref(adapters_path),
            "question_generation_rules.yaml": ref(rules_path),
        },
        "registries": registries,
        "assertion_data_hash": assertion_data_hash,
        "slot_data_hash": slot_data_hash,
        "data_hash": data_hash,
        # Keep the query boundary independently observable.  The state rows
        # normally make data_hash change as well, but a consumer should not
        # have to infer a temporal query from a row diff.
        "projection_query_hash": hashlib.sha256(
            canonical_json({"as_of": as_of, "modality": modality}).encode("utf-8")
        ).hexdigest(),
        # Schema-level compatibility is intentionally separate from content
        # hashes.  It lets a later question build use a different data
        # snapshot while still proving that the reducer contracts are
        # compatible across the history chain.
        "contract_compatibility": reducer_contract_compatibility(
            relation_types_contract, adapters_contract, rules_contract
        ),
    }
    return manifest


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]], manifest: dict[str, Any] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        if manifest is not None:
            handle.write(canonical_json({BUILD_MANIFEST_KEY: manifest}) + "\n")
        for row in rows:
            handle.write(canonical_json(row) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--contracts-dir", type=Path)
    parser.add_argument("--assertions", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="strict ISO query time (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS); states are "
        "computed as-of this instant",
    )
    parser.add_argument(
        "--assertions-only",
        action="store_true",
        help="write only the raw assertion index; no temporal slot states or leads are built",
    )
    parser.add_argument(
        "--modality",
        type=str,
        default=None,
        choices=["actual", "planned", "conditional", "unknown"],
        help="restrict the state merge to a single query modality",
    )
    parser.add_argument(
        "--extra-registry",
        type=Path,
        action="append",
        default=[],
        help="additional contract-bound reference registry (recorded in the build manifest)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.assertions_only and (args.as_of is not None or args.modality is not None):
        raise RelationIndexError(
            "--assertions-only is a raw projection and cannot be combined with "
            "--as-of or --modality"
        )
    if not args.as_of and not args.assertions_only:
        raise RelationIndexError(
            "temporal slot-state build requires explicit --as-of; "
            "use --assertions-only for a raw assertion index"
        )
    root = args.root.resolve()
    contracts = (args.contracts_dir or root / "contracts").resolve()
    assertions_path = (args.assertions or root / "relation_assertions.yaml").resolve()
    output = (args.output_dir or root / "out").resolve()
    as_of = parse_iso_datetime(args.as_of) if args.as_of else None
    assertions, slot_states = build_relation_graph(
        root,
        contracts,
        assertions_path,
        extra_registries=tuple(args.extra_registry),
        as_of=as_of,
        modality=args.modality,
    )
    if args.assertions_only:
        # A raw assertion projection deliberately carries no temporal slot
        # state.  Keep the normal manifest shape so the assertion rows remain
        # content-addressed, but never write a slot-state or lead file from a
        # no-as_of invocation.  Consumers that need a temporal projection must
        # use the explicit --as-of path below.
        manifest = compute_build_manifest(
            assertions,
            [],
            contracts,
            contracts / "question_generation_rules.yaml",
            contracts / "relation_adapters.yaml",
            as_of=None,
            modality=args.modality,
            extra_registry_paths=args.extra_registry,
        )
        manifest["projection_kind"] = "raw_assertions"
        write_jsonl(output / "relation_assertion_index.jsonl", assertions, manifest)
        print(
            f"raw relation assertions: {len(assertions)} -> {output} "
            f"(build {manifest['build_id']})"
        )
        return 0
    manifest = compute_build_manifest(
        assertions,
        slot_states,
        contracts,
        contracts / "question_generation_rules.yaml",
        contracts / "relation_adapters.yaml",
        as_of=as_of,
        modality=args.modality,
        extra_registry_paths=args.extra_registry,
    )
    write_jsonl(output / "relation_assertion_index.jsonl", assertions, manifest)
    write_jsonl(output / "relation_slot_states.jsonl", slot_states, manifest)
    # The route-service rule is frozen as an experimental lead-only rule.  Keep
    # the 83 (or current deterministic) overlaps observable alongside the
    # relation index without presenting them as formal questions or canonical
    # relations.  Import lazily to avoid a module cycle: recompute_question_state
    # imports the reducer helpers above.
    from tools.research.recompute_question_state import generate_relation_leads

    relation_contract = load_yaml(contracts / "relation_types.yaml")
    adapter_contract = load_yaml(contracts / "relation_adapters.yaml")
    adapter_contract["relation_contract"] = relation_contract
    rules_contract = load_yaml(contracts / "question_generation_rules.yaml")
    leads, funnel = generate_relation_leads(
        assertions,
        slot_states,
        rules_contract,
        adapter_contract,
        relation_contract,
        as_of=as_of,
    )
    write_jsonl(output / "relation_leads.jsonl", leads)
    funnel_payload = {
        **funnel,
        "relation_build_id": manifest["build_id"],
        "relation_data_hash": manifest["data_hash"],
        "as_of": as_of,
        "modality": args.modality,
    }
    (output / "relation_lead_funnel.json").write_text(
        canonical_json(funnel_payload) + "\n", encoding="utf-8"
    )
    print(
        f"relation index: {len(assertions)} assertions, "
        f"{len(slot_states)} slots -> {output} (build {manifest['build_id']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
