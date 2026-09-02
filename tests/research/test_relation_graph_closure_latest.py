"""Latest reducer-pilot acceptance tests.

These tests exercise the production adapters/reducer seam.  They deliberately
use the real calls event ledger for the lifecycle example and keep the broad
capability overlap in the lead-only output.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from tools.research.build_relation_index import (
    BUILD_MANIFEST_KEY,
    ROOT,
    adapt_calls,
    build_relation_graph,
    compute_build_manifest,
    compute_slot_states,
    load_yaml,
    make_assertion,
)
from tools.research.recompute_question_state import (
    generate_diagnostic_questions,
    generate_relation_leads,
)


CONTRACTS = ROOT / "contracts"
RULES = load_yaml(CONTRACTS / "question_generation_rules.yaml")
ADAPTERS = load_yaml(CONTRACTS / "relation_adapters.yaml")
RELATION_TYPES = load_yaml(CONTRACTS / "relation_types.yaml")


class LatestClosureTests(unittest.TestCase):
    @staticmethod
    def _copy_production_fixture(root: Path) -> Path:
        fixture_root = root / "production"
        fixture_root.mkdir()
        for name in ("points.csv", "route_bom.csv", "relation_assertions.yaml"):
            shutil.copy2(ROOT / name, fixture_root / name)
        shutil.copytree(ROOT / "contracts", fixture_root / "contracts")
        shutil.copytree(ROOT / "calls", fixture_root / "calls")
        return fixture_root

    @staticmethod
    def _run_build(fixture_root: Path, output: Path, as_of: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/research/build_relation_index.py"),
                "--root",
                str(fixture_root),
                "--output-dir",
                str(output),
                "--as-of",
                as_of,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def _run_recompute(
        fixture_root: Path,
        output: Path,
        as_of: str,
        previous: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(ROOT / "tools/research/recompute_question_state.py"),
            "--assertion-index",
            str(output / "relation_assertion_index.jsonl"),
            "--slot-states",
            str(output / "relation_slot_states.jsonl"),
            "--rules",
            str(fixture_root / "contracts/question_generation_rules.yaml"),
            "--adapters",
            str(fixture_root / "contracts/relation_adapters.yaml"),
            "--contracts-dir",
            str(fixture_root / "contracts"),
            "--output",
            str(output / "questions.jsonl"),
            "--as-of",
            as_of,
        ]
        if previous is not None:
            command.extend(("--previous-snapshot", str(previous)))
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)

    @staticmethod
    def _snapshot(path: Path) -> tuple[dict, dict]:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        return rows[0]["__build_manifest__"], rows[1]

    @staticmethod
    def _append_withdrawal(fixture_root: Path) -> None:
        additions = {
            "events": {
                "event_id": "EV900",
                "program_id": "PRG_AVGO_TAURUS",
                "event_category": "product_stage",
                "lifecycle_stage": "sampling",
                "event_status": "withdrawn",
                "primary_subject_id": "AVGO",
                "counterparty_ids": "",
                "theme_ids": "T011",
                "occurred_start": "2026-03-13",
                "occurred_end": "2026-03-13",
                "date_precision": "exact",
                "previous_event_id": "EV003",
                "site_country": "",
                "target_market": "",
                "policy_jurisdiction": "",
                "summary": "Test-only withdrawal of the Taurus sampling event",
                "notes": "temporary pilot fixture",
            },
            "event_claims": {
                "event_claim_id": "ECL900",
                "legacy_claim_id": "",
                "disclosure_id": "D_AVGO_20260311_TAURUS",
                "claimant_entity_id": "AVGO",
                "claimant_role": "corporate_disclosure",
                "statement_kind": "fact_assertion",
                "quote": "Taurus sampling statement withdrawn for the pilot fixture",
                "anchor": "test fixture",
                "summary": "temporary withdrawal assertion",
                "review_status": "anchor_reviewed",
                "reviewed_at": "2026-08-12",
                "notes": "temporary pilot fixture",
            },
            "event_evidence": {
                "evidence_id": "EE900",
                "event_id": "EV900",
                "event_claim_id": "ECL900",
                "relationship": "withdraws",
                "independence_class": "first_party",
                "origin_group": "OG_AVGO_20260311_TAURUS",
                "notes": "temporary pilot fixture",
            },
        }
        for stem, addition in additions.items():
            path = fixture_root / "calls" / f"{stem}.csv"
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                fields = list(reader.fieldnames or ())
            rows.append({field: addition.get(field, "") for field in fields})
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

    @staticmethod
    def _append_future_sampling(fixture_root: Path) -> None:
        """Add a same-slot assertion whose event starts after the prior as_of."""
        additions = {
            "events": {
                "event_id": "EV901",
                "program_id": "PRG_AVGO_TAURUS",
                "event_category": "product_stage",
                "lifecycle_stage": "sampling",
                "event_status": "asserted",
                "primary_subject_id": "AVGO",
                "counterparty_ids": "",
                "theme_ids": "T011",
                "occurred_start": "2026-03-20",
                "occurred_end": "2026-03-20",
                "date_precision": "exact",
                "previous_event_id": "",
                "site_country": "",
                "target_market": "",
                "policy_jurisdiction": "",
                "summary": "Test-only future Taurus sampling assertion",
                "notes": "temporary pilot fixture",
            },
            "event_claims": {
                "event_claim_id": "ECL901",
                "legacy_claim_id": "",
                "disclosure_id": "D_AVGO_20260311_TAURUS",
                "claimant_entity_id": "AVGO",
                "claimant_role": "corporate_disclosure",
                "statement_kind": "fact_assertion",
                "quote": "Future Taurus sampling assertion for the pilot fixture",
                "anchor": "test fixture",
                "summary": "temporary future assertion",
                "review_status": "anchor_reviewed",
                "reviewed_at": "2026-08-12",
                "notes": "temporary pilot fixture",
            },
            "event_evidence": {
                "evidence_id": "EE901",
                "event_id": "EV901",
                "event_claim_id": "ECL901",
                "relationship": "reports",
                "independence_class": "first_party",
                "origin_group": "OG_AVGO_20260311_TAURUS",
                "notes": "temporary pilot fixture",
            },
        }
        for stem, addition in additions.items():
            path = fixture_root / "calls" / f"{stem}.csv"
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                fields = list(reader.fieldnames or ())
            rows.append({field: addition.get(field, "") for field in fields})
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

    def test_cli_real_production_lifecycle_a_b_c_history(self) -> None:
        """The production command sequence must demonstrate a real state loop."""
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_root = self._copy_production_fixture(Path(temp_dir))
            out_a = fixture_root / "out-a"
            out_b = fixture_root / "out-b"
            out_c = fixture_root / "out-c"

            build_a = self._run_build(fixture_root, out_a, "2026-03-10")
            self.assertEqual(build_a.returncode, 0, build_a.stderr)
            recompute_a = self._run_recompute(fixture_root, out_a, "2026-03-10")
            self.assertEqual(recompute_a.returncode, 0, recompute_a.stderr)
            manifest_a, question_a = self._snapshot(out_a / "questions.jsonl")
            self.assertEqual(question_a["resolution_status"], "open")

            build_b = self._run_build(fixture_root, out_b, "2026-03-12")
            self.assertEqual(build_b.returncode, 0, build_b.stderr)
            recompute_b = self._run_recompute(
                fixture_root,
                out_b,
                "2026-03-12",
                out_a / "questions.jsonl",
            )
            self.assertEqual(recompute_b.returncode, 0, recompute_b.stderr)
            manifest_b, question_b = self._snapshot(out_b / "questions.jsonl")
            self.assertEqual(question_b["resolution_status"], "satisfied")

            self._append_withdrawal(fixture_root)
            build_c = self._run_build(fixture_root, out_c, "2026-03-14")
            self.assertEqual(build_c.returncode, 0, build_c.stderr)
            recompute_c = self._run_recompute(
                fixture_root,
                out_c,
                "2026-03-14",
                out_b / "questions.jsonl",
            )
            self.assertEqual(recompute_c.returncode, 0, recompute_c.stderr)
            manifest_c, question_c = self._snapshot(out_c / "questions.jsonl")
            self.assertEqual(question_c["resolution_status"], "reopened")

            # The question identity survives changing data and query time; the
            # target is exact sampling, not a generic program lifecycle slot.
            for field in ("question_id", "dedupe_fingerprint", "target_identity_hash"):
                self.assertEqual(question_a[field], question_b[field])
                self.assertEqual(question_b[field], question_c[field])
            self.assertEqual(question_a["target"]["object_ref"], "lifecycle_stage:sampling")
            self.assertEqual(question_a["target"]["slot_id"], question_b["target"]["slot_id"])
            self.assertEqual(question_b["target"]["slot_id"], question_c["target"]["slot_id"])

            build_manifests = (manifest_a, manifest_b, manifest_c)
            self.assertEqual(
                len({item["build_id"] for item in build_manifests}), 3
            )
            self.assertEqual(
                len({item["data_hash"] for item in build_manifests}), 3
            )
            self.assertEqual(manifest_b["previous_build_id"], manifest_a["current_build_id"])
            self.assertEqual(manifest_c["previous_build_id"], manifest_b["current_build_id"])
            self.assertEqual(
                manifest_b["parent_snapshot_hash"],
                hashlib.sha256((out_a / "questions.jsonl").read_bytes()).hexdigest(),
            )
            self.assertEqual(
                manifest_c["parent_snapshot_hash"],
                hashlib.sha256((out_b / "questions.jsonl").read_bytes()).hexdigest(),
            )
            self.assertEqual(
                manifest_b["prior_state"]["snapshot"]["sha256"],
                manifest_b["parent_snapshot_hash"],
            )
            self.assertEqual(
                manifest_c["prior_state"]["snapshot"]["sha256"],
                manifest_c["parent_snapshot_hash"],
            )
            self.assertLessEqual(manifest_a["as_of"], manifest_b["as_of"])
            self.assertLessEqual(manifest_b["as_of"], manifest_c["as_of"])

            c_index = [
                json.loads(line)
                for line in (out_c / "relation_assertion_index.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
                if line and "__build_manifest__" not in line
            ]
            withdrawal_id = next(
                item["assertion_id"]
                for item in c_index
                if "calls/event_evidence.csv#EE900" in item.get("source_refs", [])
            )
            self.assertEqual(question_c["transition_cause_assertion_ids"], [withdrawal_id])

    def test_cli_temporal_boundary_and_raw_assertion_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_root = self._copy_production_fixture(Path(temp_dir))
            no_as_of = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/research/build_relation_index.py"),
                    "--root",
                    str(fixture_root),
                    "--output-dir",
                    str(fixture_root / "no-as-of"),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(no_as_of.returncode, 0)
            self.assertIn("--as-of", no_as_of.stderr)

            raw_out = fixture_root / "raw"
            raw = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/research/build_relation_index.py"),
                    "--root",
                    str(fixture_root),
                    "--output-dir",
                    str(raw_out),
                    "--assertions-only",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(raw.returncode, 0, raw.stderr)
            self.assertEqual(
                {item.name for item in raw_out.iterdir()},
                {"relation_assertion_index.jsonl"},
            )
            raw_manifest, _ = self._snapshot(raw_out / "relation_assertion_index.jsonl")
            self.assertIsNone(raw_manifest["as_of"])
            self.assertEqual(raw_manifest["projection_kind"], "raw_assertions")

    def test_cross_build_history_rejects_tampered_identity_contract_lineage_and_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_root = self._copy_production_fixture(Path(temp_dir))
            out_a = fixture_root / "out-a"
            out_b = fixture_root / "out-b"
            out_c = fixture_root / "out-c"
            self.assertEqual(self._run_build(fixture_root, out_a, "2026-03-10").returncode, 0)
            self.assertEqual(
                self._run_recompute(fixture_root, out_a, "2026-03-10").returncode,
                0,
            )
            self.assertEqual(self._run_build(fixture_root, out_b, "2026-03-12").returncode, 0)
            self.assertEqual(
                self._run_recompute(
                    fixture_root, out_b, "2026-03-12", out_a / "questions.jsonl"
                ).returncode,
                0,
            )
            # A different query boundary is enough to exercise cross-build
            # validation even when the underlying data has not changed.
            self._append_future_sampling(fixture_root)
            self.assertEqual(self._run_build(fixture_root, out_c, "2026-03-14").returncode, 0)

            source = out_b / "questions.jsonl"
            current_assertions = [
                json.loads(line)
                for line in (out_c / "relation_assertion_index.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line and "__build_manifest__" not in line
            ]
            future_id = next(
                item["assertion_id"]
                for item in current_assertions
                if "calls/event_evidence.csv#EE901" in item.get("source_refs", [])
            )
            other_id = next(
                item["assertion_id"]
                for item in current_assertions
                if item.get("relation_type") != "product_has_lifecycle_stage"
            )

            def write_variant(
                name: str,
                mutate_manifest=None,
                mutate_question=None,
            ) -> Path:
                rows = [
                    json.loads(line)
                    for line in source.read_text(encoding="utf-8").splitlines()
                    if line
                ]
                manifest = rows[0][BUILD_MANIFEST_KEY]
                question = rows[1]
                if mutate_question is not None:
                    mutate_question(question)
                    digest = hashlib.sha256(
                        json.dumps(
                            [question], ensure_ascii=False, sort_keys=True, separators=(",", ":")
                        ).encode("utf-8")
                    ).hexdigest()
                    manifest["questions_data_hash"] = digest
                    manifest["snapshot_content_hash"] = digest
                if mutate_manifest is not None:
                    mutate_manifest(manifest)
                variant = fixture_root / name / "questions.jsonl"
                variant.parent.mkdir()
                variant.write_text(
                    "\n".join(
                        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                        for item in rows
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return variant

            def assert_rejected(previous: Path, as_of: str = "2026-03-14") -> None:
                result = self._run_recompute(
                    fixture_root, out_c, as_of, previous
                )
                self.assertNotEqual(result.returncode, 0, result.stderr)

            assert_rejected(
                write_variant(
                    "tampered-target",
                    mutate_question=lambda question: question.__setitem__(
                        "target_identity_hash", "0" * 64
                    ),
                )
            )
            assert_rejected(
                write_variant(
                    "tampered-rule",
                    mutate_question=lambda question: question.__setitem__("rule_version", 999),
                )
            )
            assert_rejected(
                write_variant(
                    "dangling-cause",
                    mutate_question=lambda question: question.__setitem__(
                        "transition_cause_assertion_ids", ["RA-NOT-IN-CURRENT-INDEX"]
                    ),
                )
            )
            assert_rejected(
                write_variant(
                    "other-slot-cause",
                    mutate_question=lambda question: question.__setitem__(
                        "transition_cause_assertion_ids", [other_id]
                    ),
                )
            )
            assert_rejected(
                write_variant(
                    "future-cause",
                    mutate_question=lambda question: question.__setitem__(
                        "transition_cause_assertion_ids", [future_id]
                    ),
                )
            )
            assert_rejected(
                write_variant(
                    "tampered-contract",
                    mutate_manifest=lambda manifest: manifest["contract_compatibility"].__setitem__(
                        "relation_product_lifecycle_hash", "0" * 64
                    ),
                )
            )
            assert_rejected(
                write_variant(
                    "tampered-parent",
                    mutate_manifest=lambda manifest: manifest.__setitem__(
                        "parent_snapshot_hash", "0" * 64
                    ),
                )
            )
            assert_rejected(
                write_variant(
                    "tampered-prior-ref",
                    mutate_manifest=lambda manifest: manifest["prior_state"]["snapshot"].__setitem__(
                        "sha256", "0" * 64
                    ),
                )
            )
            # A predecessor at a later as_of cannot be used to answer an
            # earlier query, even though its relation data build is otherwise
            # compatible.
            assert_rejected(out_b / "questions.jsonl", as_of="2026-03-10")

    def test_calls_ev003_is_reached_by_and_persists_after_event_date(self) -> None:
        config = dict(ADAPTERS, relation_contract=RELATION_TYPES)
        rows = adapt_calls(ROOT, config)
        ev003 = next(
            row
            for row in rows
            if row["source_refs"] == [
                "calls/event_claims.csv#ECL003",
                "calls/event_evidence.csv#EE003",
                "calls/events.csv#EV003",
            ]
        )
        self.assertEqual(ev003["object_ref"], "lifecycle_stage:sampling")
        self.assertEqual(ev003["valid_time"], {"start": "2026-03-11", "end": None})

        before = compute_slot_states(
            [ev003], as_of="2026-03-10", relation_contract=RELATION_TYPES
        )[0]
        after = compute_slot_states(
            [ev003], as_of="2026-03-12", relation_contract=RELATION_TYPES
        )[0]
        self.assertEqual(before["effective_status"], "unknown")
        self.assertEqual(after["effective_status"], "supported")

    def test_lifecycle_stage_is_part_of_slot_identity(self) -> None:
        sampling = make_assertion(
            relation_type="product_has_lifecycle_stage",
            subject_ref="product_or_program:PRG_AVGO_TAURUS",
            object_ref="lifecycle_stage:sampling",
            scope={
                "program_id": "PRG_AVGO_TAURUS",
                "primary_subject_id": "AVGO",
                "lifecycle_stage": "sampling",
            },
            valid_time={"start": "2026-03-11", "end": None},
            modality="actual",
            polarity="supporting",
            epistemic_status="source_encoded",
            origin_group="OG-AVGO",
            adapter_version="test",
            source_refs=["calls/events.csv#EV003"],
            assertion_key="sampling",
            relation_contract=RELATION_TYPES,
        )
        scaled = make_assertion(
            relation_type="product_has_lifecycle_stage",
            subject_ref="product_or_program:PRG_AVGO_TAURUS",
            object_ref="lifecycle_stage:scaled",
            scope={
                "program_id": "PRG_AVGO_TAURUS",
                "primary_subject_id": "AVGO",
                "lifecycle_stage": "scaled",
            },
            valid_time={"start": "2026-03-11", "end": None},
            modality="actual",
            polarity="supporting",
            epistemic_status="source_encoded",
            origin_group="OG-AVGO",
            adapter_version="test",
            source_refs=["calls/events.csv#EV003-SCALED"],
            assertion_key="scaled",
            relation_contract=RELATION_TYPES,
        )
        # The stage target must not be closed by evidence for a different stage.
        self.assertNotEqual(sampling["slot_id"], scaled["slot_id"])
        state_ids = {
            state["slot_id"]
            for state in compute_slot_states(
                [sampling, scaled], relation_contract=RELATION_TYPES
            )
        }
        self.assertEqual(state_ids, {sampling["slot_id"], scaled["slot_id"]})

    def test_capability_overlap_is_lead_only_and_funnel_has_no_admitted_question(self) -> None:
        assertions, states = build_relation_graph(
            ROOT,
            CONTRACTS,
            ROOT / "relation_assertions.yaml",
            as_of="2026-09-02",
        )
        leads, funnel = generate_relation_leads(
            assertions,
            states,
            RULES,
            ADAPTERS,
            RELATION_TYPES,
            as_of="2026-09-02",
        )
        self.assertEqual(len(leads), 83)
        self.assertEqual(len({lead["lead_id"] for lead in leads}), 83)
        self.assertTrue(all(lead["output_kind"] == "relation_lead" for lead in leads))
        self.assertTrue(all(lead["admission_status"] == "not_admitted" for lead in leads))
        required_fields = {
            "subject_ref",
            "route_profile_id",
            "actor_role",
            "matched_actual_cells",
            "matched_planned_cells",
            "unmatched_cells",
            "coverage_kind",
            "deferred_reason",
            "source_assertion_ids",
        }
        self.assertTrue(all(required_fields <= set(lead) for lead in leads))
        self.assertEqual(funnel["counts"]["overlap_leads"], 83)
        self.assertEqual(funnel["counts"]["role_eligible_leads"], 83)
        self.assertEqual(funnel["counts"]["product_bound_leads"], 0)
        self.assertEqual(funnel["counts"]["formal_question_candidates"], 0)
        self.assertEqual(funnel["counts"]["reviewed_assertions"], 0)

        questions, _deferred = generate_diagnostic_questions(
            assertions, states, RULES, ADAPTERS, RELATION_TYPES, return_deferred=True
        )
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["rule_id"], "QGR-PRODUCT-STAGE-AS-OF-V1")
        self.assertEqual(questions[0]["resolution_status"], "satisfied")

    def test_lifecycle_question_is_open_before_ev003_and_satisfied_after(self) -> None:
        before_assertions, before_states = build_relation_graph(
            ROOT, CONTRACTS, ROOT / "relation_assertions.yaml", as_of="2026-03-10"
        )
        after_assertions, after_states = build_relation_graph(
            ROOT, CONTRACTS, ROOT / "relation_assertions.yaml", as_of="2026-03-12"
        )
        before, _ = generate_diagnostic_questions(
            before_assertions,
            before_states,
            RULES,
            ADAPTERS,
            RELATION_TYPES,
            return_deferred=True,
        )
        after, _ = generate_diagnostic_questions(
            after_assertions,
            after_states,
            RULES,
            ADAPTERS,
            RELATION_TYPES,
            return_deferred=True,
        )
        self.assertEqual(len(before), 1)
        self.assertEqual(before[0]["resolution_status"], "open")
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0]["resolution_status"], "satisfied")
        self.assertEqual(
            before[0]["target"]["object_ref"], "lifecycle_stage:sampling"
        )
        self.assertEqual(before[0]["target"]["slot_id"], after[0]["target"]["slot_id"])

    def test_projection_query_changes_build_identity(self) -> None:
        assertions_t1, states_t1 = build_relation_graph(
            ROOT, CONTRACTS, ROOT / "relation_assertions.yaml", as_of="2026-03-10"
        )
        assertions_t2, states_t2 = build_relation_graph(
            ROOT, CONTRACTS, ROOT / "relation_assertions.yaml", as_of="2026-03-12"
        )
        first = compute_build_manifest(
            assertions_t1,
            states_t1,
            CONTRACTS,
            CONTRACTS / "question_generation_rules.yaml",
            CONTRACTS / "relation_adapters.yaml",
            as_of="2026-03-10",
        )
        second = compute_build_manifest(
            assertions_t2,
            states_t2,
            CONTRACTS,
            CONTRACTS / "question_generation_rules.yaml",
            CONTRACTS / "relation_adapters.yaml",
            as_of="2026-03-12",
        )
        self.assertNotEqual(first["build_id"], second["build_id"])
        self.assertNotEqual(first["data_hash"], second["data_hash"])
        self.assertNotEqual(first["projection_query_hash"], second["projection_query_hash"])


if __name__ == "__main__":
    unittest.main()
