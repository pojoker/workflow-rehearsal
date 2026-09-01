#!/usr/bin/env python3
"""Generate diagnostic question candidates and recompute their resolution state.

Round-2 reducer-pilot fixes implemented here:
  3. the route-service gap candidate is generated ONLY when the complete ACTUAL
     coverage satisfies every all_of and one_of requirement group of the exact
     profile. A single cell, a partial match or a planned match never licenses
     the claim that a company has the route capability.
  4. the question target must be a REAL fully-bound slot. A synthetic
     route-level slot (route_profile_id only) and any aggregation across
     products / service kinds are forbidden. service_kind is pinned per slot so
     listed/qualifying never close a demonstrated/shipping/deployed question.
     When nothing can bind, no question is generated and the deferral is reported.
  5. `reopened` requires a real previous-state input (a previous question
     snapshot or an append-only state event log). With no prior state a question
     is never "reopened"; it is simply open.
  6. the CLI accepts a strict ISO `as_of` and a query `modality` and refuses to
     mix them with projections built for other query parameters.
 10. the output manifest binds contract CONTENT hashes and relative paths only;
     generated output is byte-identical across worktree roots.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.research.build_relation_index import (
    BUILD_MANIFEST_KEY,
    ROOT,
    RelationIndexError,
    SOURCE_REF_KINDS,
    SERVICE_KIND_ENUM,
    build_reference_registry,
    canonical_json,
    evaluate_requirement_group,
    is_active_at_as_of,
    load_yaml,
    parse_iso_datetime,
    relation_slot_identity,
    stable_id,
    validate_relation_contract,
    write_jsonl,
)


DEFAULT_ASSERTION_INDEX = ROOT / "out/relation_assertion_index.jsonl"
DEFAULT_SLOT_STATES = ROOT / "out/relation_slot_states.jsonl"
DEFAULT_RULES = ROOT / "contracts/question_generation_rules.yaml"
DEFAULT_ADAPTERS = ROOT / "contracts/relation_adapters.yaml"
DEFAULT_OUTPUT = ROOT / "out/generated_diagnostic_questions.jsonl"
_UNSET = object()


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


def read_index_with_manifest(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """H. read a JSONL index; separate the build manifest line from data rows."""
    manifest = None
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise QuestionStateError(f"{path}:{line_number} must be a JSON object")
            if BUILD_MANIFEST_KEY in value:
                if manifest is not None:
                    raise QuestionStateError(f"{path}:{line_number} contains duplicate build manifests")
                manifest = value[BUILD_MANIFEST_KEY]
                if not isinstance(manifest, dict):
                    raise QuestionStateError(f"{path}:{line_number} build manifest must be an object")
                continue
            rows.append(value)
    return manifest, rows


# ---------------------------------------------------------------------------
# 10. manifest content revalidation (not just build_id equality)
# ---------------------------------------------------------------------------
def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contract_ref(path: Path, base: Path | None = None) -> dict[str, str]:
    """10. a root-relative, content-addressed contract reference.

    The base is the root of the projection being described (the parent of the
    `out/` directory holding the index), not the module's repo root, so absolute
    paths never reach the generated output and the same projection is
    byte-identical in every worktree root.
    """
    resolved = path.resolve()
    roots = [base] if base is not None else []
    roots.append(ROOT)
    for candidate in roots:
        try:
            relative = resolved.relative_to(candidate.resolve())
            break
        except ValueError:
            continue
    else:
        relative = Path(resolved.name)
    return {"path": relative.as_posix(), "sha256": _file_hash(resolved)}


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_manifest_shape(manifest: dict[str, Any], label: str) -> None:
    """Validate every manifest field before comparing two projections."""
    if not isinstance(manifest, dict):
        raise QuestionStateError(f"{label} build manifest must be an object")
    for key in ("build_id", "data_hash", "assertion_data_hash", "slot_data_hash"):
        value = manifest.get(key)
        if not isinstance(value, str) or not value:
            raise QuestionStateError(f"{label} manifest missing {key}")
    if not re.fullmatch(r"[0-9A-F]{24}", manifest["build_id"]):
        raise QuestionStateError(f"{label} manifest build_id is malformed")
    for key in ("data_hash", "assertion_data_hash", "slot_data_hash"):
        if not _SHA256_RE.fullmatch(manifest[key]):
            raise QuestionStateError(f"{label} manifest {key} is not a SHA-256 hash")
    for key in ("assertion_count", "slot_count"):
        if not isinstance(manifest.get(key), int) or manifest[key] < 0:
            raise QuestionStateError(f"{label} manifest {key} must be a non-negative integer")
    if manifest.get("as_of") is not None:
        parse_iso_datetime(manifest["as_of"])
    if manifest.get("modality") not in (None, "actual", "planned", "conditional", "unknown"):
        raise QuestionStateError(f"{label} manifest modality is invalid")

    contracts = manifest.get("contracts")
    expected_contract_names = {
        "relation_types.yaml",
        "relation_adapters.yaml",
        "question_generation_rules.yaml",
    }
    if not isinstance(contracts, dict) or set(contracts) != expected_contract_names:
        raise QuestionStateError(
            f"{label} manifest must contain complete relation_types/relation_adapters/"
            f"question_generation_rules contract hashes"
        )
    for name, value in contracts.items():
        if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
            raise QuestionStateError(f"{label} manifest contract {name} must contain path and sha256")
        path = value["path"]
        if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise QuestionStateError(f"{label} manifest contract {name} path must be relative")
        if not isinstance(value["sha256"], str) or not _SHA256_RE.fullmatch(value["sha256"]):
            raise QuestionStateError(f"{label} manifest contract {name} hash is malformed")

    registries = manifest.get("registries")
    if not isinstance(registries, list):
        raise QuestionStateError(f"{label} manifest registries must be a list")
    seen_paths: set[str] = set()
    for entry in registries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise QuestionStateError(f"{label} manifest registry entries must contain path and sha256")
        path = entry["path"]
        if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise QuestionStateError(f"{label} manifest registry path must be relative")
        if path in seen_paths:
            raise QuestionStateError(f"{label} manifest contains duplicate registry {path!r}")
        seen_paths.add(path)
        if not isinstance(entry["sha256"], str) or not _SHA256_RE.fullmatch(entry["sha256"]):
            raise QuestionStateError(f"{label} manifest registry hash is malformed")


def _require_same_build(
    assertion_manifest: dict[str, Any] | None,
    slot_manifest: dict[str, Any] | None,
    rules_path: Path | None = None,
    adapters_path: Path | None = None,
    assertion_rows: list[dict[str, Any]] | None = None,
    slot_rows: list[dict[str, Any]] | None = None,
    relation_types_path: Path | None = None,
    extra_registry_paths: Iterable[Path] = (),
) -> dict[str, Any]:
    """10. revalidate manifest CONTENT and row hashes, not only build_id equality."""
    if assertion_manifest is None or slot_manifest is None:
        raise QuestionStateError(
            "missing build manifest: assertion index and slot states must carry a build id"
        )
    _validate_manifest_shape(assertion_manifest, "assertion index")
    _validate_manifest_shape(slot_manifest, "slot state")
    for key in (
        "build_id",
        "data_hash",
        "assertion_data_hash",
        "slot_data_hash",
        "assertion_count",
        "slot_count",
        "as_of",
        "modality",
    ):
        if assertion_manifest.get(key) != slot_manifest.get(key):
            raise QuestionStateError(
                f"cross-build file mismatch: {key} differs between the assertion index "
                f"and the slot states; files from different builds must not be mixed"
            )
    contracts_a = assertion_manifest["contracts"]
    contracts_s = slot_manifest["contracts"]
    if contracts_a != contracts_s:
        raise QuestionStateError(
            "cross-build file mismatch: contract content hashes differ between the "
            "assertion index and the slot states"
        )
    if assertion_rows is not None:
        actual = hashlib.sha256(canonical_json(assertion_rows).encode("utf-8")).hexdigest()
        if len(assertion_rows) != assertion_manifest["assertion_count"] or actual != assertion_manifest["assertion_data_hash"]:
            raise QuestionStateError("assertion JSONL rows do not match the build manifest count/hash")
    if slot_rows is not None:
        actual = hashlib.sha256(canonical_json(slot_rows).encode("utf-8")).hexdigest()
        if len(slot_rows) != slot_manifest["slot_count"] or actual != slot_manifest["slot_data_hash"]:
            raise QuestionStateError("slot-state JSONL rows do not match the build manifest count/hash")
    if assertion_rows is not None and slot_rows is not None:
        combined = hashlib.sha256(
            (canonical_json(assertion_rows) + canonical_json(slot_rows)).encode("utf-8")
        ).hexdigest()
        if combined != assertion_manifest["data_hash"]:
            raise QuestionStateError("assertion/slot JSONL rows do not match the combined build data_hash")

    if (assertion_rows is not None or slot_rows is not None) and any(
        path is None for path in (rules_path, adapters_path, relation_types_path)
    ):
        raise QuestionStateError(
            "rules, adapters and relation_types paths are all required when "
            "revalidating projection rows"
        )

    def verify_file(name: str, path: Path | None) -> None:
        if path is None:
            return
        if not path.is_file():
            raise QuestionStateError(f"{name} contract file is missing: {path}")
        recorded = contracts_a[name]
        if recorded["sha256"] != _file_hash(path):
            raise QuestionStateError(
                f"{name} changed after the projection was built; rebuild the relation index "
                "before recomputing question state"
            )
    verify_file("question_generation_rules.yaml", rules_path)
    verify_file("relation_adapters.yaml", adapters_path)
    verify_file("relation_types.yaml", relation_types_path)
    if relation_types_path is not None:
        try:
            validate_relation_contract(load_yaml(relation_types_path))
        except (OSError, RelationIndexError) as exc:
            raise QuestionStateError(
                f"relation_types contract cannot be validated: {relation_types_path}"
            ) from exc

    registry_base = rules_path.resolve().parent.parent if rules_path is not None else None
    expected_registries = sorted(
        (_contract_ref(Path(path), registry_base) for path in extra_registry_paths),
        key=lambda item: item["path"],
    )
    if assertion_manifest.get("registries") != expected_registries:
        raise QuestionStateError(
            "extra registry content/path does not match the build manifest; "
            "unlisted product identities are not allowed"
        )
    return assertion_manifest


def _require_query_matches_manifest(
    manifest: dict[str, Any], as_of: str | None, modality: str | None
) -> None:
    """6. the query parameters must match the projection that was built."""
    normalized_as_of = parse_iso_datetime(as_of) if as_of is not None else None
    if manifest.get("as_of") != normalized_as_of:
        raise QuestionStateError(
            f"as_of {as_of!r} does not match the projection as_of {manifest.get('as_of')!r}; "
            f"rebuild the relation index with --as-of {as_of}"
        )
    if manifest.get("modality") != modality:
        raise QuestionStateError(
            f"modality {modality!r} does not match the projection modality "
            f"{manifest.get('modality')!r}; rebuild with --modality {modality}"
        )


# ---------------------------------------------------------------------------
# 5. prior question state (real previous snapshot / append-only event log)
# ---------------------------------------------------------------------------
class PriorQuestionState:
    """Real previous-state evidence required before `reopened` may be used.

    Without one of these inputs a question is never reopened: there is no way to
    prove it was ever satisfied.
    """

    def __init__(
        self,
        statuses: dict[str, str] | None = None,
        transitions: list[dict[str, Any]] | None = None,
        sources: list[str] | None = None,
        known_questions: Iterable[str] | None = None,
        metadata: dict[str, Any] | None = None,
        _validated: bool = False,
    ) -> None:
        if (statuses or transitions) and not _validated:
            raise QuestionStateError(
                "previous question state must be loaded from a validated snapshot "
                "or append-only event log"
            )
        self._statuses: dict[str, str] = dict(statuses or {})
        self._transitions: list[dict[str, Any]] = list(transitions or [])
        self.sources: list[str] = list(sources or [])
        self._known_questions: set[str] = set(known_questions or self._statuses)
        self.metadata: dict[str, Any] = dict(metadata or {})

    @property
    def empty(self) -> bool:
        return not self._statuses and not self._transitions

    @classmethod
    def _validate_history_manifest(
        cls,
        manifest: dict[str, Any] | None,
        *,
        path: Path,
        expected_manifest: dict[str, Any] | None,
        rules_path: Path | None,
        adapters_path: Path | None,
        relation_types_path: Path | None,
        extra_registry_paths: Iterable[Path],
        registry: dict[str, dict[str, Any]] | None,
        expected_as_of: str | None | object,
        expected_modality: str | None | object,
        kind: str,
    ) -> dict[str, Any]:
        if manifest is None:
            raise QuestionStateError(
                f"{path}: previous {kind} must carry a content-addressed build manifest"
            )
        if expected_manifest is None:
            raise QuestionStateError(
                f"{path}: previous {kind} must be checked against the current build manifest"
            )
        _validate_manifest_shape(manifest, f"previous {kind}")
        history_base = (
            relation_types_path.resolve().parent.parent
            if relation_types_path is not None
            else rules_path.resolve().parent.parent
            if rules_path is not None
            else None
        )
        extra_registry_paths = tuple(extra_registry_paths)
        expected_registries = sorted(
            (
                _contract_ref(Path(registry_path), history_base)
                for registry_path in extra_registry_paths
            ),
            key=lambda item: item["path"],
        )
        # Direct Python callers often already pass the validated registry map
        # and omit the original paths.  Reuse its content-addressed refs in
        # that case; a plain hand-built dict has no refs and cannot authorize a
        # product target.
        if not extra_registry_paths and registry is not None:
            expected_registries = sorted(
                getattr(registry, "bound_registry_refs", []),
                key=lambda item: item["path"],
            )
        if manifest.get("registries") != expected_registries:
            raise QuestionStateError(
                f"{path}: previous {kind} registry set does not match the current build"
            )
        if registry is not None:
            bound_registries = sorted(
                getattr(registry, "bound_registry_refs", []),
                key=lambda item: item["path"],
            )
            if bound_registries != manifest.get("registries"):
                raise QuestionStateError(
                    f"{path}: previous {kind} registry manifest does not match the "
                    "validated reference registry"
                )
        if expected_as_of is not _UNSET:
            expected_time = (
                parse_iso_datetime(expected_as_of)
                if expected_as_of is not None
                else None
            )
            if manifest.get("as_of") != expected_time:
                raise QuestionStateError(
                    f"{path}: previous {kind} as_of does not match the requested query"
                )
        if expected_modality is not _UNSET:
            if manifest.get("modality") != expected_modality:
                raise QuestionStateError(
                    f"{path}: previous {kind} modality does not match the requested query"
                )
        if expected_manifest is not None:
            for key in (
                "build_id",
                "data_hash",
                "assertion_data_hash",
                "slot_data_hash",
                "assertion_count",
                "slot_count",
                "as_of",
                "modality",
                "contracts",
                "registries",
            ):
                if manifest.get(key) != expected_manifest.get(key):
                    raise QuestionStateError(
                        f"{path}: previous {kind} belongs to a different relation build ({key})"
                    )

        def verify(name: str, candidate: Path | None) -> None:
            if candidate is not None and manifest["contracts"][name]["sha256"] != _file_hash(candidate):
                raise QuestionStateError(f"{path}: previous {kind} contract {name} hash is stale")

        verify("question_generation_rules.yaml", rules_path)
        verify("relation_adapters.yaml", adapters_path)
        verify("relation_types.yaml", relation_types_path)
        return manifest

    @classmethod
    def from_snapshot(
        cls,
        path: Path,
        *,
        expected_manifest: dict[str, Any] | None = None,
        rules_path: Path | None = None,
        adapters_path: Path | None = None,
        relation_types_path: Path | None = None,
        extra_registry_paths: Iterable[Path] = (),
        registry: dict[str, dict[str, Any]] | None = None,
        expected_as_of: str | None | object = _UNSET,
        expected_modality: str | None | object = _UNSET,
    ) -> "PriorQuestionState":
        """A previous generated-questions projection (question_id -> status).

        A bare line saying ``satisfied`` is not a historical source.  The
        snapshot must be a real generated projection with a manifest, matching
        build/query/contract hashes, and complete target identities.
        """
        manifest, rows = read_index_with_manifest(path)
        manifest = cls._validate_history_manifest(
            manifest,
            path=path,
            expected_manifest=expected_manifest,
            rules_path=rules_path,
            adapters_path=adapters_path,
            relation_types_path=relation_types_path,
            extra_registry_paths=extra_registry_paths,
            registry=registry,
            expected_as_of=expected_as_of,
            expected_modality=expected_modality,
            kind="snapshot",
        )
        if manifest.get("snapshot_schema_version") != "question_state_snapshot_v1":
            raise QuestionStateError(f"{path}: snapshot_schema_version is missing or unsupported")
        if registry is None:
            raise QuestionStateError(
                f"{path}: previous snapshot validation requires the current reference registry"
            )
        if manifest.get("question_count") != len(rows):
            raise QuestionStateError(f"{path}: question_count does not match snapshot rows")
        expected_rows_hash = hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()
        if manifest.get("questions_data_hash") != expected_rows_hash:
            raise QuestionStateError(f"{path}: snapshot rows do not match questions_data_hash")
        allowed = {"open", "partial", "blocked", "satisfied", "reopened", "conflicted"}
        statuses: dict[str, str] = {}
        known: set[str] = set()
        fingerprints: set[str] = set()
        relation_contract = load_yaml(relation_types_path or DEFAULT_ADAPTERS.parent / "relation_types.yaml")
        for index, row in enumerate(rows, start=1):
            required = {"question_id", "target", "dedupe_fingerprint", "resolution_status"}
            if not required <= set(row):
                raise QuestionStateError(f"{path}:{index}: snapshot question is incomplete")
            question_id = row["question_id"]
            status = row["resolution_status"]
            if not isinstance(question_id, str) or not question_id or status not in allowed:
                raise QuestionStateError(f"{path}:{index}: invalid question id or resolution status")
            target = row["target"]
            if not isinstance(target, dict):
                raise QuestionStateError(f"{path}:{index}: question target must be an object")
            for field in ("slot_id", "relation_type", "subject_ref", "object_ref", "route_profile_id", "product_ref", "service_kind"):
                if not target.get(field):
                    raise QuestionStateError(f"{path}:{index}: target is missing {field}")
            if target["relation_type"] != "company_serves_route" or target["service_kind"] not in SERVICE_KIND_ENUM:
                raise QuestionStateError(f"{path}:{index}: target relation/service identity is invalid")
            if not target["subject_ref"].startswith("company:"):
                raise QuestionStateError(
                    f"{path}:{index}: target subject must use canonical company:<name> identity"
                )
            if target["object_ref"] != f"route_profile:{target['route_profile_id']}":
                raise QuestionStateError(
                    f"{path}:{index}: target object_ref and route_profile_id disagree"
                )
            if not target["product_ref"].startswith("product:"):
                raise QuestionStateError(
                    f"{path}:{index}: target product_ref must use product:<id> identity"
                )
            product = registry.get(target["product_ref"])
            if (
                not product
                or product.get("kind") != "product"
                or product.get("company") != target["subject_ref"]
                or not product.get("registry_id")
                or product.get("registry_id") not in set(
                    getattr(registry, "bound_registry_ids", set())
                )
            ):
                raise QuestionStateError(
                    f"{path}:{index}: target product is not present in the "
                    "validated current product registry"
                )
            target_identity_scope = target.get("identity_scope")
            expected_identity_scope = {
                "route_profile_id": target["route_profile_id"],
                "product_ref": target["product_ref"],
                "service_kind": target["service_kind"],
            }
            if target_identity_scope != expected_identity_scope:
                raise QuestionStateError(
                    f"{path}:{index}: target identity_scope is incomplete or inconsistent"
                )
            identity = relation_slot_identity(
                "company_serves_route",
                target["subject_ref"],
                target["object_ref"],
                {
                    "route_profile_id": target["route_profile_id"],
                    "product_ref": target["product_ref"],
                    "service_kind": target["service_kind"],
                },
                relation_contract,
            )
            if target["slot_id"] != stable_id("RS", identity):
                raise QuestionStateError(f"{path}:{index}: target slot_id is not identity-derived")
            if question_id in known:
                raise QuestionStateError(f"{path}:{index}: duplicate question_id")
            known.add(question_id)
            statuses[question_id] = status
            fingerprint = row["dedupe_fingerprint"]
            if not isinstance(fingerprint, str) or not fingerprint:
                raise QuestionStateError(f"{path}:{index}: empty dedupe_fingerprint")
            if fingerprint in fingerprints:
                raise QuestionStateError(f"{path}:{index}: duplicate dedupe_fingerprint")
            fingerprints.add(fingerprint)
            try:
                fingerprint_value = json.loads(fingerprint)
            except (TypeError, ValueError) as exc:
                raise QuestionStateError(
                    f"{path}:{index}: dedupe_fingerprint is not canonical JSON"
                ) from exc
            if not isinstance(fingerprint_value, dict) or any(
                fingerprint_value.get(field) != expected
                for field, expected in (
                    ("target_relation_type", "company_serves_route"),
                    ("subject_ref", target["subject_ref"]),
                    ("route_profile_id", target["route_profile_id"]),
                    ("product_ref", target["product_ref"]),
                    ("service_kind", target["service_kind"]),
                )
            ):
                raise QuestionStateError(
                    f"{path}:{index}: dedupe_fingerprint does not bind the target identity"
                )
            expected_question_id = stable_id("GQ", fingerprint, length=12)
            if question_id != expected_question_id:
                raise QuestionStateError(
                    f"{path}:{index}: question_id is not derived from dedupe_fingerprint"
                )
            statuses[fingerprint] = status
        return cls(
            statuses=statuses,
            known_questions=known | set(statuses),
            sources=[f"snapshot:{path.name}"],
            metadata=manifest,
            _validated=True,
        )

    @classmethod
    def from_events(
        cls,
        path: Path,
        *,
        expected_manifest: dict[str, Any] | None = None,
        rules_path: Path | None = None,
        adapters_path: Path | None = None,
        relation_types_path: Path | None = None,
        extra_registry_paths: Iterable[Path] = (),
        registry: dict[str, dict[str, Any]] | None = None,
        expected_as_of: str | None | object = _UNSET,
        expected_modality: str | None | object = _UNSET,
    ) -> "PriorQuestionState":
        """An append-only question state event log.

        The log is verified to really be append-only: records must be in
        non-decreasing time order and every transition must start from the
        previous status of the same question. A log that is edited in place is
        rejected instead of being trusted.
        """
        manifest, rows = read_index_with_manifest(path)
        manifest = cls._validate_history_manifest(
            manifest,
            path=path,
            expected_manifest=expected_manifest,
            rules_path=rules_path,
            adapters_path=adapters_path,
            relation_types_path=relation_types_path,
            extra_registry_paths=extra_registry_paths,
            registry=registry,
            expected_as_of=expected_as_of,
            expected_modality=expected_modality,
            kind="state event log",
        )
        if manifest.get("state_event_schema_version") != "question_state_events_v1":
            raise QuestionStateError(f"{path}: state_event_schema_version is missing or unsupported")
        if manifest.get("event_count") != len(rows):
            raise QuestionStateError(f"{path}: event_count does not match state event rows")
        expected_rows_hash = hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()
        if manifest.get("events_data_hash") != expected_rows_hash:
            raise QuestionStateError(f"{path}: state event rows do not match events_data_hash")
        transitions: list[dict[str, Any]] = []
        last_status: dict[str, str] = {}
        previous_at: str | None = None
        allowed = {"open", "partial", "blocked", "satisfied", "reopened", "conflicted"}
        for index, row in enumerate(rows, start=1):
            question_id = row.get("question_id")
            from_status = row.get("from_status")
            to_status = row.get("to_status")
            at = row.get("at")
            if not question_id or not from_status or not to_status or from_status not in allowed or to_status not in allowed:
                raise QuestionStateError(
                    f"{path.name}:{index}: a state event needs question_id, "
                    f"from_status and to_status"
                )
            if at is None:
                raise QuestionStateError(f"{path.name}:{index}: state events require at")
            parsed = parse_iso_datetime(at)
            if expected_as_of is not _UNSET and expected_as_of is not None and parsed > parse_iso_datetime(expected_as_of):
                raise QuestionStateError(f"{path.name}:{index}: state event is after the query as_of")
            if previous_at is not None and parsed < previous_at:
                raise QuestionStateError(
                    f"{path.name}:{index}: state event log is not append-only "
                    f"(event time {parsed} precedes {previous_at})"
                )
            previous_at = parsed
            expected = last_status.get(question_id)
            if expected is not None and expected != from_status:
                raise QuestionStateError(
                    f"{path.name}:{index}: state event log is not append-only "
                    f"(expected from_status {expected!r}, got {from_status!r})"
                )
            last_status[question_id] = to_status
            transitions.append(row)
        return cls(
            transitions=transitions,
            known_questions={row["question_id"] for row in transitions},
            sources=[f"events:{path.name}"],
            metadata=manifest,
            _validated=True,
        )

    @classmethod
    def load(
        cls,
        snapshot: Path | None = None,
        events: Path | None = None,
        **kwargs: Any,
    ) -> "PriorQuestionState | None":
        states: list[PriorQuestionState] = []
        if snapshot is not None:
            states.append(cls.from_snapshot(snapshot, **kwargs))
        if events is not None:
            states.append(cls.from_events(events, **kwargs))
        if not states:
            return None
        merged = cls(
            statuses={
                key: value for state in states for key, value in state._statuses.items()
            },
            transitions=[
                item for state in states for item in state._transitions
            ],
            sources=[source for state in states for source in state.sources],
            known_questions={
                question for state in states for question in state._known_questions
            },
            metadata=states[0].metadata,
            _validated=True,
        )
        if any(state.metadata != states[0].metadata for state in states[1:]):
            raise QuestionStateError("previous snapshot and state events belong to different builds")
        return merged

    def has_question(self, question_id: str, fingerprint: str | None = None) -> bool:
        return question_id in self._known_questions or bool(
            fingerprint and fingerprint in self._known_questions
        )

    def was_satisfied(self, question_id: str, fingerprint: str | None = None) -> bool:
        if self._statuses.get(question_id) == "satisfied":
            return True
        if fingerprint and self._statuses.get(fingerprint) == "satisfied":
            return True
        for event in self._transitions:
            if event.get("question_id") != question_id:
                continue
            if event.get("to_status") == "satisfied":
                return True
        return False


# ---------------------------------------------------------------------------
# 3/4. coverage gate and real target binding
# ---------------------------------------------------------------------------
def actual_coverage_cells(
    assertions: list[dict[str, Any]],
    subject_ref: str,
    profile_id: str,
    slot_states: list[dict[str, Any]] | None = None,
    as_of: str | None = None,
    modality: str | None = None,
) -> set[str]:
    """3. cells covered by an ACTUAL match in the filtered state projection.

    Looking at the raw assertion list here used to let a 2026 match create a
    question in an ``as_of=2020`` projection.  State IDs are authoritative when
    supplied; the direct time/modality checks remain a defensive guard for API
    callers that only pass assertions.
    """
    # None means no state projection was supplied (legacy direct API fallback);
    # an explicitly supplied empty list is an authoritative projection with no
    # active slots and must not fall back to raw rows.
    has_state_projection = slot_states is not None
    state_by_slot = {state["slot_id"]: state for state in (slot_states or [])}
    return {
        item["scope"]["capability_cell_id"]
        for item in assertions
        if item["relation_type"] == "capability_matches_route"
        and item["subject_ref"] == subject_ref
        and item["scope"].get("route_profile_id") == profile_id
        and item["scope"].get("capability_cell_id")
        and item["modality"] == "actual"
        and item["polarity"] == "supporting"
        and (modality in (None, "actual"))
        and is_active_at_as_of(item, as_of)
        and (
            not has_state_projection
            or item["assertion_id"]
            in set(state_by_slot.get(item["slot_id"], {}).get("active_assertion_ids") or [])
        )
    }


def project_group_cells(
    assertions: list[dict[str, Any]], profile_id: str
) -> dict[str, set[str]]:
    """Project each declared requirement group onto capability cell ids.

    A group declares route_bom items; the cells it actually requires are the ones
    produced by the (derived_candidate) route_requires_capability projection for
    that group. Coverage is measured in cells, so the comparison must happen in
    cells too - comparing route-item ids against covered cells would silently
    make every group unsatisfiable.
    """
    projected: dict[str, set[str]] = defaultdict(set)
    for item in assertions:
        if item["relation_type"] != "route_requires_capability":
            continue
        if item["scope"].get("route_profile_id") != profile_id:
            continue
        group_id = (item.get("metadata") or {}).get("requirement_group_id")
        cell_id = item["scope"].get("capability_cell_id")
        if group_id and cell_id:
            projected[group_id].add(cell_id)
    return dict(projected)


def evaluate_coverage(
    profile: dict[str, Any],
    coverage_cells: set[str],
    group_cells: dict[str, set[str]] | None = None,
) -> tuple[bool, list[dict[str, Any]], str | None]:
    """3. every declared all_of / one_of group must be satisfied by ACTUAL coverage."""
    if profile.get("requirement_semantics") == "UNKNOWN":
        return False, [], "unknown_requirement_semantics"
    groups = profile.get("requirement_groups") or []
    if not groups:
        return False, [], "no_declared_requirement_groups"
    group_cells = group_cells or {}
    evaluated = []
    for group in groups:
        group_id = group.get("group_id")
        cells = group_cells.get(group_id)
        if cells is None:
            # the group has no projected cells: it cannot be covered at all
            evaluated.append(
                {
                    "group_id": group_id,
                    "kind": group.get("kind"),
                    "satisfied": False,
                    "capability_cell_ids": list(group.get("capability_cell_ids") or []),
                    "required_capability_cell_ids": [],
                }
            )
            continue
        evaluated.append(
            {
                "group_id": group_id,
                "kind": group.get("kind"),
                "satisfied": evaluate_requirement_group(
                    {"kind": group.get("kind"), "capability_cell_ids": sorted(cells)},
                    coverage_cells,
                ),
                "capability_cell_ids": list(group.get("capability_cell_ids") or []),
                "required_capability_cell_ids": sorted(cells),
            }
        )
    complete = all(item["satisfied"] for item in evaluated)
    reason = None if complete else "incomplete_actual_coverage"
    return complete, evaluated, reason


def _identity_scope(
    relation_contract: dict[str, Any],
    relation_type: str,
    scope: dict[str, Any],
) -> dict[str, Any]:
    """8. the identity part of a scope, per the declared identity fields."""
    definition = (relation_contract.get("relation_types") or {}).get(relation_type) or {}
    id_fields = definition.get("slot_identity_fields") or ["subject_ref", "object_ref"]
    return {field: scope[field] for field in id_fields if field in scope}


def bind_target_slot(
    relation_contract: dict[str, Any],
    target_relation_type: str,
    subject_ref: str,
    object_ref: str,
    scope: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """4. bind a REAL slot, or refuse with a reason.

    A slot is real only when every declared slot identity field is bound. A
    company_serves_route target that carries only `route_profile_id` is a
    synthetic route-level slot and is refused.
    """
    definition = (relation_contract.get("relation_types") or {}).get(target_relation_type)
    if not isinstance(definition, dict):
        return None, None, f"unknown_target_relation_type:{target_relation_type}"
    id_fields = definition.get("slot_identity_fields") or ["subject_ref", "object_ref"]
    unbound = [
        field
        for field in id_fields
        if field not in ("subject_ref", "object_ref") and not scope.get(field)
    ]
    if unbound:
        return None, None, f"unbound_identity_fields:{','.join(sorted(unbound))}"
    if target_relation_type == "company_serves_route":
        if not isinstance(subject_ref, str) or not subject_ref.startswith("company:"):
            return None, None, "noncanonical_subject_identity"
        route_profile_id = scope.get("route_profile_id")
        if object_ref != f"route_profile:{route_profile_id}":
            return None, None, "route_profile_identity_mismatch"
        if not isinstance(scope.get("product_ref"), str) or not scope["product_ref"].startswith("product:"):
            return None, None, "noncanonical_product_identity"
    if definition.get("requires_service_kind"):
        service_kind = scope.get("service_kind")
        if service_kind not in SERVICE_KIND_ENUM:
            return None, None, f"uncontrolled_service_kind:{service_kind!r}"
    identity = relation_slot_identity(
        target_relation_type, subject_ref, object_ref, scope, relation_contract
    )
    return stable_id("RS", identity), identity, None


def candidate_product_refs(registry: dict[str, dict[str, Any]], subject_ref: str, kind: str) -> list[str]:
    """4. product_ref values that really resolve and really belong to the subject."""
    candidates: list[str] = []
    for ref, entry in (registry or {}).items():
        if entry.get("kind") != kind or entry.get("company") != subject_ref:
            continue
        if kind == "product":
            if not isinstance(ref, str) or not ref.startswith("product:"):
                continue
            # Products are not present in the production CSV ledgers in this
            # pilot.  A target may therefore come only from a validated,
            # manifest-bound extra registry; accepting an arbitrary in-memory
            # dict here would reintroduce synthetic product injection.
            if not entry.get("registry_id"):
                continue
            if entry.get("registry_id") not in set(
                getattr(registry, "bound_registry_ids", set())
            ):
                continue
            source_refs = entry.get("source_refs") or []
            # An extra registry product is only a target when it is itself
            # evidenced by resolvable, same-company source objects.  This keeps
            # a caller from injecting a bare product id into the question path.
            if not source_refs or any(
                not registry.get(source_ref)
                or registry[source_ref].get("kind") not in SOURCE_REF_KINDS
                or registry[source_ref].get("company") != subject_ref
                for source_ref in source_refs
            ):
                continue
        candidates.append(ref)
    return sorted(candidates)


# ---------------------------------------------------------------------------
# resolution
# ---------------------------------------------------------------------------
def question_fingerprint(
    rule_id: str, subject_ref: str, route_profile_id: str, product_ref: str, service_kind: str
) -> str:
    return canonical_json(
        {
            "rule_id": rule_id,
            "subject_ref": subject_ref,
            "target_relation_type": "company_serves_route",
            "route_profile_id": route_profile_id,
            "product_ref": product_ref,
            "service_kind": service_kind,
        }
    )


def _qualified_supports(
    assertions: list[dict[str, Any]],
    active_ids: set[str],
    acceptance: dict[str, Any],
    service_kind: str | None,
) -> list[dict[str, Any]]:
    accepted_kinds = set(acceptance.get("service_kind_acceptance") or [])
    if accepted_kinds and service_kind not in accepted_kinds:
        raise QuestionStateError(
            f"target service_kind {service_kind!r} is not in the acceptance "
            f"service_kind_acceptance {sorted(accepted_kinds)}"
        )
    return [
        item
        for item in assertions
        if item["assertion_id"] in active_ids
        and item["relation_type"] == acceptance["relation_type"]
        and item["epistemic_status"] == acceptance["epistemic_status"]
        and item["polarity"] == acceptance["polarity"]
        and item["modality"] == acceptance["modality"]
        # 4. service_kind is pinned to the target slot: listed / qualifying can
        # never close a demonstrated / shipping / deployed question, because they
        # live in a different slot and never match here.
        and (
            service_kind is None
            or item["scope"].get("service_kind") == service_kind
        )
    ]


def compute_resolution(
    target_assertions: list[dict[str, Any]],
    slot_state: dict[str, Any] | None,
    acceptance: dict[str, Any],
    service_kind: str | None = None,
    prior_state: PriorQuestionState | None = None,
    question_id: str | None = None,
    fingerprint: str | None = None,
) -> tuple[str, dict[str, Any]]:
    if service_kind is None:
        target_kinds = {
            item.get("scope", {}).get("service_kind")
            for item in target_assertions
            if item.get("scope", {}).get("service_kind") in SERVICE_KIND_ENUM
        }
        service_kind = next(iter(target_kinds), None) if len(target_kinds) == 1 else None
    if slot_state is None:
        basis = {
            "qualified_origin_groups": [],
            "qualified_assertion_ids": [],
            "independent_support_count": 0,
            "target_slot_effective_status": None,
            "conflict_pairs": [],
            "withdrawn_assertion_ids": [],
            "target_service_kind": service_kind,
        }
        # 5. no prior-state evidence => a question can never be "reopened".
        if prior_state is not None and question_id and prior_state.was_satisfied(
            question_id, fingerprint
        ):
            basis["reopened_from"] = prior_state.sources
            return "reopened", basis
        return "open", basis

    active_ids = set(slot_state.get("active_assertion_ids") or [])
    qualified = _qualified_supports(target_assertions, active_ids, acceptance, service_kind)
    # Reviewed assertions carry a canonical origin derived by the relation
    # builder.  Never count an untrusted hand-filled origin_group as a second
    # independent source.
    origin_groups = sorted(
        {item.get("derived_origin_group") or item["origin_group"] for item in qualified}
    )
    minimum = int(acceptance.get("minimum_independent_origin_groups", 1))
    basis = {
        "qualified_origin_groups": origin_groups,
        "qualified_assertion_ids": sorted(item["assertion_id"] for item in qualified),
        "independent_support_count": len(origin_groups),
        "target_slot_effective_status": slot_state.get("effective_status"),
        "conflict_pairs": slot_state.get("conflict_pairs") or [],
        "withdrawn_assertion_ids": slot_state.get("withdrawn_assertion_ids") or [],
        "target_service_kind": service_kind,
    }
    if slot_state.get("effective_status") == "conflicted":
        return "conflicted", basis
    if qualified and slot_state.get("limiting_assertion_ids"):
        return "partial", basis
    if len(origin_groups) >= minimum:
        return "satisfied", basis

    # 5. reopened requires real prior-state evidence that this exact question was
    # once satisfied. Absent that input the question stays open.
    if prior_state is not None and question_id and prior_state.was_satisfied(
        question_id, fingerprint
    ):
        basis["reopened_from"] = prior_state.sources
        basis["withdrawn_qualified_assertion_ids"] = sorted(
            item_id
            for item_id in slot_state.get("withdrawn_assertion_ids") or []
            if any(item["assertion_id"] == item_id for item in target_assertions)
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
    relation_contract: dict[str, Any] | None = None,
    registry: dict[str, dict[str, Any]] | None = None,
    prior_state: PriorQuestionState | None = None,
    return_deferred: bool | None = None,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], dict[str, int]]:
    """Return questions, or (questions, deferred_counts) when requested.

    Deferrals are counted explicitly so that "no question could honestly be
    generated" is reported instead of being hidden by a synthetic target.
    """
    # Preserve the historical four-argument API: it always returned only the
    # question list.  Callers that need the explicit deferral accounting opt in
    # with return_deferred=True; passing a relation contract or registry alone
    # must not silently change the return type.
    return_tuple = bool(return_deferred)
    if relation_contract is None:
        relation_contract = load_yaml(ROOT / "contracts/relation_types.yaml")
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
    deferred: dict[str, int] = defaultdict(int)

    for rule in rules_contract.get("rules") or []:
        if rule.get("trigger_relation_type") != "capability_matches_route":
            continue
        target_relation_type = rule["target_relation_type"]
        binding = rule.get("target_binding") or {}
        coverage_gate = rule.get("coverage_gate") or {}
        target_service_kinds = sorted(
            binding.get("target_service_kinds") or SERVICE_KIND_ENUM
        )
        accepted_kinds = set(rule.get("acceptance", {}).get("service_kind_acceptance") or [])
        if accepted_kinds:
            outside = sorted(set(target_service_kinds) - accepted_kinds)
            if outside:
                raise QuestionStateError(
                    f"{rule['rule_id']}: target_service_kinds {outside} are not accepted "
                    f"by the acceptance service_kind_acceptance"
                )
        for (subject_ref, profile_id), trigger_items in sorted(matches.items()):
            if profile_id not in set(rule.get("route_profile_ids") or []):
                continue
            profile = profiles.get(profile_id)
            if profile is None:
                raise QuestionStateError(f"rule targets unknown route profile: {profile_id}")
            object_ref = f"route_profile:{profile_id}"

            # 3. complete ACTUAL coverage gate.
            coverage_cells = actual_coverage_cells(
                assertions,
                subject_ref,
                profile_id,
                slot_states=slot_states,
            )
            group_cells = project_group_cells(assertions, profile_id)
            complete, requirement_groups, reason = evaluate_coverage(
                profile, coverage_cells, group_cells
            )
            if not complete:
                deferred[reason or "incomplete_actual_coverage"] += 1
                continue
            if coverage_gate.get("planned_counts_as_coverage", False):
                raise QuestionStateError(
                    "coverage_gate.planned_counts_as_coverage must stay false: a planned "
                    "match is not route capability"
                )

            # 4. bind real product identities; never synthesize a route slot.
            product_refs = candidate_product_refs(
                registry or {}, subject_ref, binding.get("product_ref_kind", "product")
            )
            if binding.get("product_ref_required", True) and not product_refs:
                deferred["no_resolvable_product_binding"] += 1
                continue

            for product_ref in product_refs:
                for service_kind in target_service_kinds:
                    scope = {
                        "route_profile_id": profile_id,
                        "product_ref": product_ref,
                        "service_kind": service_kind,
                    }
                    slot_id, target_identity, bind_reason = bind_target_slot(
                        relation_contract,
                        target_relation_type,
                        subject_ref,
                        object_ref,
                        scope,
                    )
                    if slot_id is None:
                        deferred[bind_reason or "target_slot_unbindable"] += 1
                        continue
                    # 4. one real slot only: no aggregation across products or
                    # service kinds, and no fallback to a route-level slot.
                    target_assertions = list(assertions_by_slot.get(slot_id) or [])
                    slot_state = states_by_id.get(slot_id)
                    fingerprint = question_fingerprint(
                        rule["rule_id"], subject_ref, profile_id, product_ref, service_kind
                    )
                    question_id = stable_id("GQ", fingerprint, length=12)
                    resolution_status, basis = compute_resolution(
                        target_assertions,
                        slot_state,
                        rule["acceptance"],
                        service_kind,
                        prior_state,
                        question_id,
                        fingerprint,
                    )
                    # H. On an initial run, an already satisfied target is not a
                    # missing-relation candidate.  Once a real prior snapshot
                    # knows the question, retain its satisfied row so the next
                    # snapshot can prove the lifecycle instead of deleting it.
                    if resolution_status == "satisfied" and not (
                        prior_state is not None
                        and prior_state.has_question(question_id, fingerprint)
                    ):
                        continue
                    company = subject_ref.split(":", 1)[-1]
                    basis["coverage"] = {
                        "coverage_modality": coverage_gate.get("coverage_modality", "actual"),
                        "covered_capability_cell_ids": sorted(coverage_cells),
                    }
                    question = {
                        "question_id": question_id,
                        "question_class": rule["question_class"],
                        "question_text": rule["question_template"].format(
                            company=company,
                            route_label=profile["label"],
                            product_ref=product_ref,
                            service_kind=service_kind,
                        ),
                        "display_parent": rule["display_parent"],
                        "depends_on": list(rule.get("depends_on") or []),
                        "generated_by": {
                            "rule_id": rule["rule_id"],
                            "reason": rule["generated_by_reason"],
                        },
                        "trigger_refs": sorted(item["assertion_id"] for item in trigger_items),
                        # 8. the target is a real slot: the identity scope that
                        # defines it is published next to the slot id.
                        "target": {
                            "slot_id": slot_id,
                            **target_identity,
                            "identity_scope": _identity_scope(
                                relation_contract, target_relation_type, scope
                            ),
                        },
                        "acceptance": rule["acceptance"],
                        "reopen_on": list(rule.get("reopen_on") or []),
                        "workflow_status": rule["initial_workflow_status"],
                        "resolution_status": resolution_status,
                        "dedupe_fingerprint": fingerprint,
                        "state_basis": basis,
                        "requirement_groups": requirement_groups,
                    }
                    if fingerprint in questions and questions[fingerprint] != question:
                        raise QuestionStateError(
                            f"non-deterministic duplicate question: {fingerprint}"
                        )
                    questions[fingerprint] = question

    result = sorted(questions.values(), key=lambda item: item["question_id"])
    allowed_workflow = set(rules_contract.get("workflow_status_enum") or [])
    allowed_resolution = set(rules_contract.get("resolution_status_enum") or [])
    for item in result:
        if item["workflow_status"] not in allowed_workflow:
            raise QuestionStateError(f"invalid workflow status: {item['workflow_status']}")
        if item["resolution_status"] not in allowed_resolution:
            raise QuestionStateError(f"invalid resolution status: {item['resolution_status']}")
    deferred_result = dict(sorted(deferred.items()))
    return (result, deferred_result) if return_tuple else result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assertion-index", type=Path, default=DEFAULT_ASSERTION_INDEX)
    parser.add_argument("--slot-states", type=Path, default=DEFAULT_SLOT_STATES)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--adapters", type=Path, default=DEFAULT_ADAPTERS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--contracts-dir", type=Path)
    parser.add_argument(
        "--extra-registry",
        type=Path,
        action="append",
        default=[],
        help="additional resolvable reference registry (product identities, test registry)",
    )
    parser.add_argument(
        "--previous-snapshot",
        type=Path,
        default=None,
        help="previous generated-questions projection; required before a question "
        "may be reported as reopened",
    )
    parser.add_argument(
        "--state-events",
        type=Path,
        default=None,
        help="append-only question state event log (question_id/from_status/to_status/at)",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="strict ISO query time the slot states were projected at",
    )
    parser.add_argument(
        "--modality",
        type=str,
        default=None,
        choices=["actual", "planned", "conditional", "unknown"],
        help="query modality the slot states were projected at",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    assertion_manifest, assertions = read_index_with_manifest(args.assertion_index)
    slot_manifest, slot_states = read_index_with_manifest(args.slot_states)
    contracts_dir = (args.contracts_dir or args.rules.resolve().parent).resolve()
    manifest = _require_same_build(
        assertion_manifest,
        slot_manifest,
        args.rules,
        args.adapters,
        assertion_rows=assertions,
        slot_rows=slot_states,
        relation_types_path=contracts_dir / "relation_types.yaml",
        extra_registry_paths=tuple(args.extra_registry),
    )
    # 6. strict query parameters, cross-checked against the projection.
    as_of = parse_iso_datetime(args.as_of) if args.as_of else None
    _require_query_matches_manifest(manifest, as_of, args.modality)
    relation_contract = load_yaml(contracts_dir / "relation_types.yaml")
    projection_root = contracts_dir.parent
    registry = build_reference_registry(projection_root, tuple(args.extra_registry))
    prior_state = PriorQuestionState.load(
        args.previous_snapshot,
        args.state_events,
        expected_manifest=manifest,
        rules_path=args.rules,
        adapters_path=args.adapters,
        relation_types_path=contracts_dir / "relation_types.yaml",
        extra_registry_paths=tuple(args.extra_registry),
        registry=registry,
        expected_as_of=as_of,
        expected_modality=args.modality,
    )
    questions, deferred = generate_diagnostic_questions(
        assertions,
        slot_states,
        load_yaml(args.rules),
        load_yaml(args.adapters),
        relation_contract=relation_contract,
        registry=registry,
        prior_state=prior_state,
        return_deferred=True,
    )
    # the projection root (parent of the directory holding the index)
    projection_root = args.assertion_index.resolve().parent.parent
    questions_manifest = {
        "snapshot_schema_version": "question_state_snapshot_v1",
        "build_id": manifest["build_id"],
        "data_hash": manifest["data_hash"],
        "assertion_data_hash": manifest["assertion_data_hash"],
        "slot_data_hash": manifest["slot_data_hash"],
        "assertion_count": manifest["assertion_count"],
        "slot_count": manifest["slot_count"],
        "as_of": manifest.get("as_of"),
        "modality": manifest.get("modality"),
        "question_count": len(questions),
        "questions_data_hash": hashlib.sha256(canonical_json(questions).encode("utf-8")).hexdigest(),
        "registries": list(manifest.get("registries") or []),
        # 10. relative, content-addressed contract references only.
        "contracts": {
            "question_generation_rules.yaml": _contract_ref(args.rules, projection_root),
            "relation_adapters.yaml": _contract_ref(args.adapters, projection_root),
            "relation_types.yaml": _contract_ref(
                contracts_dir / "relation_types.yaml", projection_root
            ),
        },
        "deferred": deferred,
        "prior_state": {
            "snapshot": _contract_ref(args.previous_snapshot, projection_root)
            if args.previous_snapshot
            else None,
            "state_events": _contract_ref(args.state_events, projection_root)
            if args.state_events
            else None,
        },
    }
    write_jsonl(args.output, questions, questions_manifest)
    counts: dict[str, int] = defaultdict(int)
    for item in questions:
        counts[item["resolution_status"]] += 1
    print(
        f"diagnostic questions: {len(questions)} -> {args.output} "
        f"({dict(sorted(counts.items()))}) [build {manifest['build_id']}]"
        + (f" deferred={deferred}" if deferred else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
