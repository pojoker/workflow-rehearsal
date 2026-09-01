#!/usr/bin/env python3
"""Independent validator CLI for explicit_reviewed relation assertions (contract A).

Validates that every explicit_reviewed assertion carries the full reviewed-write
gate provenance and that every cited reference resolves to a known claim/source/
disclosure/point/event object. Intended to be wired into `scan.py --check` and the
pre-commit total gate.

Usage:
    python tools/research/validate_reviewed_assertions.py [--assertions PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.build_relation_index import (
    ROOT as _INDEX_ROOT,
    RelationIndexError,
    build_receipt_registry,
    build_reference_registry,
    load_yaml,
    validate_explicit_reviewed,
    validate_relation_contract,
    validate_withdrawals,
)

ROOT = _INDEX_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assertions", type=Path, default=ROOT / "relation_assertions.yaml")
    parser.add_argument("--contracts-dir", type=Path, default=ROOT / "contracts")
    parser.add_argument(
        "--extra-registry",
        type=Path,
        action="append",
        default=[],
        help="additional resolvable reference registry (e.g. a test registry)",
    )
    args = parser.parse_args()

    contracts_dir = args.contracts_dir.resolve()
    relation_contract = load_yaml(contracts_dir / "relation_types.yaml")
    validate_relation_contract(relation_contract)
    adapter_contract = load_yaml(contracts_dir / "relation_adapters.yaml")
    assertions_path = args.assertions.resolve()
    # Use the project containing the supplied contracts/ so a sidecar copied to
    # another worktree cannot accidentally consult the caller's production
    # ledger.  This also keeps the validator deterministic across roots.
    project_root = contracts_dir.parent
    registry = build_reference_registry(project_root, tuple(args.extra_registry))
    # 1. a review_receipt_id must resolve in the receipt registry; otherwise it
    # is a fake receipt and the assertion must not pass the write gate.
    receipts = build_receipt_registry(adapter_contract, tuple(args.extra_registry))
    data = load_yaml(assertions_path)
    items = data.get("assertions") or []

    errors: list[str] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"assertion {index}: must be a mapping")
            continue
        try:
            validate_explicit_reviewed(item, registry, relation_contract, receipts)
        except RelationIndexError as exc:
            errors.append(f"{item.get('assertion_id', f'assertion {index}')}: {exc}")

    # F. withdrawal / revision integrity across the explicit set
    try:
        validate_withdrawals(
            [item for item in items if isinstance(item, dict)], relation_contract
        )
    except RelationIndexError as exc:
        errors.append(str(exc))

    if errors:
        for message in errors:
            print(f"REVIEWED-GATE: {message}")
        return 1
    print(f"REVIEWED-GATE: {len(items)} explicit assertion(s) passed write-gate validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
