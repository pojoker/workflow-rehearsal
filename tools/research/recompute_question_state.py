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
    reducer_contract_compatibility,
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


def target_identity_hash(target: dict[str, Any]) -> str:
    """Content hash of the exact target identity, excluding resolution state."""
    identity = {
        "relation_type": target.get("relation_type"),
        "subject_ref": target.get("subject_ref"),
        "object_ref": target.get("object_ref"),
        "identity_scope": target.get("identity_scope") or {},
    }
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()


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
    if manifest.get("projection_query_hash") is not None and not _SHA256_RE.fullmatch(
        manifest["projection_query_hash"]
    ):
        raise QuestionStateError(
            f"{label} manifest projection_query_hash is not a SHA-256 hash"
        )
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

    relation_artifacts = manifest.get("relation_artifacts")
    if relation_artifacts is not None:
        if not isinstance(relation_artifacts, dict) or not set(relation_artifacts) <= {
            "assertion_index",
            "slot_states",
        }:
            raise QuestionStateError(
                f"{label} manifest relation_artifacts has unsupported names"
            )
        for name, ref in relation_artifacts.items():
            if not isinstance(ref, dict) or set(ref) != {"path", "sha256", "row_count"}:
                raise QuestionStateError(
                    f"{label} manifest relation artifact {name} is malformed"
                )
            path = ref["path"]
            if (
                not isinstance(path, str)
                or not path
                or Path(path).is_absolute()
                or ".." in Path(path).parts
            ):
                raise QuestionStateError(
                    f"{label} manifest relation artifact {name} path must be relative"
                )
            if not isinstance(ref["sha256"], str) or not _SHA256_RE.fullmatch(
                ref["sha256"]
            ):
                raise QuestionStateError(
                    f"{label} manifest relation artifact {name} hash is malformed"
                )
            if not isinstance(ref["row_count"], int) or ref["row_count"] < 0:
                raise QuestionStateError(
                    f"{label} manifest relation artifact {name} row_count is malformed"
                )


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
        "projection_query_hash",
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
    if rules_path is not None and adapters_path is not None and relation_types_path is not None:
        try:
            computed_compatibility = reducer_contract_compatibility(
                load_yaml(relation_types_path),
                load_yaml(adapters_path),
                load_yaml(rules_path),
            )
        except (OSError, RelationIndexError) as exc:
            raise QuestionStateError(
                "reducer contract compatibility cannot be computed from current files"
            ) from exc
        for label, candidate in (
            ("assertion index", assertion_manifest),
            ("slot state", slot_manifest),
        ):
            if candidate.get("contract_compatibility") != computed_compatibility:
                raise QuestionStateError(
                    f"{label} manifest reducer contract compatibility is stale or forged"
                )
    return assertion_manifest


def _resolve_relative_ref(
    ref: dict[str, Any], *, path: Path, history_base: Path | None
) -> Path:
    """Resolve a content reference without allowing absolute/path-traversal refs."""
    if not isinstance(ref, dict) or set(ref) - {"path", "sha256", "row_count"}:
        raise QuestionStateError(f"{path}: malformed relation artifact reference")
    ref_path = ref.get("path")
    if (
        not isinstance(ref_path, str)
        or not ref_path
        or Path(ref_path).is_absolute()
        or ".." in Path(ref_path).parts
    ):
        raise QuestionStateError(f"{path}: relation artifact reference path must be relative")
    candidates: list[Path] = []
    for base in (
        history_base,
        path.resolve().parent.parent,
        path.resolve().parent,
    ):
        if base is None:
            continue
        candidate = base / ref_path
        if candidate not in candidates:
            candidates.append(candidate)
    existing = next((candidate for candidate in candidates if candidate.is_file()), None)
    if existing is None:
        raise QuestionStateError(
            f"{path}: referenced relation artifact {ref_path!r} is unavailable"
        )
    return existing


def _validate_relation_artifacts(
    manifest: dict[str, Any],
    *,
    snapshot_path: Path,
    rules_path: Path | None,
    adapters_path: Path | None,
    relation_types_path: Path | None,
    extra_registry_paths: Iterable[Path],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Load and content-check the relation artifacts that produced a snapshot.

    A question row is a projection, not evidence of how it was computed.  The
    snapshot therefore binds the exact assertion/slot row sets used to derive
    it.  Their own manifests and hashes are checked before any state replay.
    """
    refs = manifest.get("relation_artifacts")
    if not isinstance(refs, dict) or set(refs) != {"assertion_index", "slot_states"}:
        raise QuestionStateError(
            f"{snapshot_path}: snapshot must bind assertion_index and slot_states artifacts"
        )
    for name, ref in refs.items():
        if not isinstance(ref, dict) or set(ref) != {"path", "sha256", "row_count"}:
            raise QuestionStateError(
                f"{snapshot_path}: relation artifact {name} ref must contain path, sha256, row_count"
            )
        if not isinstance(ref["sha256"], str) or not _SHA256_RE.fullmatch(ref["sha256"]):
            raise QuestionStateError(
                f"{snapshot_path}: relation artifact {name} row hash is malformed"
            )
        if not isinstance(ref["row_count"], int) or ref["row_count"] < 0:
            raise QuestionStateError(
                f"{snapshot_path}: relation artifact {name} row_count is malformed"
            )

    history_base = (
        relation_types_path.resolve().parent.parent
        if relation_types_path is not None
        else rules_path.resolve().parent.parent
        if rules_path is not None
        else None
    )
    loaded: dict[str, tuple[dict[str, Any], list[dict[str, Any]], Path]] = {}
    for name in ("assertion_index", "slot_states"):
        artifact_path = _resolve_relative_ref(
            refs[name], path=snapshot_path, history_base=history_base
        )
        artifact_manifest, rows = read_index_with_manifest(artifact_path)
        if artifact_manifest is None:
            raise QuestionStateError(
                f"{snapshot_path}: relation artifact {name} has no build manifest"
            )
        _validate_manifest_shape(artifact_manifest, f"relation artifact {name}")
        expected_hash = hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()
        if (
            refs[name]["row_count"] != len(rows)
            or refs[name]["sha256"] != expected_hash
        ):
            raise QuestionStateError(
                f"{snapshot_path}: relation artifact {name} rows do not match its bound ref"
            )
        loaded[name] = (artifact_manifest, rows, artifact_path)

    assertion_manifest, assertions, _ = loaded["assertion_index"]
    slot_manifest, states, _ = loaded["slot_states"]
    _require_same_build(
        assertion_manifest,
        slot_manifest,
        rules_path,
        adapters_path,
        assertion_rows=assertions,
        slot_rows=states,
        relation_types_path=relation_types_path,
        extra_registry_paths=extra_registry_paths,
    )
    comparable_keys = (
        "build_id",
        "data_hash",
        "assertion_data_hash",
        "slot_data_hash",
        "assertion_count",
        "slot_count",
        "as_of",
        "modality",
        "projection_query_hash",
        "contracts",
        "registries",
        "contract_compatibility",
    )
    for key in comparable_keys:
        if assertion_manifest.get(key) != manifest.get(key):
            raise QuestionStateError(
                f"{snapshot_path}: snapshot relation artifact binding disagrees on {key}"
            )
        if slot_manifest.get(key) != manifest.get(key):
            raise QuestionStateError(
                f"{snapshot_path}: snapshot relation artifact binding disagrees on {key}"
            )
    return assertions, states, assertion_manifest


def _assert_replayed_snapshot_matches(
    snapshot_path: Path,
    stored_rows: list[dict[str, Any]],
    replayed_rows: list[dict[str, Any]],
) -> None:
    """Compare the semantic output of the reducer with a stored snapshot."""
    stored_by_id = {row.get("question_id"): row for row in stored_rows}
    replayed_by_id = {row.get("question_id"): row for row in replayed_rows}
    if set(stored_by_id) != set(replayed_by_id):
        raise QuestionStateError(
            f"{snapshot_path}: snapshot question set does not match reducer replay"
        )
    fields = (
        "question_id",
        "dedupe_fingerprint",
        "target_identity_hash",
        "target",
        "rule_id",
        "rule_version",
        "question_class",
        "workflow_status",
        "resolution_status",
        "transition_cause_assertion_ids",
    )
    for question_id, stored in stored_by_id.items():
        replayed = replayed_by_id[question_id]
        for field in fields:
            if stored.get(field) != replayed.get(field):
                raise QuestionStateError(
                    f"{snapshot_path}: snapshot question {question_id!r} field {field!r} "
                    "does not match reducer replay"
                )


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
        records: dict[str, dict[str, Any]] | None = None,
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
        # Full validated question rows are retained for cross-build identity
        # and transition checks; status-only compatibility callers continue to
        # work through _statuses/_known_questions.
        self._records: dict[str, dict[str, Any]] = dict(records or {})

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
        expected_parent_snapshot_hash: str | None = None,
        current_contract_compatibility: dict[str, Any] | None = None,
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
        # Snapshot lineage is part of the trusted input, not decorative
        # metadata.  A question snapshot is portable, but whenever its parent
        # is present the parent reference/hash pair must remain internally
        # consistent.  The actual parent file is verified below when it is
        # available beside the snapshot.
        current_build_id = manifest.get("current_build_id")
        if kind == "snapshot":
            if not isinstance(current_build_id, str) or not re.fullmatch(
                r"[0-9A-F]{24}", current_build_id
            ):
                raise QuestionStateError(
                    f"{path}: previous snapshot current_build_id is missing or malformed"
                )
            if current_build_id != manifest.get("build_id"):
                raise QuestionStateError(
                    f"{path}: previous snapshot current_build_id does not match build_id"
                )
        parent_hash = manifest.get("parent_snapshot_hash")
        previous_build_id = manifest.get("previous_build_id")
        if parent_hash is not None and not _SHA256_RE.fullmatch(str(parent_hash)):
            raise QuestionStateError(
                f"{path}: previous {kind} parent_snapshot_hash is malformed"
            )
        if previous_build_id is not None and parent_hash is None:
            raise QuestionStateError(
                f"{path}: previous {kind} previous_build_id requires parent_snapshot_hash"
            )
        parent_rows_hash = manifest.get("parent_snapshot_questions_data_hash")
        if parent_rows_hash is not None and not _SHA256_RE.fullmatch(str(parent_rows_hash)):
            raise QuestionStateError(
                f"{path}: previous {kind} parent snapshot rows hash is malformed"
            )
        prior_state = manifest.get("prior_state")
        parent_ref = prior_state.get("snapshot") if isinstance(prior_state, dict) else None
        if parent_hash is None:
            if previous_build_id is not None or parent_rows_hash is not None or parent_ref is not None:
                raise QuestionStateError(
                    f"{path}: previous {kind} has parent lineage fields without a parent snapshot"
                )
        else:
            if previous_build_id is None or parent_rows_hash is None:
                raise QuestionStateError(
                    f"{path}: previous {kind} parent_snapshot_hash requires previous_build_id "
                    "and parent_snapshot_questions_data_hash"
                )
            if not isinstance(parent_ref, dict) or set(parent_ref) != {"path", "sha256"}:
                raise QuestionStateError(
                    f"{path}: previous {kind} prior_state.snapshot must be a content reference"
                )
            ref_path = parent_ref.get("path")
            ref_hash = parent_ref.get("sha256")
            if (
                not isinstance(ref_path, str)
                or not ref_path
                or Path(ref_path).is_absolute()
                or ".." in Path(ref_path).parts
                or not isinstance(ref_hash, str)
                or not _SHA256_RE.fullmatch(ref_hash)
                or ref_hash != parent_hash
            ):
                raise QuestionStateError(
                    f"{path}: previous {kind} parent snapshot reference does not match "
                    "parent_snapshot_hash"
                )
        if expected_parent_snapshot_hash is not None:
            if manifest.get("parent_snapshot_hash") != expected_parent_snapshot_hash:
                raise QuestionStateError(
                    f"{path}: previous {kind} parent_snapshot_hash does not match expected history"
                )
        history_base = (
            relation_types_path.resolve().parent.parent
            if relation_types_path is not None
            else rules_path.resolve().parent.parent
            if rules_path is not None
            else None
        )
        if parent_hash is not None and isinstance(parent_ref, dict):
            # Resolve a relative parent reference against the common projection
            # root first (the normal CLI layout), then the snapshot's parents.
            # If an artifact was copied without its parent, metadata validation
            # above still protects the chain; when the parent is present, verify
            # the recorded file hash and its row hash as well.
            candidate_paths: list[Path] = []
            for base in (
                history_base,
                path.resolve().parent.parent,
                path.resolve().parent,
            ):
                if base is None:
                    continue
                candidate = base / parent_ref["path"]
                if candidate not in candidate_paths:
                    candidate_paths.append(candidate)
            existing_parent = next(
                (candidate for candidate in candidate_paths if candidate.is_file()), None
            )
            if existing_parent is None:
                raise QuestionStateError(
                    f"{path}: previous {kind} parent snapshot file is unavailable; "
                    "history cannot be verified"
                )
            if _file_hash(existing_parent) != parent_hash:
                raise QuestionStateError(
                    f"{path}: previous {kind} parent snapshot file hash does not match"
                )
            parent_manifest, parent_rows = read_index_with_manifest(existing_parent)
            if (
                parent_manifest is None
                or parent_manifest.get("questions_data_hash") != parent_rows_hash
            ):
                raise QuestionStateError(
                    f"{path}: previous {kind} parent snapshot rows hash does not match"
                )
            if kind == "snapshot" and parent_manifest.get("current_build_id") != previous_build_id:
                raise QuestionStateError(
                    f"{path}: previous snapshot previous_build_id does not match its parent snapshot"
                )
            if kind == "snapshot":
                parent_as_of = parent_manifest.get("as_of")
                current_as_of = manifest.get("as_of")
                if (
                    isinstance(parent_as_of, str)
                    and isinstance(current_as_of, str)
                    and parse_iso_datetime(parent_as_of) > parse_iso_datetime(current_as_of)
                ):
                    raise QuestionStateError(
                        f"{path}: previous snapshot as_of is later than its child snapshot"
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
        same_relation_build = (
            expected_manifest is not None
            and manifest.get("build_id") == expected_manifest.get("build_id")
            and manifest.get("projection_query_hash")
            == expected_manifest.get("projection_query_hash")
        )
        if expected_as_of is not _UNSET:
            expected_time = (
                parse_iso_datetime(expected_as_of)
                if expected_as_of is not None
                else None
            )
            previous_time = manifest.get("as_of")
            if same_relation_build:
                if previous_time != expected_time:
                    raise QuestionStateError(
                        f"{path}: previous {kind} as_of does not match the requested query"
                    )
            elif expected_time is None or previous_time is None:
                # Temporal history is only comparable when both builds have an
                # explicit query boundary.  None is never interpreted as now.
                raise QuestionStateError(
                    f"{path}: cross-build temporal history requires explicit as_of on both builds"
                )
            elif parse_iso_datetime(previous_time) > expected_time:
                raise QuestionStateError(
                    f"{path}: previous {kind} as_of is later than the current query"
                )
        if expected_modality is not _UNSET:
            if manifest.get("modality") != expected_modality:
                raise QuestionStateError(
                    f"{path}: previous {kind} modality does not match the requested query"
                )
        computed_current_compatibility: dict[str, Any] | None = None
        if rules_path is not None and adapters_path is not None and relation_types_path is not None:
            try:
                computed_current_compatibility = reducer_contract_compatibility(
                    load_yaml(relation_types_path),
                    load_yaml(adapters_path),
                    load_yaml(rules_path),
                )
            except (OSError, RelationIndexError) as exc:
                raise QuestionStateError(
                    f"{path}: current reducer contract compatibility cannot be computed"
                ) from exc
            if manifest.get("contract_compatibility") != computed_current_compatibility:
                raise QuestionStateError(
                    f"{path}: previous {kind} reducer contract compatibility is stale or forged"
                )
            if (
                expected_manifest is not None
                and expected_manifest.get("contract_compatibility")
                != computed_current_compatibility
            ):
                raise QuestionStateError(
                    f"{path}: current relation build reducer contract compatibility is stale or forged"
                )
        elif current_contract_compatibility is not None:
            computed_current_compatibility = current_contract_compatibility
        if expected_manifest is not None and same_relation_build:
            # A same-build replay is still strict: the snapshot must describe
            # the exact projection it was generated from.
            for key in (
                "build_id",
                "data_hash",
                "assertion_data_hash",
                "slot_data_hash",
                "assertion_count",
                "slot_count",
                "as_of",
                "modality",
                "projection_query_hash",
                "contracts",
                "registries",
                "contract_compatibility",
            ):
                if manifest.get(key) != expected_manifest.get(key):
                    raise QuestionStateError(
                        f"{path}: previous {kind} belongs to a different relation build ({key})"
                    )
        elif expected_manifest is not None:
            # A legitimate historical snapshot is allowed to come from a
            # different data build.  Bind its lineage and reducer contract,
            # rather than comparing data hashes that are expected to change.
            if manifest.get("current_build_id") not in (None, manifest.get("build_id")):
                raise QuestionStateError(
                    f"{path}: previous {kind} current_build_id does not match its relation build"
                )
            previous_compatibility = manifest.get("contract_compatibility")
            if not isinstance(previous_compatibility, dict) or not isinstance(
                computed_current_compatibility, dict
            ):
                raise QuestionStateError(
                    f"{path}: cross-build {kind} is missing reducer contract compatibility"
                )
            if previous_compatibility != computed_current_compatibility:
                raise QuestionStateError(
                    f"{path}: cross-build {kind} reducer contract is incompatible"
                )

        def verify(name: str, candidate: Path | None) -> None:
            if (
                candidate is not None
                and same_relation_build
                and manifest["contracts"][name]["sha256"] != _file_hash(candidate)
            ):
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
        expected_parent_snapshot_hash: str | None = None,
        current_contract_compatibility: dict[str, Any] | None = None,
        current_assertions: list[dict[str, Any]] | None = None,
        _replay_stack: tuple[str, ...] = (),
    ) -> "PriorQuestionState":
        """A previous generated-questions projection (question_id -> status).

        A bare line saying ``satisfied`` is not a historical source.  The
        snapshot must be a real generated projection with a manifest, matching
        build/query/contract hashes, and complete target identities.
        """
        extra_registry_paths = tuple(extra_registry_paths)
        resolved_snapshot = path.resolve()
        if str(resolved_snapshot) in _replay_stack:
            raise QuestionStateError(
                f"{path}: snapshot parent lineage contains a cycle"
            )
        replay_stack = (*_replay_stack, str(resolved_snapshot))
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
            expected_parent_snapshot_hash=expected_parent_snapshot_hash,
            current_contract_compatibility=current_contract_compatibility,
        )
        if manifest.get("snapshot_schema_version") != "question_state_snapshot_v1":
            raise QuestionStateError(f"{path}: snapshot_schema_version is missing or unsupported")
        if registry is None:
            raise QuestionStateError(
                f"{path}: previous snapshot validation requires the current reference registry"
            )
        if not isinstance(manifest.get("as_of"), str):
            raise QuestionStateError(
                f"{path}: previous snapshot replay requires an explicit as_of"
            )
        if manifest.get("question_count") != len(rows):
            raise QuestionStateError(f"{path}: question_count does not match snapshot rows")
        # A relation build can keep the same data-derived build_id while its
        # temporal projection changes (for example T1 -> T2).  Such a snapshot
        # is still a different historical projection and must receive the
        # cross-build identity/lineage checks below.
        cross_build = (
            expected_manifest is not None
            and (
                manifest.get("build_id") != expected_manifest.get("build_id")
                or manifest.get("projection_query_hash")
                != expected_manifest.get("projection_query_hash")
            )
        )
        expected_rows_hash = hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()
        if manifest.get("questions_data_hash") != expected_rows_hash:
            raise QuestionStateError(f"{path}: snapshot rows do not match questions_data_hash")
        snapshot_content_hash = manifest.get("snapshot_content_hash")
        if snapshot_content_hash is not None and snapshot_content_hash != expected_rows_hash:
            raise QuestionStateError(
                f"{path}: snapshot_content_hash does not match snapshot rows"
            )
        if cross_build and snapshot_content_hash is None:
            raise QuestionStateError(
                f"{path}: cross-build snapshot needs snapshot_content_hash"
            )
        allowed = {"open", "partial", "blocked", "satisfied", "reopened", "conflicted"}
        statuses: dict[str, str] = {}
        records: dict[str, dict[str, Any]] = {}
        known: set[str] = set()
        fingerprints: set[str] = set()
        relation_contract = load_yaml(
            relation_types_path or DEFAULT_ADAPTERS.parent / "relation_types.yaml"
        )
        current_assertions_by_id: dict[str, dict[str, Any]] | None = None
        if current_assertions is not None:
            current_assertions_by_id = {}
            for assertion in current_assertions:
                if not isinstance(assertion, dict):
                    raise QuestionStateError(
                        f"{path}: current assertion index contains a non-object row"
                    )
                assertion_id = assertion.get("assertion_id")
                if not isinstance(assertion_id, str) or not assertion_id:
                    raise QuestionStateError(
                        f"{path}: current assertion index contains an assertion without an ID"
                    )
                if assertion_id in current_assertions_by_id:
                    raise QuestionStateError(
                        f"{path}: current assertion index contains duplicate assertion ID "
                        f"{assertion_id!r}"
                    )
                current_assertions_by_id[assertion_id] = assertion
        rule_map: dict[str, dict[str, Any]] = {}
        if rules_path is not None and rules_path.is_file():
            rule_map = {
                rule.get("rule_id"): rule
                for rule in (load_yaml(rules_path).get("rules") or [])
                if rule.get("rule_id")
            }

        # The stored question rows are not trusted as evidence of their own
        # resolution.  Re-load the exact relation artifacts named by this
        # snapshot and replay the reducer against them before accepting the
        # predecessor state.
        replay_assertions, replay_states, replay_relation_manifest = (
            _validate_relation_artifacts(
                manifest,
                snapshot_path=path,
                rules_path=rules_path,
                adapters_path=adapters_path,
                relation_types_path=relation_types_path,
                extra_registry_paths=extra_registry_paths,
            )
        )
        replay_prior: PriorQuestionState | None = None
        prior_state_manifest = manifest.get("prior_state")
        prior_snapshot_ref = (
            prior_state_manifest.get("snapshot")
            if isinstance(prior_state_manifest, dict)
            else None
        )
        if prior_snapshot_ref is not None:
            history_base = (
                relation_types_path.resolve().parent.parent
                if relation_types_path is not None
                else rules_path.resolve().parent.parent
                if rules_path is not None
                else None
            )
            parent_path = _resolve_relative_ref(
                prior_snapshot_ref, path=path, history_base=history_base
            )
            parent_manifest, _parent_rows = read_index_with_manifest(parent_path)
            if parent_manifest is None:
                raise QuestionStateError(
                    f"{path}: parent snapshot has no build manifest"
                )
            parent_assertions, _parent_states, parent_relation_manifest = (
                _validate_relation_artifacts(
                    parent_manifest,
                    snapshot_path=parent_path,
                    rules_path=rules_path,
                    adapters_path=adapters_path,
                    relation_types_path=relation_types_path,
                    extra_registry_paths=extra_registry_paths,
                )
            )
            replay_prior = cls.from_snapshot(
                parent_path,
                expected_manifest=parent_relation_manifest,
                rules_path=rules_path,
                adapters_path=adapters_path,
                relation_types_path=relation_types_path,
                extra_registry_paths=extra_registry_paths,
                registry=registry,
                expected_as_of=parent_manifest.get("as_of"),
                expected_modality=parent_manifest.get("modality"),
                current_contract_compatibility=parent_manifest.get(
                    "contract_compatibility"
                ),
                current_assertions=parent_assertions,
                _replay_stack=replay_stack,
            )
        replayed_questions, _replay_deferred = generate_diagnostic_questions(
            replay_assertions,
            replay_states,
            load_yaml(rules_path),
            load_yaml(adapters_path),
            relation_contract=load_yaml(relation_types_path),
            registry=registry,
            prior_state=replay_prior,
            return_deferred=True,
            as_of=manifest["as_of"],
        )
        _assert_replayed_snapshot_matches(path, rows, replayed_questions)
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
            for field in ("slot_id", "relation_type", "subject_ref", "object_ref"):
                if not target.get(field):
                    raise QuestionStateError(f"{path}:{index}: target is missing {field}")
            relation_type = target["relation_type"]
            if relation_type == "company_serves_route":
                for field in ("route_profile_id", "product_ref", "service_kind"):
                    if not target.get(field):
                        raise QuestionStateError(f"{path}:{index}: target is missing {field}")
                if target["service_kind"] not in SERVICE_KIND_ENUM:
                    raise QuestionStateError(
                        f"{path}:{index}: target relation/service identity is invalid"
                    )
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
                    or product.get("registry_id")
                    not in set(getattr(registry, "bound_registry_ids", set()))
                ):
                    raise QuestionStateError(
                        f"{path}:{index}: target product is not present in the "
                        "validated current product registry"
                    )
                expected_identity_scope = {
                    "route_profile_id": target["route_profile_id"],
                    "product_ref": target["product_ref"],
                    "service_kind": target["service_kind"],
                }
                expected_fp = {
                    "target_relation_type": "company_serves_route",
                    "subject_ref": target["subject_ref"],
                    "route_profile_id": target["route_profile_id"],
                    "product_ref": target["product_ref"],
                    "service_kind": target["service_kind"],
                }
                identity_scope = expected_identity_scope
                identity_scope_input = {
                    "route_profile_id": target["route_profile_id"],
                    "product_ref": target["product_ref"],
                    "service_kind": target["service_kind"],
                }
            elif relation_type == "product_has_lifecycle_stage":
                for field in (
                    "program_id",
                    "primary_subject_id",
                    "lifecycle_stage",
                ):
                    if not target.get(field):
                        raise QuestionStateError(f"{path}:{index}: lifecycle target is missing {field}")
                if target["object_ref"] != f"lifecycle_stage:{target['lifecycle_stage']}":
                    raise QuestionStateError(
                        f"{path}:{index}: lifecycle object_ref and lifecycle_stage disagree"
                    )
                expected_identity_scope = {
                    "program_id": target["program_id"],
                    "primary_subject_id": target["primary_subject_id"],
                    "lifecycle_stage": target["lifecycle_stage"],
                }
                expected_fp = {
                    "target_relation_type": "product_has_lifecycle_stage",
                    "subject_ref": target["subject_ref"],
                    "program_id": target["program_id"],
                    "object_ref": target["object_ref"],
                }
                identity_scope = expected_identity_scope
                identity_scope_input = {
                    "program_id": target["program_id"],
                    "primary_subject_id": target["primary_subject_id"],
                    "lifecycle_stage": target["lifecycle_stage"],
                }
            else:
                raise QuestionStateError(
                    f"{path}:{index}: unsupported snapshot target relation {relation_type!r}"
                )
            if target.get("identity_scope") != identity_scope:
                raise QuestionStateError(
                    f"{path}:{index}: target identity_scope is incomplete or inconsistent"
                )
            identity = relation_slot_identity(
                relation_type,
                target["subject_ref"],
                target["object_ref"],
                identity_scope_input,
                relation_contract,
            )
            if target["slot_id"] != stable_id("RS", identity):
                raise QuestionStateError(
                    f"{path}:{index}: target slot_id is not identity-derived"
                )

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
                for field, expected in expected_fp.items()
            ):
                raise QuestionStateError(
                    f"{path}:{index}: dedupe_fingerprint does not bind the target identity"
                )
            expected_question_id = stable_id("GQ", fingerprint, length=12)
            if question_id != expected_question_id:
                raise QuestionStateError(
                    f"{path}:{index}: question_id is not derived from dedupe_fingerprint"
                )
            if question_id in known:
                raise QuestionStateError(f"{path}:{index}: duplicate question_id")
            known.add(question_id)
            statuses[question_id] = status
            statuses[fingerprint] = status

            current_target_hash = target_identity_hash(target)
            if row.get("target_identity_hash") is not None and row["target_identity_hash"] != current_target_hash:
                raise QuestionStateError(
                    f"{path}:{index}: target_identity_hash does not bind the target"
                )
            if cross_build and not row.get("target_identity_hash"):
                raise QuestionStateError(
                    f"{path}:{index}: cross-build snapshot needs target_identity_hash"
                )
            rule_id = row.get("rule_id") or (row.get("generated_by") or {}).get("rule_id")
            rule_version = row.get("rule_version")
            if cross_build:
                if not isinstance(rule_id, str) or not rule_id or rule_version is None:
                    raise QuestionStateError(
                        f"{path}:{index}: cross-build snapshot needs rule_id and rule_version"
                    )
                current_rule = rule_map.get(rule_id)
                if current_rule is None or current_rule.get("rule_version") != rule_version:
                    raise QuestionStateError(
                        f"{path}:{index}: question rule version is incompatible across builds"
                    )
            causes = row.get("transition_cause_assertion_ids", [])
            if not isinstance(causes, list) or any(
                not isinstance(value, str) or not value for value in causes
            ):
                raise QuestionStateError(
                    f"{path}:{index}: transition_cause_assertion_ids must be a list of IDs"
                )
            if cross_build and "transition_cause_assertion_ids" not in row:
                raise QuestionStateError(
                    f"{path}:{index}: cross-build snapshot needs transition cause assertion IDs"
                )
            if current_assertions_by_id is not None:
                for cause_id in causes:
                    cause = current_assertions_by_id.get(cause_id)
                    if cause is None:
                        raise QuestionStateError(
                            f"{path}:{index}: transition cause assertion {cause_id!r} "
                            "is not present in the current assertion index"
                        )
                    previous_as_of = manifest.get("as_of")
                    if not isinstance(previous_as_of, str) or not is_active_at_as_of(
                        cause, previous_as_of
                    ):
                        raise QuestionStateError(
                            f"{path}:{index}: transition cause assertion {cause_id!r} "
                            "was not effective at the previous snapshot as_of"
                        )
                    previous_modality = manifest.get("modality")
                    if previous_modality is not None and cause.get("modality") != previous_modality:
                        raise QuestionStateError(
                            f"{path}:{index}: transition cause assertion {cause_id!r} "
                            "does not match the previous snapshot modality"
                        )
                    # An assertion from another relation, slot, or exact target
                    # is not a valid explanation for this question's transition.
                    # Checking both slot_id and the endpoints prevents a stale
                    # or hand-edited slot identifier from laundering an unrelated
                    # assertion into the history chain.
                    if any(
                        (
                            cause.get("slot_id") != target["slot_id"],
                            cause.get("relation_type") != relation_type,
                            cause.get("subject_ref") != target["subject_ref"],
                            cause.get("object_ref") != target["object_ref"],
                        )
                    ):
                        raise QuestionStateError(
                            f"{path}:{index}: transition cause assertion {cause_id!r} "
                            "does not belong to the question target slot"
                        )
            records[question_id] = {
                "question_id": question_id,
                "fingerprint": fingerprint,
                "status": status,
                "target_identity_hash": current_target_hash,
                "rule_id": rule_id,
                "rule_version": rule_version,
                "transition_cause_assertion_ids": list(causes),
            }
        return cls(
            statuses=statuses,
            known_questions=known | set(statuses),
            sources=[f"snapshot:{path.name}"],
            metadata=manifest,
            records=records,
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
        expected_parent_snapshot_hash: str | None = None,
        current_contract_compatibility: dict[str, Any] | None = None,
        current_assertions: list[dict[str, Any]] | None = None,
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
            expected_parent_snapshot_hash=expected_parent_snapshot_hash,
            current_contract_compatibility=current_contract_compatibility,
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

    def status_for(self, question_id: str, fingerprint: str | None = None) -> str | None:
        """Return the validated predecessor status for transition recording."""
        return self._statuses.get(question_id) or (
            self._statuses.get(fingerprint) if fingerprint else None
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
# Capability overlap leads (the route-service rule is deliberately lead-only)
# ---------------------------------------------------------------------------
def _profile_required_cells(
    profile: dict[str, Any],
    assertions: list[dict[str, Any]],
) -> set[str]:
    """Return the exact cells declared by a frozen profile.

    This is a reporting surface only.  It deliberately does not turn a cell
    intersection into a route-capability assertion or a company-serves-route
    assertion.  Keeping this helper separate from ``evaluate_coverage`` makes
    that boundary visible to callers and to the production CLI.
    """
    declared = {
        cell
        for group in profile.get("requirement_groups") or []
        for cell in group.get("capability_cell_ids") or []
    }
    if declared:
        return declared
    # UNKNOWN profiles have no exact requirement semantics and therefore have
    # no honest unmatched-cell denominator.
    return set()


def _profile_unmatched_cells(
    profile: dict[str, Any], matched_cells: set[str]
) -> set[str]:
    """Return deficits using the profile's declared all_of/one_of semantics.

    A raw union of declared cells is misleading for an alternative group: if
    C1 satisfies ``one_of(C1, C4)``, C4 is not an outstanding requirement.  The
    lead reports only cells that still block the frozen profile's declared
    coverage, while remaining explicitly non-assertive about route service.
    """
    unmatched: set[str] = set()
    for group in profile.get("requirement_groups") or []:
        cells = set(group.get("capability_cell_ids") or [])
        kind = group.get("kind")
        if kind == "all_of":
            unmatched.update(cells - matched_cells)
        elif kind == "one_of":
            if not cells & matched_cells:
                unmatched.update(cells)
        else:
            # The route-profile contract validator rejects unknown group kinds;
            # keep this conservative for direct API callers.
            unmatched.update(cells - matched_cells)
    return unmatched


def generate_relation_leads(
    assertions: list[dict[str, Any]],
    slot_states: list[dict[str, Any]] | None,
    rules_contract: dict[str, Any],
    adapters_contract: dict[str, Any],
    relation_contract: dict[str, Any] | None = None,
    *,
    as_of: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Aggregate capability-cell overlaps into observable, non-assertive leads.

    The old route rule used the same overlap as a predicate for a formal
    ``company_serves_route`` question.  The pilot now exposes the overlap as a
    lead, retaining actual/planned coverage and the cells still unmatched.  A
    lead is not a claim that the company has the route capability, and this
    function never emits a formal route-service question.
    """
    if as_of is not None:
        as_of = parse_iso_datetime(as_of)
    if relation_contract is None:
        relation_contract = load_yaml(ROOT / "contracts/relation_types.yaml")
    profiles = {
        item["route_profile_id"]: item
        for item in adapters_contract.get("route_profiles") or []
        if item.get("route_profile_id")
    }
    # State projections are authoritative where supplied.  A direct caller can
    # still pass no projection, in which case the defensive time filter is
    # applied below.
    states_by_id = {row["slot_id"]: row for row in (slot_states or [])}
    has_projection = slot_states is not None
    active_by_slot = {
        slot_id: set(row.get("active_assertion_ids") or [])
        for slot_id, row in states_by_id.items()
    }
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in assertions:
        if (
            item.get("relation_type") != "capability_matches_route"
            or item.get("epistemic_status") != "derived_candidate"
            or item.get("polarity") != "supporting"
        ):
            continue
        profile_id = item.get("scope", {}).get("route_profile_id")
        if not profile_id or profile_id not in profiles:
            continue
        if has_projection:
            if item["assertion_id"] not in active_by_slot.get(item["slot_id"], set()):
                continue
        elif as_of is not None and not is_active_at_as_of(item, as_of):
            continue
        grouped[(item["subject_ref"], profile_id)].append(item)

    experimental_rule = next(
        (
            rule
            for rule in rules_contract.get("rules") or []
            if rule.get("rule_id") == "QGR-CAPABILITY-WITHOUT-EXACT-SERVICE-V1"
        ),
        {},
    )
    admission_status = experimental_rule.get("admission_status", "not_admitted")
    rule_status = experimental_rule.get("status", "experimental")
    if admission_status != "not_admitted" or rule_status != "experimental":
        raise QuestionStateError(
            "QGR-CAPABILITY-WITHOUT-EXACT-SERVICE-V1 must remain experimental/not_admitted"
        )

    leads: list[dict[str, Any]] = []
    for (subject_ref, profile_id), matches in sorted(grouped.items()):
        profile = profiles[profile_id]
        actual_cells = sorted(
            {
                item["scope"]["capability_cell_id"]
                for item in matches
                if item.get("modality") == "actual"
            }
        )
        planned_cells = sorted(
            {
                item["scope"]["capability_cell_id"]
                for item in matches
                if item.get("modality") == "planned"
            }
        )
        matched_cells = set(actual_cells) | set(planned_cells)
        unmatched_cells = sorted(_profile_unmatched_cells(profile, matched_cells))
        if not actual_cells and planned_cells:
            coverage_kind = "planned_cell_overlap"
        elif actual_cells and planned_cells:
            coverage_kind = "actual_and_planned_cell_overlap"
        else:
            coverage_kind = "actual_cell_overlap"
        # These leads are intentionally deferred even if a future data set
        # happens to cover every declared cell: the experimental rule is not an
        # admission gate, and full BOM coverage is not a company question gate.
        deferred_reason = "experimental_rule_not_admitted"
        # These are the IDs of the derived match assertions that caused the
        # lead.  Raw CSV anchors remain available through each assertion's
        # source_refs in the relation index; they must not be mislabeled as
        # assertion IDs here.
        source_assertion_ids = sorted(
            {item["assertion_id"] for item in matches}
        )
        lead = {
            "lead_id": stable_id(
                "RL", ["QGR-CAPABILITY-WITHOUT-EXACT-SERVICE-V1", subject_ref, profile_id]
            ),
            "output_kind": "relation_lead",
            "admission_status": admission_status,
            "subject_ref": subject_ref,
            "route_profile_id": profile_id,
            # This names the role represented by the observed edge; it does not
            # imply that the company is a module maker or route service owner.
            "actor_role": "capability_holder",
            "matched_actual_cells": actual_cells,
            "matched_planned_cells": planned_cells,
            "unmatched_cells": unmatched_cells,
            "coverage_kind": coverage_kind,
            "deferred_reason": deferred_reason,
            "source_assertion_ids": source_assertion_ids,
        }
        leads.append(lead)

    reviewed_assertions = sum(
        item.get("epistemic_status") == "explicit_reviewed" for item in assertions
    )
    # The named funnel is deliberately about route leads.  The five requested
    # counters are the only canonical vocabulary; a route lead never enters
    # formal_question_candidates under this experimental rule.
    funnel = {
        "rule_id": "QGR-CAPABILITY-WITHOUT-EXACT-SERVICE-V1",
        "rule_status": rule_status,
        "admission_status": admission_status,
        "counts": {
            "overlap_leads": len(leads),
            "role_eligible_leads": len(leads),
            "product_bound_leads": 0,
            "formal_question_candidates": 0,
            "reviewed_assertions": reviewed_assertions,
        },
    }
    return leads, funnel


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


def lifecycle_question_fingerprint(
    rule_id: str,
    subject_ref: str,
    program_id: str,
    object_ref: str,
) -> str:
    """Stable identity for the narrow production lifecycle question."""
    return canonical_json(
        {
            "rule_id": rule_id,
            "subject_ref": subject_ref,
            "target_relation_type": "product_has_lifecycle_stage",
            "program_id": program_id,
            "object_ref": object_ref,
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
        "limiting_assertion_ids": slot_state.get("limiting_assertion_ids") or [],
        # Keep the revision assertion IDs distinct from the support assertion
        # IDs they affect.  ``withdrawn_assertion_ids`` names the historical
        # support target, while ``withdrawal_assertion_ids`` names the newly
        # observed withdrawal assertion that caused the state transition.
        "withdrawal_assertion_ids": slot_state.get("withdrawal_assertion_ids") or [],
        "withdrawn_assertion_ids": slot_state.get("withdrawn_assertion_ids") or [],
        "contradicting_assertion_ids": slot_state.get("contradicting_assertion_ids") or [],
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


def transition_cause_assertion_ids(
    previous_status: str | None,
    current_status: str,
    basis: dict[str, Any],
) -> list[str]:
    """Derive transition causes only from reducer evidence, never hand input."""
    if previous_status is None or previous_status == current_status:
        return []
    causes: set[str] = set()
    if current_status == "satisfied":
        causes.update(basis.get("qualified_assertion_ids") or [])
    if current_status in {"reopened", "conflicted", "blocked", "partial"}:
        # A transition is caused by the new revision/contradiction, not by the
        # older support row that it withdraws or challenges.  Keep the old IDs
        # in the state basis for auditability, but expose the new assertion IDs
        # as the machine-readable cause.
        causes.update(basis.get("withdrawal_assertion_ids") or [])
        causes.update(basis.get("contradicting_assertion_ids") or [])
        if current_status == "partial":
            causes.update(basis.get("limiting_assertion_ids") or [])
        for pair in basis.get("conflict_pairs") or []:
            if isinstance(pair, list):
                causes.update(value for value in pair if isinstance(value, str))
    return sorted(causes)


def generate_diagnostic_questions(
    assertions: list[dict[str, Any]],
    slot_states: list[dict[str, Any]],
    rules_contract: dict[str, Any],
    adapters_contract: dict[str, Any],
    relation_contract: dict[str, Any] | None = None,
    registry: dict[str, dict[str, Any]] | None = None,
    prior_state: PriorQuestionState | None = None,
    return_deferred: bool | None = None,
    as_of: str | None = None,
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
    if as_of is not None:
        as_of = parse_iso_datetime(as_of)
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
        trigger_relation_type = rule.get("trigger_relation_type")

        # Narrow production lifecycle pilot.  The target is an exact
        # program/stage slot from calls; no product registry or synthetic
        # route target is involved.  We retain the row even when already
        # satisfied so a later build can prove a real transition.
        if trigger_relation_type == "product_has_lifecycle_stage":
            if rule.get("target_relation_type") != "product_has_lifecycle_stage":
                raise QuestionStateError(
                    f"{rule.get('rule_id')}: lifecycle rule must target "
                    "product_has_lifecycle_stage"
                )
            allowed_programs = set(rule.get("program_ids") or [])
            allowed_stages = set(rule.get("lifecycle_stages") or [])
            lifecycle_targets: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for item in assertions:
                if item.get("relation_type") != "product_has_lifecycle_stage":
                    continue
                program_id = item.get("scope", {}).get("program_id")
                stage = item.get("scope", {}).get("lifecycle_stage")
                if allowed_programs and program_id not in allowed_programs:
                    continue
                if allowed_stages and stage not in allowed_stages:
                    continue
                # The production adapter puts a dated event in valid_time.  A
                # caller cannot manufacture this question from an unrelated
                # relation by merely naming a program: source_encoded or
                # explicit_reviewed lifecycle evidence is required.
                if item.get("epistemic_status") not in {"source_encoded", "explicit_reviewed"}:
                    continue
                slot_id = item.get("slot_id")
                if not slot_id:
                    slot_id = stable_id(
                        "RS",
                        relation_slot_identity(
                            item["relation_type"],
                            item["subject_ref"],
                            item["object_ref"],
                            item.get("scope") or {},
                            relation_contract,
                        ),
                    )
                lifecycle_targets[slot_id].append(item)

            for slot_id, trigger_items in sorted(lifecycle_targets.items()):
                representative = sorted(
                    trigger_items, key=lambda item: item["assertion_id"]
                )[0]
                scope = representative.get("scope") or {}
                program_id = scope.get("program_id")
                stage = scope.get("lifecycle_stage")
                if not program_id or not stage:
                    deferred["unbound_lifecycle_target"] += 1
                    continue
                object_ref = representative["object_ref"]
                target_identity = relation_slot_identity(
                    "product_has_lifecycle_stage",
                    representative["subject_ref"],
                    object_ref,
                    scope,
                    relation_contract,
                )
                # Make sure the representative's exact target identity agrees
                # with the slot identity emitted by the production adapter.
                expected_slot_id = stable_id("RS", target_identity)
                if slot_id != expected_slot_id:
                    raise QuestionStateError(
                        f"{representative['assertion_id']}: lifecycle target slot_id "
                        "does not match exact program/stage identity"
                    )
                fingerprint = lifecycle_question_fingerprint(
                    rule["rule_id"],
                    representative["subject_ref"],
                    program_id,
                    object_ref,
                )
                question_id = stable_id("GQ", fingerprint, length=12)
                target_assertions = list(assertions_by_slot.get(slot_id) or [])
                slot_state = states_by_id.get(slot_id)
                resolution_status, basis = compute_resolution(
                    target_assertions,
                    slot_state,
                    rule["acceptance"],
                    None,
                    prior_state,
                    question_id,
                    fingerprint,
                )
                previous_status = (
                    prior_state.status_for(question_id, fingerprint)
                    if prior_state is not None
                    else None
                )
                transition_causes = transition_cause_assertion_ids(
                    previous_status, resolution_status, basis
                )
                question = {
                    "question_id": question_id,
                    "rule_id": rule["rule_id"],
                    "rule_version": rule.get("rule_version"),
                    "question_class": rule["question_class"],
                    "question_text": rule["question_template"].format(
                        as_of=as_of or "as_of",
                        program_id=program_id,
                        lifecycle_stage=stage,
                    ),
                    "display_parent": rule["display_parent"],
                    "depends_on": list(rule.get("depends_on") or []),
                    "generated_by": {
                        "rule_id": rule["rule_id"],
                        "rule_version": rule.get("rule_version"),
                        "reason": rule["generated_by_reason"],
                    },
                    "trigger_refs": sorted(
                        item["assertion_id"] for item in trigger_items
                    ),
                    "target": {
                        "slot_id": slot_id,
                        "relation_type": "product_has_lifecycle_stage",
                        "subject_ref": representative["subject_ref"],
                        "object_ref": object_ref,
                        "program_id": program_id,
                        "primary_subject_id": scope.get("primary_subject_id"),
                        "lifecycle_stage": stage,
                        "identity_scope": _identity_scope(
                            relation_contract,
                            "product_has_lifecycle_stage",
                            scope,
                        ),
                    },
                    "acceptance": rule["acceptance"],
                    "reopen_on": list(rule.get("reopen_on") or []),
                    "workflow_status": rule["initial_workflow_status"],
                    "resolution_status": resolution_status,
                    "dedupe_fingerprint": fingerprint,
                    "target_identity_hash": target_identity_hash(
                        {
                            "relation_type": "product_has_lifecycle_stage",
                            "subject_ref": representative["subject_ref"],
                            "object_ref": object_ref,
                            "identity_scope": _identity_scope(
                                relation_contract,
                                "product_has_lifecycle_stage",
                                scope,
                            ),
                        }
                    ),
                    "previous_resolution_status": previous_status,
                    "transition_cause_assertion_ids": transition_causes,
                    "state_basis": basis,
                    "requirement_groups": [],
                }
                if fingerprint in questions and questions[fingerprint] != question:
                    raise QuestionStateError(
                        f"non-deterministic duplicate question: {fingerprint}"
                    )
                questions[fingerprint] = question
            continue

        if trigger_relation_type != "capability_matches_route":
            continue
        # Frozen route-service rule: it remains an experimental lead rule and
        # is intentionally not admitted to the formal question stream.
        if (
            rule.get("rule_id") == "QGR-CAPABILITY-WITHOUT-EXACT-SERVICE-V1"
            and (
                rule.get("status") == "experimental"
                or rule.get("admission_status") == "not_admitted"
                or rule.get("output_kind") == "relation_lead"
            )
        ):
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
                    previous_status = (
                        prior_state.status_for(question_id, fingerprint)
                        if prior_state is not None
                        else None
                    )
                    transition_causes = transition_cause_assertion_ids(
                        previous_status, resolution_status, basis
                    )
                    # H. On an initial run, an already satisfied target is not a
                    # missing-relation candidate.  Once a real prior snapshot
                    # knows the question, retain its satisfied row so the next
                    # snapshot can prove the lifecycle instead of deleting it.
                    if resolution_status == "satisfied" and not rule.get("retain_satisfied", False) and not (
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
                        "rule_id": rule["rule_id"],
                        "rule_version": rule.get("rule_version"),
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
                            "rule_version": rule.get("rule_version"),
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
                        "target_identity_hash": target_identity_hash(
                            {
                                "relation_type": target_relation_type,
                                "subject_ref": subject_ref,
                                "object_ref": object_ref,
                                "identity_scope": _identity_scope(
                                    relation_contract,
                                    target_relation_type,
                                    scope,
                                ),
                            }
                        ),
                        "previous_resolution_status": previous_status,
                        "transition_cause_assertion_ids": transition_causes,
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
    if not args.as_of:
        raise QuestionStateError(
            "temporal question recompute requires explicit --as-of; "
            "as_of=None is not interpreted as current"
        )
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
        current_contract_compatibility=manifest.get("contract_compatibility"),
        current_assertions=assertions,
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
        as_of=as_of,
    )
    # the projection root (parent of the directory holding the index)
    projection_root = args.assertion_index.resolve().parent.parent
    question_rows_hash = hashlib.sha256(
        canonical_json(questions).encode("utf-8")
    ).hexdigest()
    previous_manifest = prior_state.metadata if prior_state is not None else None
    transition_causes = {
        item["question_id"]: list(item.get("transition_cause_assertion_ids") or [])
        for item in questions
        if item.get("transition_cause_assertion_ids")
    }

    def relation_artifact_ref(
        path: Path, *, rows_hash: str, row_count: int
    ) -> dict[str, Any]:
        # The relation artifact file contains its own build manifest, so the
        # snapshot binds the canonical JSONL rows rather than a self-referential
        # whole-file hash.  The loader verifies this row hash/count and then
        # checks the artifact's own manifest against the snapshot build fields.
        ref = _contract_ref(path, projection_root)
        ref["sha256"] = rows_hash
        ref["row_count"] = row_count
        return ref

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
        "projection_query_hash": manifest.get("projection_query_hash"),
        "question_count": len(questions),
        "questions_data_hash": question_rows_hash,
        # Alias the row digest as an explicit snapshot-content identity.  It is
        # checked when this file becomes a parent so history cannot be made to
        # appear continuous by editing only its lineage metadata.
        "snapshot_content_hash": question_rows_hash,
        "registries": list(manifest.get("registries") or []),
        "contract_compatibility": manifest.get("contract_compatibility"),
        "relation_artifacts": {
            "assertion_index": relation_artifact_ref(
                args.assertion_index,
                rows_hash=manifest["assertion_data_hash"],
                row_count=manifest["assertion_count"],
            ),
            "slot_states": relation_artifact_ref(
                args.slot_states,
                rows_hash=manifest["slot_data_hash"],
                row_count=manifest["slot_count"],
            ),
        },
        "current_build_id": manifest["build_id"],
        "previous_build_id": (
            previous_manifest.get("current_build_id", previous_manifest.get("build_id"))
            if previous_manifest
            else None
        ),
        "parent_snapshot_hash": (
            _file_hash(args.previous_snapshot) if args.previous_snapshot else None
        ),
        "parent_snapshot_questions_data_hash": (
            previous_manifest.get("questions_data_hash") if previous_manifest else None
        ),
        "transition_cause_assertion_ids": transition_causes,
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
