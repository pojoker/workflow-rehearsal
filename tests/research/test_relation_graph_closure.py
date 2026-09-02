"""Relation closure reducer pilot tests.

Round 1 (contract) counterexamples 1-15 are kept. Round 2 adds one
production-path regression test per evaluator finding (R2-1 .. R2-10); each of
those drives the real production functions (adapters, slot-state reducer,
question generator, validator CLI) instead of a reimplementation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

from tools.research.build_relation_index import (
    BUILD_MANIFEST_KEY,
    ROOT,
    RelationIndexError,
    adapt_route_requirements,
    build_receipt_registry,
    build_reference_registry,
    build_relation_graph,
    compute_build_manifest,
    compute_slot_states,
    derive_capability_matches,
    evaluate_requirement_group,
    load_yaml,
    make_assertion,
    parse_iso_datetime,
    relation_slot_identity,
    stable_id,
    validate_explicit_reviewed,
    validate_relation_contract,
    validate_route_profiles,
    validate_withdrawals,
)
from tools.research.recompute_question_state import (
    PriorQuestionState,
    QuestionStateError,
    actual_coverage_cells,
    bind_target_slot,
    candidate_product_refs,
    compute_resolution,
    evaluate_coverage,
    generate_diagnostic_questions,
    generate_relation_leads,
    project_group_cells,
    read_index_with_manifest,
    _require_query_matches_manifest,
    _require_same_build,
)


# Use the declared relation contract so slot identity (D) is applied in tests.
_orig_make_assertion = make_assertion


def make_assertion(*args: Any, **kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("relation_contract", RELATION_TYPES)
    return _orig_make_assertion(*args, **kwargs)


CONTRACTS = ROOT / "contracts"
RULES = load_yaml(CONTRACTS / "question_generation_rules.yaml")
ADAPTERS = load_yaml(CONTRACTS / "relation_adapters.yaml")
ADAPTERS["relation_contract"] = load_yaml(CONTRACTS / "relation_types.yaml")
RELATION_TYPES = ADAPTERS["relation_contract"]
EXACT_PROFILE = "RPF-800G-DR8-LPO-SIPH-FPP-V1"
OTHER_PROFILE = "RPF-800G-DR8-FRO-DISCRETE-FPP-V1"
FIXTURE = ROOT / "tests/fixtures/research_graph/relation_assertions_exact_support.yaml"
TEST_REGISTRY = ROOT / "tests/fixtures/research_graph/test_registry.yaml"
REGISTRY = build_reference_registry(ROOT, (TEST_REGISTRY,))
RECEIPTS = build_receipt_registry(ADAPTERS, (TEST_REGISTRY,))


def cfg() -> dict[str, Any]:
    data = copy.deepcopy(ADAPTERS)
    data["relation_contract"] = RELATION_TYPES
    return data


def make_slot_id(identity: dict[str, Any]) -> str:
    return stable_id("RS", identity)


def route_bom_rows() -> dict[str, dict[str, str]]:
    from tools.research.build_relation_index import load_csv

    return {row["route_item_id"]: row for row in load_csv(ROOT / "route_bom.csv")}


def assertions_conflict_demo(left: dict[str, Any], right: dict[str, Any]) -> bool:
    from tools.research.build_relation_index import assertions_conflict

    return assertions_conflict(left, right)


def derive_capability_matches_demo(assertions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return derive_capability_matches(assertions, cfg())


class RelationGraphClosureTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def explicit_support(self, **overrides: Any) -> dict[str, Any]:
        item = copy.deepcopy(load_yaml(FIXTURE)["assertions"][0])
        item.update(overrides)
        return item

    def service_assertion(self, service_kind: str, assertion_id: str, **overrides: Any) -> dict[str, Any]:
        item = self.explicit_support(assertion_id=assertion_id)
        item["scope"]["service_kind"] = service_kind
        item.update(overrides)
        return item

    def write_sidecar(self, directory: Path, items: list[dict[str, Any]]) -> Path:
        sidecar = directory / "relation_assertions.yaml"
        sidecar.write_text(
            yaml.safe_dump(
                {"schema_version": "relation_assertions_v1", "fixture_only": True, "assertions": items},
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return sidecar

    def build_with(
        self, items: list[dict[str, Any]], as_of: str | None = None, modality: str | None = None
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
        """Full production projection + question generation for a fixture sidecar."""
        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar = self.write_sidecar(Path(temp_dir), items)
            assertions, states = build_relation_graph(
                ROOT,
                CONTRACTS,
                sidecar,
                extra_registries=(TEST_REGISTRY,),
                as_of=as_of,
                modality=modality,
            )
        questions, deferred = generate_diagnostic_questions(
            assertions, states, RULES, ADAPTERS, RELATION_TYPES, REGISTRY,
            return_deferred=True,
        )
        return assertions, states, questions, deferred

    def required_cells(self, assertions: list[dict[str, Any]], profile_id: str = EXACT_PROFILE) -> list[str]:
        return sorted(
            {
                item["scope"]["capability_cell_id"]
                for item in assertions
                if item["relation_type"] == "route_requires_capability"
                and item["scope"].get("route_profile_id") == profile_id
            }
        )

    def capability_assertion(self, company: str, cell_id: str, modality: str, index: int) -> dict[str, Any]:
        return make_assertion(
            relation_type="company_has_capability_at",
            subject_ref=company,
            object_ref=f"capability_cell:{cell_id}",
            scope={"capability_cell_id": cell_id},
            valid_time={"start": "2026-01-01"},
            modality=modality,
            polarity="supporting",
            epistemic_status="source_encoded",
            origin_group=f"OG-TEST-CAP-{index}",
            adapter_version="points_company_capability_v1",
            source_refs=[f"points.csv#TEST-{index}"],
            assertion_key=f"test-cap-{company}-{cell_id}-{index}",
        )

    def scenario(
        self,
        items: list[dict[str, Any]],
        company: str = "company:Lumentum",
        capability_modality: str = "actual",
        cells: list[str] | None = None,
        registry: dict[str, dict[str, Any]] | None = None,
        prior_state: PriorQuestionState | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
        """Production projection + a test company with controllable coverage."""
        assertions, _states = self.build_index(items)
        target_cells = cells if cells is not None else self.required_caps(assertions)
        caps = [
            self.capability_assertion(company, cell_id, capability_modality, index)
            for index, cell_id in enumerate(target_cells)
        ]
        pool = [
            item for item in assertions if item["relation_type"] != "capability_matches_route"
        ] + caps
        pool = pool + derive_capability_matches(pool, cfg())
        pool.sort(key=lambda item: item["assertion_id"])
        states = compute_slot_states(pool, relation_contract=RELATION_TYPES)
        questions, deferred = generate_diagnostic_questions(
            pool, states, RULES, ADAPTERS, RELATION_TYPES,
            REGISTRY if registry is None else registry, prior_state,
            return_deferred=True,
        )
        return pool, states, questions, deferred

    def required_caps(self, assertions: list[dict[str, Any]]) -> list[str]:
        """Cells needed for COMPLETE actual coverage of the LPO profile groups."""
        profile = next(
            item for item in ADAPTERS["route_profiles"] if item["route_profile_id"] == EXACT_PROFILE
        )
        required_items: list[str] = []
        for group in profile["requirement_groups"]:
            if group.get("kind") == "all_of":
                required_items.extend(group["capability_cell_ids"])
            else:
                required_items.append(sorted(group["capability_cell_ids"])[0])
        return sorted(
            {
                item["scope"]["capability_cell_id"]
                for item in assertions
                if item["relation_type"] == "route_requires_capability"
                and item["metadata"].get("requirement_group_id") in
                {group["group_id"] for group in profile["requirement_groups"]}
                and item["scope"].get("requirement_source_rb_item") in required_items
            }
        )

    def build_index(self, items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar = self.write_sidecar(Path(temp_dir), items)
            return build_relation_graph(ROOT, CONTRACTS, sidecar, extra_registries=(TEST_REGISTRY,))

    @staticmethod
    def question_for(questions: list[dict[str, Any]], company: str) -> dict[str, Any]:
        target = f"company:{company}"
        return next(item for item in questions if item["target"]["subject_ref"] == target)

    @staticmethod
    def questions_for(questions: list[dict[str, Any]], company: str) -> list[dict[str, Any]]:
        target = f"company:{company}"
        return [item for item in questions if item["target"]["subject_ref"] == target]

    # ------------------------------------------------------------------
    # existing behavioural tests (updated for the new gates)
    # ------------------------------------------------------------------
    def test_capability_and_requirement_only_make_match_and_candidate_question(self) -> None:
        assertions, _, questions, deferred = self.build_with([])
        relation_types = {item["relation_type"] for item in assertions}
        self.assertIn("company_has_capability_at", relation_types)
        self.assertIn("route_requires_capability", relation_types)
        self.assertIn("capability_matches_route", relation_types)
        self.assertNotIn("company_serves_route", relation_types)
        # The overlap is a lead-only experimental output.  It never enters the
        # formal route-service question stream, regardless of coverage.
        self.assertFalse(
            any(
                item["target"]["relation_type"] == "company_serves_route"
                for item in questions
            )
        )
        self.assertEqual(
            [item["rule_id"] for item in questions],
            ["QGR-PRODUCT-STAGE-AS-OF-V1"],
        )
        self.assertEqual(deferred, {})

    def test_component_product_evidence_cannot_close_service_question(self) -> None:
        assertions, _, questions, _ = self.build_with([])
        self.assertTrue(
            any(item["relation_type"] == "product_has_lifecycle_stage" for item in assertions)
        )
        self.assertFalse(
            any(
                item["target"]["relation_type"] == "company_serves_route"
                for item in questions
            )
        )
        self.assertEqual(len(questions), 1)  # the independent lifecycle pilot

    def test_exact_reviewed_service_assertion_satisfies_question(self) -> None:
        assertions, states, questions, _ = self.build_with([self.explicit_support()])
        csr = [
            s for s in states
            if s["relation_type"] == "company_serves_route" and s["subject_ref"] == "company:Lumentum"
        ]
        self.assertTrue(csr)
        self.assertEqual(csr[0]["effective_status"], "supported")
        # H. a satisfied target must not spawn a missing_relation candidate
        self.assertFalse(self.questions_for(questions, "Lumentum"))

    def test_different_route_profile_does_not_close_question(self) -> None:
        assertion = self.explicit_support()
        assertion["assertion_id"] = "RA-TEST-LITE-OTHER-PROFILE"
        assertion["object_ref"] = f"route_profile:{OTHER_PROFILE}"
        assertion["scope"]["route_profile_id"] = OTHER_PROFILE
        assertion["scope"]["product_ref"] = "product:TEST-PRODUCT-001"
        assertion["scope"]["service_kind"] = "demonstrated"
        _assertions, _states, questions, _deferred = self.build_with([assertion])
        self.assertFalse(self.questions_for(questions, "Lumentum"))

    def test_withdrawal_reopens_and_same_condition_conflict_is_open_conflict(self) -> None:
        support = self.explicit_support()
        withdrawal = copy.deepcopy(support)
        withdrawal.update(
            {
                "assertion_id": "RA-TEST-LITE-WITHDRAWAL",
                "polarity": "withdrawn",
                "source_refs": ["source:TEST-SRC-001", "disclosure:TEST-DISC-001"],
                "origin_group": "OG-TEST-REGISTRY",
                "revises_assertion_ids": [support["assertion_id"]],
                "revision_kind": "withdraws",
                "effective_at": "2026-06-01",
                "retroactive": False,
            }
        )
        _a, _s, questions, _d = self.build_with([support, withdrawal])
        # 5. without prior-state evidence the question is open, never "reopened".
        self.assertEqual(self.question_for_scenario(questions, "Lumentum", "open"), "open")

        contradiction = copy.deepcopy(support)
        contradiction.update(
            {
                "assertion_id": "RA-TEST-LITE-CONTRADICTION",
                "polarity": "contradicting",
                "supports": [],
                "does_not_support": ["claim:TEST-CLAIM-001"],
                "source_refs": ["source:TEST-SRC-001", "disclosure:TEST-DISC-001"],
                "origin_group": "OG-TEST-REGISTRY",
            }
        )
        _a, _s, questions, _d = self.build_with([support, contradiction])
        slot = next(
            s for s in _s
            if s["relation_type"] == "company_serves_route"
            and s["subject_ref"] == "company:Lumentum"
        )
        self.assertEqual(slot["effective_status"], "conflicted")
        self.assertTrue(slot["conflict_pairs"])

    def question_for_scenario(
        self, questions: list[dict[str, Any]], company: str, expected: str
    ) -> str:
        found = self.questions_for(questions, company)
        if not found:
            return expected
        return found[0]["resolution_status"]

    def test_planned_ramp_and_current_demonstrated_are_not_automatic_conflict(self) -> None:
        demonstrated = make_assertion(
            relation_type="product_has_lifecycle_stage",
            subject_ref="product_or_program:TEST-PRODUCT",
            object_ref="lifecycle_stage:demonstrated",
            scope={"program_id": "TEST-PRODUCT", "primary_subject_id": "SUB-1", "lifecycle_stage": "demonstrated"},
            valid_time={"start": "2026-04-30", "end": "2026-04-30"},
            modality="actual",
            polarity="supporting",
            epistemic_status="source_encoded",
            origin_group="OG-TEST-DEMO",
            adapter_version="test_v1",
            source_refs=["test:demo"],
            assertion_key="demo",
        )
        ramp = make_assertion(
            relation_type="product_has_lifecycle_stage",
            subject_ref="product_or_program:TEST-PRODUCT",
            object_ref="lifecycle_stage:ramping",
            scope={"program_id": "TEST-PRODUCT", "primary_subject_id": "SUB-1", "lifecycle_stage": "ramping"},
            valid_time={"start": "2027-01-01", "end": None},
            modality="planned",
            polarity="contradicting",
            epistemic_status="source_encoded",
            origin_group="OG-TEST-RAMP",
            adapter_version="test_v1",
            source_refs=["test:ramp"],
            assertion_key="ramp",
        )
        self.assertFalse(assertions_conflict_demo(demonstrated, ramp))
        self.assertTrue(
            all(item["effective_status"] != "conflicted" for item in compute_slot_states([demonstrated, ramp]))
        )

    def test_same_origin_duplicates_do_not_raise_independent_evidence_count(self) -> None:
        first = self.explicit_support()
        duplicate = copy.deepcopy(first)
        duplicate["assertion_id"] = "RA-TEST-LITE-DUPLICATE"
        duplicate["source_refs"] = ["source:TEST-SRC-002"]
        duplicate["evidence_claim_refs"] = ["claim:TEST-CLAIM-001"]
        assertions, states, _q, _d = self.build_with([first, duplicate])
        target_assertion = next(
            item for item in assertions if item["assertion_id"] == first["assertion_id"]
        )
        state = next(item for item in states if item["slot_id"] == target_assertion["slot_id"])
        self.assertEqual(state["independent_origin_counts"]["supporting"], 1)
        self.assertEqual(len(state["supporting_assertion_ids"]), 2)

    def test_repeated_run_is_deterministic_and_questions_are_deduplicated(self) -> None:
        first = self.build_with([])
        second = self.build_with([])
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[1], second[1])
        self.assertEqual(first[2], second[2])
        fingerprints = [item["dedupe_fingerprint"] for item in first[2]]
        self.assertEqual(len(fingerprints), len(set(fingerprints)))

    # ------------------------------------------------------------------
    # A. reviewed assertion write gate (counterexamples 1, 2)
    # ------------------------------------------------------------------
    def test_write_gate_rejects_empty_or_unresolvable_refs(self) -> None:
        def gate(**overrides: Any) -> None:
            item = self.explicit_support(**overrides)
            validate_explicit_reviewed(item, REGISTRY, RELATION_TYPES, RECEIPTS)

        with self.assertRaises(RelationIndexError):
            gate(source_refs=[])
        with self.assertRaises(RelationIndexError):
            gate(evidence_claim_refs=["claim:DOES-NOT-EXIST"])
        with self.assertRaises(RelationIndexError):
            gate(review_receipt_id="")
        with self.assertRaises(RelationIndexError):
            gate(reviewer="")
        with self.assertRaises(RelationIndexError):
            gate(reviewed_at="")
        with self.assertRaises(RelationIndexError):
            gate(reviewed_at="2026-9-1")
        with self.assertRaises(RelationIndexError):
            gate(supports="not-a-list")

    def test_hand_filled_origin_group_rejected_and_derived_count_is_one(self) -> None:
        with self.assertRaises(RelationIndexError):
            item = self.explicit_support()
            item["origin_group"] = "OG-HAND-FILLED"
            validate_explicit_reviewed(item, REGISTRY, RELATION_TYPES, RECEIPTS)
        first = self.explicit_support()
        duplicate = copy.deepcopy(first)
        duplicate["assertion_id"] = "RA-TEST-LITE-DUP2"
        duplicate["source_refs"] = ["source:TEST-SRC-002"]
        duplicate["evidence_claim_refs"] = ["claim:TEST-CLAIM-001"]
        _a, states, _q, _d = self.build_with([first, duplicate])
        slot = next(
            s for s in states if s["relation_type"] == "company_serves_route"
            and s["scope"].get("product_ref") == "product:TEST-PRODUCT-001"
        )
        self.assertEqual(slot["independent_origin_counts"]["supporting"], 1)

    # ------------------------------------------------------------------
    # C. point status mapping (counterexample 3)
    # ------------------------------------------------------------------
    def test_planned_point_does_not_generate_actual_match(self) -> None:
        cap = make_assertion(
            relation_type="company_has_capability_at",
            subject_ref="company:TESTCO",
            object_ref="capability_cell:RB002",
            scope={"capability_cell_id": "RB002"},
            valid_time={"start": "2026-01-01"},
            modality="planned",
            polarity="supporting",
            epistemic_status="source_encoded",
            origin_group="OG-CAP",
            adapter_version="points_company_capability_v1",
            source_refs=["points.csv#P1"],
            assertion_key="cap",
        )
        req = make_assertion(
            relation_type="route_requires_capability",
            subject_ref=f"route_profile:{EXACT_PROFILE}",
            object_ref="capability_cell:RB002",
            scope={"route_profile_id": EXACT_PROFILE, "capability_cell_id": "RB002"},
            valid_time=None,
            modality="actual",
            polarity="supporting",
            epistemic_status="derived_candidate",
            origin_group="OG-REQ",
            adapter_version="route_bom_profile_requirements_v1",
            source_refs=["route_bom.csv#RB002"],
            assertion_key="req",
        )
        matches = derive_capability_matches_demo([cap, req])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["modality"], "planned")
        self.assertNotEqual(matches[0]["modality"], "actual")

    # ------------------------------------------------------------------
    # B. requirement-group semantics (counterexample 4)
    # ------------------------------------------------------------------
    def test_one_of_requirement_not_treated_as_all_required(self) -> None:
        one_of = {"group_id": "g1", "kind": "one_of", "capability_cell_ids": ["RB004", "RB005"]}
        all_of = {"group_id": "g2", "kind": "all_of", "capability_cell_ids": ["RB002", "RB003"]}
        self.assertTrue(evaluate_requirement_group(one_of, {"RB004"}))
        self.assertFalse(evaluate_requirement_group(all_of, {"RB002"}))

    # ------------------------------------------------------------------
    # D. relation-specific slot identity + context roll-up (counterexample 5)
    # ------------------------------------------------------------------
    def test_context_does_not_mint_new_slot_and_policy_is_explicit(self) -> None:
        definition = RELATION_TYPES["relation_types"]["company_serves_route"]
        self.assertIn("geography", definition.get("context_fields", []))
        self.assertNotIn("geography", definition.get("slot_identity_fields", []))
        base_scope = {
            "route_profile_id": EXACT_PROFILE,
            "product_ref": "product:TEST-PRODUCT-001",
            "service_kind": "demonstrated",
        }
        id_a = relation_slot_identity(
            "company_serves_route", "company:Lumentum",
            f"route_profile:{EXACT_PROFILE}", {**base_scope, "geography": "US"}, RELATION_TYPES,
        )
        id_b = relation_slot_identity(
            "company_serves_route", "company:Lumentum",
            f"route_profile:{EXACT_PROFILE}", {**base_scope, "geography": "EU"}, RELATION_TYPES,
        )
        self.assertEqual(id_a, id_b)
        self.assertEqual(make_slot_id(id_a), make_slot_id(id_b))

    # ------------------------------------------------------------------
    # E. as_of / modality state merge (counterexamples 6, 7, 8)
    # ------------------------------------------------------------------
    def _service_pair(self, **overrides: Any) -> dict[str, Any]:
        base = dict(
            relation_type="company_serves_route",
            subject_ref="company:Lumentum",
            object_ref=f"route_profile:{EXACT_PROFILE}",
            scope={
                "route_profile_id": EXACT_PROFILE,
                "product_ref": "product:TEST-PRODUCT-001",
                "service_kind": "demonstrated",
            },
            epistemic_status="explicit_reviewed",
            origin_group="OG-TEST-REGISTRY",
            adapter_version="explicit_relation_assertions_v1",
            source_refs=["source:TEST-SRC-001"],
        )
        base.update(overrides)
        return base

    def test_historical_support_cannot_override_current_contradiction(self) -> None:
        support = make_assertion(
            **self._service_pair(
                valid_time={"start": "2024-01-01", "end": "2024-12-31"},
                modality="actual", polarity="supporting", assertion_key="s",
            )
        )
        contradiction = make_assertion(
            **self._service_pair(
                valid_time={"start": "2026-01-01", "end": None},
                modality="actual", polarity="contradicting", assertion_key="c",
            )
        )
        states = compute_slot_states([support, contradiction], as_of="2026-06-01")
        self.assertNotEqual(states[0]["effective_status"], "supported")
        self.assertEqual(states[0]["supporting_assertion_ids"], [])

    def test_future_planned_limit_does_not_pollute_current_actual(self) -> None:
        support = make_assertion(
            **self._service_pair(
                valid_time={"start": "2026-01-01", "end": None},
                modality="actual", polarity="supporting", assertion_key="s",
            )
        )
        limit = make_assertion(
            **self._service_pair(
                valid_time={"start": "2027-01-01", "end": None},
                modality="planned", polarity="limiting", assertion_key="l",
            )
        )
        states = compute_slot_states([support, limit], as_of="2026-06-01")
        self.assertEqual(states[0]["effective_status"], "supported")

    def test_non_iso_time_rejected(self) -> None:
        parse_iso_datetime("2026-04-30")
        parse_iso_datetime("2026-04-30T10:00:00")
        for bad in ("2026-9-1", "FY2026Q3", ""):
            with self.assertRaises(RelationIndexError):
                parse_iso_datetime(bad)

    # ------------------------------------------------------------------
    # F. withdrawal / correction integrity (counterexample 9)
    # ------------------------------------------------------------------
    def test_withdrawal_across_slot_or_unknown_or_corrects_rejected(self) -> None:
        support = make_assertion(
            **self._service_pair(
                valid_time={"start": "2026-01-01", "end": None},
                modality="actual", polarity="supporting", assertion_key="support-1",
            )
        )
        w_unknown = make_assertion(
            **self._service_pair(
                valid_time={"start": "2026-06-01", "end": None},
                modality="actual", polarity="withdrawn", assertion_key="w-unknown",
                revises_assertion_ids=["RA-DOES-NOT-EXIST"], revision_kind="withdraws",
                effective_at="2026-06-01", retroactive=False,
            )
        )
        with self.assertRaises(RelationIndexError):
            validate_withdrawals([support, w_unknown], RELATION_TYPES)

        other = make_assertion(
            **self._service_pair(
                subject_ref="company:Coherent",
                valid_time={"start": "2026-01-01", "end": None},
                modality="actual", polarity="supporting", assertion_key="other-co",
            )
        )
        w_cross = make_assertion(
            **self._service_pair(
                valid_time={"start": "2026-06-01", "end": None},
                modality="actual", polarity="withdrawn", assertion_key="w-cross",
                revises_assertion_ids=[other["assertion_id"]], revision_kind="withdraws",
                effective_at="2026-06-01", retroactive=False,
            )
        )
        with self.assertRaises(RelationIndexError):
            validate_withdrawals([support, other, w_cross], RELATION_TYPES)

        w_corrects = make_assertion(
            **self._service_pair(
                valid_time={"start": "2026-06-01", "end": None},
                modality="actual", polarity="withdrawn", assertion_key="w-corrects",
                revises_assertion_ids=[support["assertion_id"]], revision_kind="corrects",
                effective_at="2026-06-01", retroactive=False,
            )
        )
        with self.assertRaises(RelationIndexError):
            validate_withdrawals([support, w_corrects], RELATION_TYPES)

    # ------------------------------------------------------------------
    # H. question lifecycle honesty (counterexamples 10, 11, 12)
    # ------------------------------------------------------------------
    def test_satisfied_target_first_run_does_not_make_missing_candidate(self) -> None:
        _a, _s, questions, _d = self.build_with([self.explicit_support()])
        for q in questions:
            self.assertNotEqual(q["target"]["subject_ref"], "company:Lumentum")

    def test_withdrawal_without_prior_satisfied_state_is_not_reopened(self) -> None:
        planned = self.explicit_support(
            assertion_id="RA-TEST-PLANNED",
            modality="planned",
            source_refs=["source:TEST-SRC-001", "disclosure:TEST-DISC-001"],
            evidence_claim_refs=["claim:TEST-CLAIM-001"],
        )
        withdrawal = copy.deepcopy(planned)
        withdrawal.update(
            {
                "assertion_id": "RA-TEST-W-PLANNED",
                "polarity": "withdrawn",
                "source_refs": ["source:TEST-SRC-001", "disclosure:TEST-DISC-001"],
                "revises_assertion_ids": ["RA-TEST-PLANNED"],
                "revision_kind": "withdraws",
                "effective_at": "2026-06-01",
                "retroactive": False,
            }
        )
        _a, _s, questions, _d = self.build_with([planned, withdrawal])
        for question in self.questions_for(questions, "Lumentum"):
            self.assertNotEqual(question["resolution_status"], "reopened")

    def test_cross_build_manifest_mismatch_rejected(self) -> None:
        manifest_a = {
            "build_id": "0" * 24, "data_hash": "2" * 64,
            "assertion_data_hash": "1" * 64, "slot_data_hash": "3" * 64,
            "assertion_count": 1, "slot_count": 1, "as_of": None, "modality": None,
            "contracts": {
                "relation_types.yaml": {"path": "contracts/relation_types.yaml", "sha256": "4" * 64},
                "relation_adapters.yaml": {"path": "contracts/relation_adapters.yaml", "sha256": "5" * 64},
                "question_generation_rules.yaml": {"path": "contracts/question_generation_rules.yaml", "sha256": "6" * 64},
            },
            "registries": [],
        }
        manifest_b = dict(manifest_a, build_id="A" * 24)
        with self.assertRaises(QuestionStateError):
            _require_same_build(manifest_a, manifest_b)
        self.assertEqual(_require_same_build(manifest_a, manifest_a)["build_id"], "0" * 24)

    # ------------------------------------------------------------------
    # G. company_serves_route narrowing (counterexample 13)
    # ------------------------------------------------------------------
    def test_different_product_or_service_kind_is_distinct_slot(self) -> None:
        a = self.explicit_support()
        b = copy.deepcopy(a)
        b["assertion_id"] = "RA-TEST-PROD2"
        b["scope"]["product_ref"] = "product:TEST-PRODUCT-002"
        _a, states, _q, _d = self.build_with([a, b])
        csr = [
            s for s in states
            if s["relation_type"] == "company_serves_route" and s["subject_ref"] == "company:Lumentum"
        ]
        p1 = next(s for s in csr if s["scope"].get("product_ref") == "product:TEST-PRODUCT-001")
        p2 = next(s for s in csr if s["scope"].get("product_ref") == "product:TEST-PRODUCT-002")
        self.assertNotEqual(p1["slot_id"], p2["slot_id"])
        self.assertEqual(p1["assertion_ids"], ["RA-TEST-LITE-EXACT-SERVICE"])
        self.assertEqual(p2["assertion_ids"], ["RA-TEST-PROD2"])
        self.assertEqual(p1["effective_status"], "supported")
        self.assertEqual(p2["effective_status"], "supported")

    # ------------------------------------------------------------------
    # I. calls adapter semantic isolation (counterexample 14)
    # ------------------------------------------------------------------
    def test_non_product_stage_events_excluded_from_lifecycle(self) -> None:
        assertions, _s, _q, _d = self.build_with([])
        excluded_events = {
            "EV001", "EV005", "EV009", "EV011", "EV013", "EV014",
            "EV017", "EV018", "EV019", "EV020", "EV021",
        }
        for item in assertions:
            if item["relation_type"] == "product_has_lifecycle_stage":
                refs = " ".join(item.get("source_refs", []))
                for ev in excluded_events:
                    self.assertNotIn(f"calls/events.csv#{ev}", refs)

    # ------------------------------------------------------------------
    # D/E. exact stage is part of slot identity; modality remains context
    # ------------------------------------------------------------------
    def test_planned_vs_demonstrated_hits_same_slot_not_short_circuit(self) -> None:
        from tools.research.build_relation_index import assertions_conflict

        demonstrated = make_assertion(
            relation_type="product_has_lifecycle_stage",
            subject_ref="product_or_program:T",
            object_ref="lifecycle_stage:demonstrated",
            scope={"program_id": "T", "primary_subject_id": "S", "lifecycle_stage": "demonstrated"},
            valid_time={"start": "2026-04-30", "end": "2026-04-30"},
            modality="actual", polarity="supporting", epistemic_status="source_encoded",
            origin_group="OG", adapter_version="v", source_refs=["test:d"], assertion_key="d",
        )
        ramping = make_assertion(
            relation_type="product_has_lifecycle_stage",
            subject_ref="product_or_program:T",
            object_ref="lifecycle_stage:ramping",
            scope={"program_id": "T", "primary_subject_id": "S", "lifecycle_stage": "ramping"},
            valid_time={"start": "2027-01-01", "end": None},
            modality="planned", polarity="contradicting", epistemic_status="source_encoded",
            origin_group="OG", adapter_version="v", source_refs=["test:r"], assertion_key="r",
        )
        self.assertNotEqual(demonstrated["slot_id"], ramping["slot_id"])
        self.assertFalse(assertions_conflict(demonstrated, ramping, RELATION_TYPES))
        contradicting_same_modality = make_assertion(
            relation_type="product_has_lifecycle_stage",
            subject_ref="product_or_program:T",
            object_ref="lifecycle_stage:demonstrated",
            scope={"program_id": "T", "primary_subject_id": "S", "lifecycle_stage": "demonstrated"},
            valid_time={"start": "2026-04-30", "end": None},
            modality="actual", polarity="contradicting", epistemic_status="source_encoded",
            origin_group="OG", adapter_version="v", source_refs=["test:c"], assertion_key="c",
        )
        self.assertEqual(demonstrated["slot_id"], contradicting_same_modality["slot_id"])
        same_stage_planned = make_assertion(
            relation_type="product_has_lifecycle_stage",
            subject_ref="product_or_program:T",
            object_ref="lifecycle_stage:demonstrated",
            scope={"program_id": "T", "primary_subject_id": "S", "lifecycle_stage": "demonstrated"},
            valid_time={"start": "2027-01-01", "end": None},
            modality="planned", polarity="supporting", epistemic_status="source_encoded",
            origin_group="OG", adapter_version="v", source_refs=["test:p"], assertion_key="p",
        )
        self.assertEqual(demonstrated["slot_id"], same_stage_planned["slot_id"])
        self.assertFalse(assertions_conflict(demonstrated, same_stage_planned, RELATION_TYPES))
        same_stage_states = compute_slot_states(
            [demonstrated, same_stage_planned], relation_contract=RELATION_TYPES
        )
        self.assertEqual(len(same_stage_states), 1)
        self.assertNotEqual(same_stage_states[0]["effective_status"], "conflicted")
        self.assertTrue(
            assertions_conflict(demonstrated, contradicting_same_modality, RELATION_TYPES)
        )


class Round2RegressionTests(unittest.TestCase):
    """One production-path regression per evaluator finding (R2-1 .. R2-10)."""

    def gate(self, **overrides: Any) -> None:
        item = copy.deepcopy(load_yaml(FIXTURE)["assertions"][0])
        item.update(overrides)
        validate_explicit_reviewed(item, REGISTRY, RELATION_TYPES, RECEIPTS)

    @staticmethod
    def _history_manifest(kind: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        def digest(value: Any) -> str:
            return hashlib.sha256(
                json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()

        contracts = {
            name: {
                "path": f"contracts/{name}",
                "sha256": hashlib.sha256((CONTRACTS / name).read_bytes()).hexdigest(),
            }
            for name in (
                "relation_types.yaml",
                "relation_adapters.yaml",
                "question_generation_rules.yaml",
            )
        }
        manifest = {
            "build_id": "A" * 24,
            "data_hash": "b" * 64,
            "assertion_data_hash": "c" * 64,
            "slot_data_hash": "d" * 64,
            "assertion_count": 1,
            "slot_count": 1,
            "as_of": None,
            "modality": None,
            "contracts": contracts,
            "registries": [
                {
                    "path": TEST_REGISTRY.relative_to(ROOT).as_posix(),
                    "sha256": hashlib.sha256(TEST_REGISTRY.read_bytes()).hexdigest(),
                }
            ],
        }
        if kind == "snapshot":
            manifest.update(
                {
                    "snapshot_schema_version": "question_state_snapshot_v1",
                    "question_count": len(rows),
                    "questions_data_hash": digest(rows),
                }
            )
        else:
            manifest.update(
                {
                    "state_event_schema_version": "question_state_events_v1",
                    "event_count": len(rows),
                    "events_data_hash": digest(rows),
                }
            )
        return manifest

    # ------------------------------------------------------------------
    # R2-1 reviewed gate
    # ------------------------------------------------------------------
    def test_r2_1_gate_rejects_fake_receipt_arbitrary_reviewer_and_unrelated_evidence(self) -> None:
        self.gate()  # the registered fixture passes
        with self.assertRaises(RelationIndexError):
            self.gate(review_receipt_id="RR-NOT-REGISTERED")
        with self.assertRaises(RelationIndexError):
            self.gate(reviewer="reviewer:someone-else")
        # wrong kind: a bare source ref is not an evidence claim
        with self.assertRaises(RelationIndexError):
            self.gate(evidence_claim_refs=["source:TEST-SRC-001"])
        with self.assertRaises(RelationIndexError):
            self.gate(
                evidence_claim_refs=["point:TEST-POINT-001"],
                supports=["point:TEST-POINT-001"],
            )
        # empty supports AND does_not_support
        with self.assertRaises(RelationIndexError):
            self.gate(supports=[], does_not_support=[])
        # evidence that belongs to a different company is semantically unrelated
        with self.assertRaises(RelationIndexError):
            self.gate(
                evidence_claim_refs=["claim:OTHER-CO-CLAIM-001"],
                supports=["claim:OTHER-CO-CLAIM-001"],
                source_refs=["source:OTHER-CO-SRC-001"],
                origin_group="OG-TEST-OTHER-CO",
            )
        # a verdict that cites evidence which was never claimed
        with self.assertRaises(RelationIndexError):
            self.gate(supports=["claim:TEST-CLAIM-002"])

        # Same-company is not enough: a source from one company must not be
        # paired with a claim from another company (the historical claims.csv
        # schema has no claimant column, so this linkage must come from source).
        with self.assertRaises(RelationIndexError):
            self.gate(
                source_refs=["source:OTHER-CO-SRC-001"],
                evidence_claim_refs=["claim:TEST-CLAIM-001"],
                supports=["claim:TEST-CLAIM-001"],
                origin_group="OG-TEST-OTHER-CO",
            )
        with self.assertRaises(RelationIndexError):
            self.gate(
                source_refs=["source:TEST-SRC-001"],
                evidence_claim_refs=["claim:OTHER-CO-CLAIM-001"],
                supports=["claim:OTHER-CO-CLAIM-001"],
                origin_group="OG-TEST-REGISTRY",
            )

    def test_r2_1_gate_audit_fields_preserved_in_assertion_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar = Path(temp_dir) / "relation_assertions.yaml"
            sidecar.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            assertions, _states = build_relation_graph(
                ROOT, CONTRACTS, sidecar, extra_registries=(TEST_REGISTRY,)
            )
        row = next(
            item for item in assertions
            if item["assertion_id"] == "RA-TEST-LITE-EXACT-SERVICE"
        )
        for field in (
            "review_receipt_id", "reviewer", "reviewed_at",
            "evidence_claim_refs", "supports", "does_not_support",
        ):
            self.assertIn(field, row, f"gate field {field} missing from the index")
        self.assertEqual(row["review_receipt_id"], "RR-TEST-LITE-001")
        self.assertEqual(row["reviewer"], "reviewer:TEST-001")

    # ------------------------------------------------------------------
    # R2-2 route identity / requirement semantics
    # ------------------------------------------------------------------
    def test_r2_2_broad_route_bom_to_exact_profile_is_never_source_encoded(self) -> None:
        adapter = ADAPTERS["adapters"]["route_bom_profile_requirements"]
        self.assertNotEqual(adapter["epistemic_status"], "source_encoded")
        emitted = adapt_route_requirements(ROOT, cfg())
        self.assertTrue(emitted)
        self.assertEqual({item["epistemic_status"] for item in emitted}, {"derived_candidate"})
        # a contract that declares source_encoded for the broad->exact projection
        # must fail the build instead of silently creating a canonical fact.
        broken = cfg()
        broken["adapters"]["route_bom_profile_requirements"]["epistemic_status"] = "source_encoded"
        with self.assertRaises(RelationIndexError):
            validate_route_profiles(broken, route_bom_rows())

    def test_r2_2_unknown_fro_semantics_emits_no_requirements_matches_or_questions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar = Path(temp_dir) / "relation_assertions.yaml"
            sidecar.write_text(
                yaml.safe_dump({"assertions": []}, allow_unicode=True), encoding="utf-8"
            )
            assertions, states = build_relation_graph(
                ROOT, CONTRACTS, sidecar, extra_registries=(TEST_REGISTRY,)
            )
        profiles = {
            item["route_profile_id"]: item for item in ADAPTERS["route_profiles"]
        }
        self.assertEqual(profiles[OTHER_PROFILE]["requirement_semantics"], "UNKNOWN")
        self.assertEqual(profiles[OTHER_PROFILE]["requirement_groups"], [])
        routed = {
            item["scope"]["route_profile_id"]
            for item in assertions
            if item["relation_type"] in ("route_requires_capability", "capability_matches_route")
        }
        self.assertNotIn(OTHER_PROFILE, routed)
        self.assertNotIn(
            OTHER_PROFILE,
            {state["scope"].get("route_profile_id") for state in states},
        )
        # declaring exact groups on an UNKNOWN profile is refused
        broken = cfg()
        for profile in broken["route_profiles"]:
            if profile["route_profile_id"] == OTHER_PROFILE:
                profile["requirement_groups"] = [
                    {"group_id": "RG-BAD", "kind": "all_of", "capability_cell_ids": ["RB002"]}
                ]
        with self.assertRaises(RelationIndexError):
            validate_route_profiles(broken, route_bom_rows())

    def test_r2_2_lpo_requirements_are_derived_from_declared_groups(self) -> None:
        emitted = adapt_route_requirements(ROOT, cfg())
        declared: set[str] = set()
        for profile in ADAPTERS["route_profiles"]:
            if profile.get("requirement_semantics") == "UNKNOWN":
                continue
            for group in profile["requirement_groups"]:
                declared.update(group["source_route_item_ids"])
        for item in emitted:
            self.assertEqual(item["epistemic_status"], "derived_candidate")
            self.assertIn(item["scope"]["requirement_source_rb_item"], declared)
            self.assertTrue(item["metadata"]["derived_from_broad_route_bom"])
            self.assertIn(
                item["metadata"]["requirement_group_kind"], ("all_of", "one_of")
            )

    def test_r2_2_profile_identity_fields_are_required_and_hashed(self) -> None:
        broken = cfg()
        profile = broken["route_profiles"][0]
        profile.pop("identity_hash")
        with self.assertRaises(RelationIndexError):
            validate_route_profiles(broken, route_bom_rows())

        broken = cfg()
        profile = broken["route_profiles"][0]
        profile["identity_axes"]["electrical_architecture"] = "FRO"
        with self.assertRaises(RelationIndexError):
            validate_route_profiles(broken, route_bom_rows())

    # ------------------------------------------------------------------
    # R2-3 complete actual coverage gate
    # ------------------------------------------------------------------
    def test_r2_3_partial_or_planned_coverage_never_generates_gap_candidate(self) -> None:
        assertions, _s = self._index()
        complete_cells = self._complete_cells(assertions)
        # partial coverage: one cell short
        _pool, states, questions, deferred = self._pool(complete_cells[:-1], "actual", [])
        self.assertEqual(self._for_company(questions, "company:Lumentum"), [])
        leads, funnel = generate_relation_leads(
            _pool, states, RULES, ADAPTERS, RELATION_TYPES
        )
        lumentum_lead = next(
            item
            for item in leads
            if item["subject_ref"] == "company:Lumentum"
            and item["route_profile_id"] == EXACT_PROFILE
        )
        self.assertTrue(lumentum_lead["unmatched_cells"])
        self.assertEqual(funnel["counts"]["overlap_leads"], len(leads))
        self.assertEqual(funnel["counts"]["formal_question_candidates"], 0)
        self.assertEqual(deferred, {})
        # planned coverage over the complete set is still not route capability
        _pool, states, questions, deferred = self._pool(complete_cells, "planned", [])
        self.assertEqual(self._for_company(questions, "company:Lumentum"), [])
        leads, funnel = generate_relation_leads(
            _pool, states, RULES, ADAPTERS, RELATION_TYPES
        )
        lumentum_lead = next(
            item
            for item in leads
            if item["subject_ref"] == "company:Lumentum"
            and item["route_profile_id"] == EXACT_PROFILE
        )
        self.assertIn(
            lumentum_lead["coverage_kind"],
            {"planned_cell_overlap", "actual_and_planned_cell_overlap"},
        )
        self.assertEqual(funnel["counts"]["formal_question_candidates"], 0)
        self.assertEqual(deferred, {})
        # a single cell is nowhere near complete coverage
        _pool, states, questions, _deferred = self._pool(complete_cells[:1], "actual", [])
        self.assertEqual(self._for_company(questions, "company:Lumentum"), [])
        leads, funnel = generate_relation_leads(
            _pool, states, RULES, ADAPTERS, RELATION_TYPES
        )
        self.assertEqual(
            len(
                [
                    item
                    for item in leads
                    if item["subject_ref"] == "company:Lumentum"
                    and item["route_profile_id"] == EXACT_PROFILE
                ]
            ),
            1,
        )
        self.assertEqual(funnel["counts"]["formal_question_candidates"], 0)

    def test_r2_3_complete_actual_coverage_generates_the_gap_candidate(self) -> None:
        assertions, _s = self._index()
        complete_cells = self._complete_cells(assertions)
        pool, states, questions, deferred = self._pool(complete_cells, "actual", [])
        leads, funnel = generate_relation_leads(
            pool, states, RULES, ADAPTERS, RELATION_TYPES
        )
        found = [item for item in leads if item["subject_ref"] == "company:Lumentum"]
        self.assertTrue(found, "complete actual coverage must generate a lead")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["unmatched_cells"], [])
        self.assertEqual(funnel["counts"]["overlap_leads"], len(leads))
        self.assertEqual(funnel["counts"]["formal_question_candidates"], 0)
        self.assertEqual(
            [item for item in questions if item["target"]["relation_type"] == "company_serves_route"],
            [],
        )
        self.assertEqual(deferred, {})

    def test_r2_3_coverage_uses_authoritative_filtered_states(self) -> None:
        assertions, states = self._index()
        match = next(
            item for item in assertions if item["relation_type"] == "capability_matches_route"
        )
        # An explicitly empty filtered projection is authoritative.  Scanning
        # the raw assertion list here would incorrectly resurrect this match.
        self.assertEqual(
            actual_coverage_cells(
                assertions,
                match["subject_ref"],
                match["scope"]["route_profile_id"],
                slot_states=[],
            ),
            set(),
        )
        # The real all-slots projection still reports the active match.
        self.assertIn(
            match["scope"]["capability_cell_id"],
            actual_coverage_cells(
                assertions,
                match["subject_ref"],
                match["scope"]["route_profile_id"],
                slot_states=states,
            ),
        )
        # A raw 2026 match must not resurrect itself in an as_of=2020 query;
        # the time-filtered state projection is authoritative here too.
        historical_states = compute_slot_states(
            assertions,
            as_of="2020-01-01",
            modality="actual",
            relation_contract=RELATION_TYPES,
        )
        self.assertNotIn(
            match["scope"]["capability_cell_id"],
            actual_coverage_cells(
                assertions,
                match["subject_ref"],
                match["scope"]["route_profile_id"],
                slot_states=historical_states,
                as_of="2020-01-01",
                modality="actual",
            ),
        )

    # ------------------------------------------------------------------
    # R2-4 real target slot, no synthetic route slot, no cross-close
    # ------------------------------------------------------------------
    def test_r2_4_synthetic_route_slot_is_refused(self) -> None:
        slot_id, _identity, reason = bind_target_slot(
            RELATION_TYPES,
            "company_serves_route",
            "company:Lumentum",
            f"route_profile:{EXACT_PROFILE}",
            {"route_profile_id": EXACT_PROFILE},
        )
        self.assertIsNone(slot_id)
        self.assertIn("unbound_identity_fields", reason)
        self.assertIn("product_ref", reason)
        self.assertIn("service_kind", reason)

    def test_r2_4_real_target_slot_is_bound_and_not_aggregated(self) -> None:
        scope = {
            "route_profile_id": EXACT_PROFILE,
            "product_ref": "product:TEST-PRODUCT-001",
            "service_kind": "demonstrated",
        }
        slot_id, identity, reason = bind_target_slot(
            RELATION_TYPES, "company_serves_route", "company:Lumentum",
            f"route_profile:{EXACT_PROFILE}", scope,
        )
        self.assertIsNone(reason)
        self.assertEqual(
            identity,
            relation_slot_identity(
                "company_serves_route", "company:Lumentum",
                f"route_profile:{EXACT_PROFILE}", scope, RELATION_TYPES,
            ),
        )
        # a different product or service_kind is a different slot: no aggregate
        other_product = dict(scope, product_ref="product:TEST-PRODUCT-002")
        other_kind = dict(scope, service_kind="listed")
        self.assertNotEqual(
            slot_id,
            bind_target_slot(
                RELATION_TYPES, "company_serves_route", "company:Lumentum",
                f"route_profile:{EXACT_PROFILE}", other_product,
            )[0],
        )
        self.assertNotEqual(
            slot_id,
            bind_target_slot(
                RELATION_TYPES, "company_serves_route", "company:Lumentum",
                f"route_profile:{EXACT_PROFILE}", other_kind,
            )[0],
        )

    def test_r2_4_service_kind_cannot_cross_close(self) -> None:
        assertions, _s = self._index()
        complete_cells = self._complete_cells(assertions)
        listed = self._service_assertion("listed", "RA-TEST-LISTED")
        pool, states, questions, _deferred = self._pool(
            complete_cells, "actual", [listed]
        )
        # The route-service rule is no longer admitted: a capability overlap is
        # observable as a lead, while the explicit listed assertion remains an
        # independent exact service slot.
        self.assertFalse(
            any(
                item["target"]["relation_type"] == "company_serves_route"
                for item in questions
            )
        )
        listed_slot = next(
            item for item in states
            if item["relation_type"] == "company_serves_route"
            and item["identity_scope"].get("service_kind") == "listed"
        )
        self.assertEqual(listed_slot["effective_status"], "supported")
        leads, funnel = generate_relation_leads(
            pool, states, RULES, ADAPTERS, RELATION_TYPES
        )
        self.assertEqual(funnel["counts"]["formal_question_candidates"], 0)
        self.assertTrue(leads)

        # A demonstrated assertion in the real demonstrated slot is still
        # represented separately; it does not mutate or collapse the listed
        # slot.
        demonstrated = self._service_assertion("demonstrated", "RA-TEST-DEMONSTRATED")
        _pool, _states, questions, _deferred = self._pool(
            complete_cells, "actual", [listed, demonstrated]
        )
        self.assertFalse(
            any(
                item["target"]["relation_type"] == "company_serves_route"
                for item in questions
            )
        )
        service_slots = [
            item for item in _states if item["relation_type"] == "company_serves_route"
        ]
        self.assertEqual(
            {
                item["identity_scope"].get("service_kind") for item in service_slots
            },
            {"listed", "demonstrated"},
        )

    def test_r2_4_no_resolvable_product_binding_means_no_question(self) -> None:
        assertions, _s = self._index()
        complete_cells = self._complete_cells(assertions)
        empty_registry = build_reference_registry(ROOT, ())
        pool, states, questions, deferred = self._pool(
            complete_cells, "actual", [], registry=empty_registry
        )
        self.assertFalse(
            any(
                item["target"]["relation_type"] == "company_serves_route"
                for item in questions
            )
        )
        leads, funnel = generate_relation_leads(
            pool, states, RULES, ADAPTERS, RELATION_TYPES
        )
        self.assertTrue(leads)
        self.assertEqual(funnel["counts"]["formal_question_candidates"], 0)
        self.assertEqual(deferred, {})
        self.assertEqual(
            candidate_product_refs(empty_registry, "company:Lumentum", "product"), []
        )
        # A plain in-memory dictionary is not a contract-bound extra registry;
        # adding registry_id by hand must not mint a target product.
        fake_registry = {
            "source:TEST-SRC-001": REGISTRY["source:TEST-SRC-001"],
            "product:FAKE": {
                "kind": "product",
                "company": "company:Lumentum",
                "registry_id": "hand-filled",
                "source_refs": ["source:TEST-SRC-001"],
            },
        }
        self.assertEqual(
            candidate_product_refs(fake_registry, "company:Lumentum", "product"), []
        )

    def test_r2_4_question_text_does_not_claim_service_evidence(self) -> None:
        assertions, _s = self._index()
        pool, states, questions, _deferred = self._pool(
            self._complete_cells(assertions), "actual", []
        )
        self.assertFalse(
            any(
                item["target"]["relation_type"] == "company_serves_route"
                for item in questions
            )
        )
        leads, _funnel = generate_relation_leads(
            pool, states, RULES, ADAPTERS, RELATION_TYPES
        )
        self.assertTrue(leads)
        self.assertTrue(
            all(item["deferred_reason"] == "experimental_rule_not_admitted" for item in leads)
        )

    # ------------------------------------------------------------------
    # R2-5 reopened requires real prior state
    # ------------------------------------------------------------------
    def test_r2_5_no_prior_state_never_reopened(self) -> None:
        assertions, _s = self._index()
        complete_cells = self._complete_cells(assertions)
        support = self._service_assertion("demonstrated", "RA-TEST-PRIOR-SUPPORT")
        withdrawal = copy.deepcopy(support)
        withdrawal.update(
            {
                "assertion_id": "RA-TEST-PRIOR-WITHDRAWAL",
                "polarity": "withdrawn",
                "revises_assertion_ids": [support["assertion_id"]],
                "revision_kind": "withdraws",
                "effective_at": "2026-06-01",
                "retroactive": False,
            }
        )
        _pool, _states, questions, _deferred = self._pool(
            complete_cells, "actual", [support, withdrawal]
        )
        self.assertFalse(
            any(
                item["target"]["relation_type"] == "company_serves_route"
                for item in questions
            )
        )

    def test_r2_5_hand_written_satisfied_row_is_not_history(self) -> None:
        # A status line (even one that happens to use a real question id) is not
        # a predecessor snapshot.  Only a generated, content-addressed
        # question projection may authorize a later reopened transition.
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = Path(temp_dir) / "previous_questions.jsonl"
            snapshot.write_text(
                json.dumps(
                    {
                        "question_id": "GQ-HAND-WRITTEN",
                        "resolution_status": "satisfied",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(QuestionStateError):
                PriorQuestionState.load(snapshot=snapshot)

    # ------------------------------------------------------------------
    # R2-6 as_of / modality on the production CLI
    # ------------------------------------------------------------------
    def test_r2_6_future_withdrawal_cannot_remove_current_support(self) -> None:
        support = make_assertion(
            relation_type="company_serves_route",
            subject_ref="company:Lumentum",
            object_ref=f"route_profile:{EXACT_PROFILE}",
            scope={
                "route_profile_id": EXACT_PROFILE,
                "product_ref": "product:TEST-PRODUCT-001",
                "service_kind": "demonstrated",
            },
            valid_time={"start": "2026-01-01", "end": None},
            modality="actual", polarity="supporting", epistemic_status="explicit_reviewed",
            origin_group="OG", adapter_version="v", source_refs=["source:TEST-SRC-001"],
            assertion_key="r2-6-support",
        )
        withdrawal = make_assertion(
            relation_type="company_serves_route",
            subject_ref="company:Lumentum",
            object_ref=f"route_profile:{EXACT_PROFILE}",
            scope={
                "route_profile_id": EXACT_PROFILE,
                "product_ref": "product:TEST-PRODUCT-001",
                "service_kind": "demonstrated",
            },
            valid_time={"start": "2027-01-01", "end": None},
            modality="actual", polarity="withdrawn", epistemic_status="explicit_reviewed",
            origin_group="OG", adapter_version="v", source_refs=["source:TEST-SRC-001"],
            assertion_key="r2-6-withdrawal",
            revises_assertion_ids=[support["assertion_id"]],
            revision_kind="withdraws",
            effective_at="2027-01-01", retroactive=False,
        )
        at_2026 = compute_slot_states([support, withdrawal], as_of="2026-06-01")[0]
        self.assertEqual(at_2026["effective_status"], "supported")
        self.assertEqual(at_2026["withdrawn_assertion_ids"], [])
        at_2027 = compute_slot_states([support, withdrawal], as_of="2027-06-01")[0]
        self.assertEqual(at_2027["effective_status"], "withdrawn")
        self.assertEqual(at_2027["withdrawn_assertion_ids"], [support["assertion_id"]])
        # effective_at is honoured independently of the valid_time window
        early = dict(withdrawal, assertion_id="RA-R2-6-EARLY", valid_time=None, effective_at="2027-01-01")
        self.assertEqual(
            compute_slot_states([support, early], as_of="2026-06-01")[0]["effective_status"],
            "supported",
        )

    def test_r2_6_cli_rejects_non_iso_as_of_and_query_mismatch(self) -> None:
        result = subprocess.run(
            [sys.executable, "tools/research/build_relation_index.py", "--as-of", "2026-9-1",
             "--output-dir", tempfile.mkdtemp()],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-ISO", result.stderr)
        result = subprocess.run(
            [sys.executable, "tools/research/build_relation_index.py", "--as-of", "FY2026Q3",
             "--output-dir", tempfile.mkdtemp()],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)

        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir)
            build = subprocess.run(
                [sys.executable, "tools/research/build_relation_index.py",
                 "--as-of", "2026-06-01", "--output-dir", str(out)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            mismatch = subprocess.run(
                [sys.executable, "tools/research/recompute_question_state.py",
                 "--assertion-index", str(out / "relation_assertion_index.jsonl"),
                 "--slot-states", str(out / "relation_slot_states.jsonl"),
                 "--output", str(out / "questions.jsonl"),
                 "--as-of", "2026-07-01"],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertNotEqual(mismatch.returncode, 0)
            self.assertIn("as_of", mismatch.stderr)
            matched = subprocess.run(
                [sys.executable, "tools/research/recompute_question_state.py",
                 "--assertion-index", str(out / "relation_assertion_index.jsonl"),
                 "--slot-states", str(out / "relation_slot_states.jsonl"),
                 "--output", str(out / "questions.jsonl"),
                 "--as-of", "2026-06-01"],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(matched.returncode, 0, matched.stderr)
            modality_mismatch = subprocess.run(
                [sys.executable, "tools/research/recompute_question_state.py",
                 "--assertion-index", str(out / "relation_assertion_index.jsonl"),
                 "--slot-states", str(out / "relation_slot_states.jsonl"),
                 "--output", str(out / "questions.jsonl"),
                 "--as-of", "2026-06-01", "--modality", "planned"],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertNotEqual(modality_mismatch.returncode, 0)
            self.assertIn("modality", modality_mismatch.stderr)

    def test_python_api_keeps_legacy_return_shapes(self) -> None:
        # compute_resolution historically accepted three positional arguments;
        # generate_diagnostic_questions historically returned only a list.
        from tools.research.recompute_question_state import compute_resolution

        status, _basis = compute_resolution([], None, {"relation_type": "company_serves_route"})
        self.assertEqual(status, "open")
        legacy = generate_diagnostic_questions([], [], RULES, ADAPTERS)
        self.assertIsInstance(legacy, list)
        extended = generate_diagnostic_questions(
            [], [], RULES, ADAPTERS, RELATION_TYPES, REGISTRY, return_deferred=True
        )
        self.assertIsInstance(extended, tuple)
        self.assertEqual(len(extended), 2)

    # ------------------------------------------------------------------
    # R2-7 revision provenance / corrects refusal
    # ------------------------------------------------------------------
    def test_r2_7_revision_provenance_preserved_and_corrects_refused(self) -> None:
        support = self._service_assertion("demonstrated", "RA-R2-7-SUPPORT")
        withdrawal = copy.deepcopy(support)
        withdrawal.update(
            {
                "assertion_id": "RA-R2-7-WITHDRAWAL",
                "polarity": "withdrawn",
                "source_refs": ["source:TEST-SRC-001", "disclosure:TEST-DISC-001"],
                "revises_assertion_ids": ["RA-R2-7-SUPPORT"],
                "revision_kind": "withdraws",
                "effective_at": "2026-08-01",
                "retroactive": False,
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar = Path(temp_dir) / "relation_assertions.yaml"
            sidecar.write_text(
                yaml.safe_dump({"assertions": [support, withdrawal]}, allow_unicode=True),
                encoding="utf-8",
            )
            assertions, _states = build_relation_graph(
                ROOT, CONTRACTS, sidecar, extra_registries=(TEST_REGISTRY,)
            )
        row = next(item for item in assertions if item["assertion_id"] == "RA-R2-7-WITHDRAWAL")
        self.assertEqual(row["revision_kind"], "withdraws")
        self.assertEqual(row["revises_assertion_ids"], ["RA-R2-7-SUPPORT"])
        self.assertEqual(row["effective_at"], "2026-08-01")
        self.assertIs(row["retroactive"], False)
        self.assertEqual(row["polarity"], "withdrawn")

        # `corrects` is refused through the real adapter path, not coerced.
        correction = copy.deepcopy(support)
        correction.update(
            {
                "assertion_id": "RA-R2-7-CORRECTS",
                "polarity": "withdrawn",
                "source_refs": ["source:TEST-SRC-001", "disclosure:TEST-DISC-001"],
                "revises_assertion_ids": ["RA-R2-7-SUPPORT"],
                "revision_kind": "corrects",
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar = Path(temp_dir) / "relation_assertions.yaml"
            sidecar.write_text(
                yaml.safe_dump({"assertions": [support, correction]}, allow_unicode=True),
                encoding="utf-8",
            )
            with self.assertRaises(RelationIndexError):
                build_relation_graph(ROOT, CONTRACTS, sidecar, extra_registries=(TEST_REGISTRY,))

    def test_r2_7_calls_corrects_is_never_coerced_to_limiting(self) -> None:
        # the calls adapter refuses a `corrects` evidence relationship outright
        from tools.research.build_relation_index import adapt_calls

        broken = copy.deepcopy(ADAPTERS)
        broken["relation_contract"] = RELATION_TYPES
        self.assertEqual(
            broken["adapters"]["calls_product_lifecycle"]["allowed_event_category"],
            ["product_stage"],
        )
        # sanity: the real ledger currently has no `corrects` relationship, so the
        # adapter path stays clean rather than being silently downgraded.
        rows = adapt_calls(ROOT, broken)
        self.assertTrue(rows)
        self.assertTrue(all(item["polarity"] != "withdrawn" for item in rows))

    # ------------------------------------------------------------------
    # R2-8 comparison_fields + identity_scope / assertion_context
    # ------------------------------------------------------------------
    def test_r2_8_comparison_fields_declared_and_context_separated(self) -> None:
        validate_relation_contract(RELATION_TYPES)
        for name, definition in RELATION_TYPES["relation_types"].items():
            self.assertTrue(definition["comparison_fields"], name)
            self.assertTrue(
                set(definition["slot_identity_fields"]) <= set(definition["comparison_fields"]),
                name,
            )
        broken = copy.deepcopy(RELATION_TYPES)
        broken["relation_types"]["company_serves_route"]["comparison_fields"] = ["subject_ref"]
        with self.assertRaises(RelationIndexError):
            validate_relation_contract(broken)

        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar = Path(temp_dir) / "relation_assertions.yaml"
            sidecar.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            assertions, states = build_relation_graph(
                ROOT, CONTRACTS, sidecar, extra_registries=(TEST_REGISTRY,)
            )
        for row in assertions:
            self.assertIn("identity_scope", row)
            self.assertIn("assertion_context", row)
            self.assertFalse(
                set(row["identity_scope"]) & set(row["assertion_context"])
            )
        for state in states:
            self.assertIn("identity_scope", state)
            self.assertIn("assertion_context", state)
        csr = next(
            row for row in assertions if row["relation_type"] == "company_serves_route"
        )
        self.assertEqual(
            csr["identity_scope"]["product_ref"], "product:TEST-PRODUCT-001"
        )
        self.assertEqual(csr["identity_scope"]["service_kind"], "demonstrated")

    def test_r2_8_conflict_uses_the_declared_comparison_surface(self) -> None:
        from tools.research.build_relation_index import assertions_conflict

        base = dict(
            relation_type="company_serves_route",
            subject_ref="company:Lumentum",
            object_ref=f"route_profile:{EXACT_PROFILE}",
            valid_time={"start": "2026-01-01", "end": None},
            modality="actual",
            epistemic_status="explicit_reviewed",
            origin_group="OG", adapter_version="v", source_refs=["s"],
        )
        support = make_assertion(
            **base, polarity="supporting", assertion_key="r2-8-s",
            scope={
                "route_profile_id": EXACT_PROFILE,
                "product_ref": "product:TEST-PRODUCT-001",
                "service_kind": "demonstrated",
            },
        )
        same_surface = make_assertion(
            **base, polarity="contradicting", assertion_key="r2-8-c",
            scope={
                "route_profile_id": EXACT_PROFILE,
                "product_ref": "product:TEST-PRODUCT-001",
                "service_kind": "demonstrated",
            },
        )
        other_kind = make_assertion(
            **base, polarity="contradicting", assertion_key="r2-8-ck",
            scope={
                "route_profile_id": EXACT_PROFILE,
                "product_ref": "product:TEST-PRODUCT-001",
                "service_kind": "shipping",
            },
        )
        self.assertTrue(assertions_conflict(support, same_surface, RELATION_TYPES))
        self.assertFalse(assertions_conflict(support, other_kind, RELATION_TYPES))

        us_support = make_assertion(
            **base,
            polarity="supporting",
            assertion_key="r2-8-us-support",
            scope={**support["scope"], "geography": "US"},
        )
        eu_contradiction = make_assertion(
            **base,
            polarity="contradicting",
            assertion_key="r2-8-eu-contradiction",
            scope={**support["scope"], "geography": "EU"},
        )
        self.assertFalse(assertions_conflict(us_support, eu_contradiction, RELATION_TYPES))
        self.assertNotEqual(
            compute_slot_states([us_support, eu_contradiction], relation_contract=RELATION_TYPES)[0]["effective_status"],
            "conflicted",
        )

    # ------------------------------------------------------------------
    # R2-9 scan.py raw sidecar must not KeyError
    # ------------------------------------------------------------------
    def test_r2_9_raw_sidecar_withdrawal_derives_identity_without_keyerror(self) -> None:
        raw = [
            {
                "assertion_id": "RA-RAW-1",
                "relation_type": "company_serves_route",
                "subject_ref": "company:Lumentum",
                "object_ref": f"route_profile:{EXACT_PROFILE}",
                "scope": {
                    "route_profile_id": EXACT_PROFILE,
                    "product_ref": "product:TEST-PRODUCT-001",
                    "service_kind": "demonstrated",
                },
                "valid_time": {"start": "2026-01-01", "end": None},
                "modality": "actual",
                "polarity": "supporting",
            },
            {
                "assertion_id": "RA-RAW-2",
                "relation_type": "company_serves_route",
                "subject_ref": "company:Lumentum",
                "object_ref": f"route_profile:{EXACT_PROFILE}",
                "scope": {
                    "route_profile_id": EXACT_PROFILE,
                    "product_ref": "product:TEST-PRODUCT-001",
                    "service_kind": "demonstrated",
                },
                "valid_time": {"start": "2026-06-01", "end": None},
                "modality": "actual",
                "polarity": "withdrawn",
                "revision_kind": "withdraws",
                "revises_assertion_ids": ["RA-RAW-1"],
                "effective_at": "2026-06-01",
                "retroactive": False,
            },
        ]
        # no slot_id anywhere: identity is derived from raw scope and the valid
        # withdrawal is accepted (the old implementation rejected this path).
        try:
            validate_withdrawals(raw, RELATION_TYPES)
        except KeyError as exc:  # pragma: no cover - regression guard
            self.fail(f"raw sidecar raised KeyError: {exc}")

        invalid_target = copy.deepcopy(raw)
        invalid_target[1]["revises_assertion_ids"] = ["RA-RAW-1"]
        invalid_target[0]["scope"]["product_ref"] = "product:TEST-PRODUCT-002"
        with self.assertRaises(RelationIndexError):
            validate_withdrawals(invalid_target, RELATION_TYPES)

        self_target = copy.deepcopy(raw)
        self_target[1]["revises_assertion_ids"] = ["RA-RAW-2"]
        with self.assertRaises(RelationIndexError):
            validate_withdrawals(self_target, RELATION_TYPES)

    def test_r2_11_supersedes_is_effective_and_keeps_new_assertion(self) -> None:
        """A supersession is a state effect, not a disguised withdrawal."""
        old = self._service_assertion("demonstrated", "RA-R2-11-OLD")
        superseder = copy.deepcopy(old)
        superseder.update(
            {
                "assertion_id": "RA-R2-11-NEW",
                "revision_kind": "supersedes",
                "revises_assertion_ids": [old["assertion_id"]],
                "effective_at": "2026-06-01",
                # The field is retained as provenance; this pilot does not
                # rewrite an earlier as_of projection when it is true.
                "retroactive": True,
            }
        )
        assertions, _states = self._build_index([old, superseder])
        before = next(
            state
            for state in compute_slot_states(
                assertions, as_of="2026-05-31", relation_contract=RELATION_TYPES
            )
            if state["relation_type"] == "company_serves_route"
            and state["scope"].get("product_ref") == "product:TEST-PRODUCT-001"
            and state["scope"].get("service_kind") == "demonstrated"
        )
        after = next(
            state
            for state in compute_slot_states(
                assertions, as_of="2026-06-01", relation_contract=RELATION_TYPES
            )
            if state["relation_type"] == "company_serves_route"
            and state["scope"].get("product_ref") == "product:TEST-PRODUCT-001"
            and state["scope"].get("service_kind") == "demonstrated"
        )
        self.assertEqual(before["active_assertion_ids"], [old["assertion_id"]])
        self.assertEqual(before["supporting_assertion_ids"], [old["assertion_id"]])
        self.assertEqual(after["active_assertion_ids"], [superseder["assertion_id"]])
        self.assertEqual(after["supporting_assertion_ids"], [superseder["assertion_id"]])
        self.assertEqual(after["superseded_assertion_ids"], [old["assertion_id"]])
        self.assertEqual(after["effective_status"], "supported")
        self.assertEqual(after["independent_origin_counts"]["supporting"], 1)

        # A superseder may not retire a target on another modality, context or
        # identity surface.  The production adapter rejects each mismatch.
        for suffix, mutate in (
            ("CONTEXT", lambda item: item["scope"].update({"geography": "EU"})),
            ("MODALITY", lambda item: item.update({"modality": "planned"})),
            (
                "SLOT",
                lambda item: item["scope"].update(
                    {"product_ref": "product:TEST-PRODUCT-002"}
                ),
            ),
        ):
            mismatched = copy.deepcopy(superseder)
            mismatched["assertion_id"] = f"RA-R2-11-{suffix}"
            mutate(mismatched)
            with self.assertRaises(RelationIndexError):
                self._build_index([old, mismatched])

    def test_r2_12_non_comparable_contradictions_do_not_block_resolution(self) -> None:
        support = self._service_assertion("demonstrated", "RA-R2-12-SUPPORT")
        contradictions: list[dict[str, Any]] = []
        for index, (field, value) in enumerate(
            (
                ("geography", "EU"),
                ("customer", "customer-B"),
                ("program_id", "program-B"),
            ),
            start=1,
        ):
            contradiction = copy.deepcopy(support)
            contradiction.update(
                {
                    "assertion_id": f"RA-R2-12-C{index}",
                    "polarity": "contradicting",
                    "supports": [],
                    "does_not_support": ["claim:TEST-CLAIM-001"],
                }
            )
            contradiction["scope"] = copy.deepcopy(support["scope"])
            contradiction["scope"][field] = value
            contradictions.append(contradiction)
        modality_contradiction = copy.deepcopy(support)
        modality_contradiction.update(
            {
                "assertion_id": "RA-R2-12-MODALITY",
                "polarity": "contradicting",
                "modality": "planned",
                "supports": [],
                "does_not_support": ["claim:TEST-CLAIM-001"],
            }
        )
        contradictions.append(modality_contradiction)

        assertions, states = self._build_index([support, *contradictions])
        target = next(
            state
            for state in states
            if state["relation_type"] == "company_serves_route"
            and state["scope"].get("product_ref") == "product:TEST-PRODUCT-001"
            and state["scope"].get("service_kind") == "demonstrated"
        )
        self.assertEqual(target["effective_status"], "supported")
        self.assertEqual(target["contradicting_assertion_ids"], [])
        self.assertCountEqual(
            target["non_comparable_contradicting_assertion_ids"],
            [item["assertion_id"] for item in contradictions],
        )
        self.assertEqual(target["independent_origin_counts"]["contradicting"], 0)

        acceptance = RULES["rules"][0]["acceptance"]
        target_assertions = [
            item for item in assertions if item["slot_id"] == target["slot_id"]
        ]
        status, _basis = compute_resolution(
            target_assertions,
            target,
            acceptance,
            service_kind="demonstrated",
        )
        self.assertEqual(status, "satisfied")

    # ------------------------------------------------------------------
    # R2-10 deterministic, root-independent output
    # ------------------------------------------------------------------
    def test_r2_10_manifest_revalidates_content_not_only_build_id(self) -> None:
        manifest_a = {
            "build_id": "BUILD-SAME", "data_hash": "HASH-1",
            "assertion_count": 3, "slot_count": 2, "as_of": None, "modality": None,
            "contracts": {"relation_types.yaml": "x"},
        }
        manifest_b = dict(manifest_a, data_hash="HASH-2")
        with self.assertRaises(QuestionStateError):
            _require_same_build(manifest_a, manifest_b)
        manifest_c = dict(manifest_a, slot_count=99)
        with self.assertRaises(QuestionStateError):
            _require_same_build(manifest_a, manifest_c)
        manifest_d = dict(manifest_a, contracts={"relation_types.yaml": "y"})
        with self.assertRaises(QuestionStateError):
            _require_same_build(manifest_a, manifest_d)
        with self.assertRaises(QuestionStateError):
            _require_query_matches_manifest(manifest_a, "2026-01-01", None)

        # The production projection path must recompute actual JSONL row hashes,
        # not merely compare the manifest's build_id.  A one-field mutation is
        # rejected while an unmodified pair passes with all three contracts.
        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar = Path(temp_dir) / "relation_assertions.yaml"
            sidecar.write_text(yaml.safe_dump({"assertions": []}), encoding="utf-8")
            assertions, states = build_relation_graph(ROOT, CONTRACTS, sidecar)
            manifest = compute_build_manifest(
                assertions,
                states,
                CONTRACTS,
                CONTRACTS / "question_generation_rules.yaml",
                CONTRACTS / "relation_adapters.yaml",
            )
            self.assertEqual(
                _require_same_build(
                    manifest,
                    manifest,
                    CONTRACTS / "question_generation_rules.yaml",
                    CONTRACTS / "relation_adapters.yaml",
                    assertion_rows=assertions,
                    slot_rows=states,
                    relation_types_path=CONTRACTS / "relation_types.yaml",
                )["build_id"],
                manifest["build_id"],
            )
            altered = copy.deepcopy(assertions)
            altered[0]["origin_group"] = "tampered"
            with self.assertRaises(QuestionStateError):
                _require_same_build(
                    manifest,
                    manifest,
                    CONTRACTS / "question_generation_rules.yaml",
                    CONTRACTS / "relation_adapters.yaml",
                    assertion_rows=altered,
                    slot_rows=states,
                    relation_types_path=CONTRACTS / "relation_types.yaml",
                )
            with self.assertRaises(QuestionStateError):
                _require_same_build(
                    manifest,
                    manifest,
                    CONTRACTS / "question_generation_rules.yaml",
                    CONTRACTS / "relation_adapters.yaml",
                    assertion_rows=assertions,
                    slot_rows=states,
                )

    def test_r2_10_generated_output_is_identical_across_worktree_roots(self) -> None:
        needed = ["points.csv", "route_bom.csv", "relation_assertions.yaml"]
        with tempfile.TemporaryDirectory() as temp_dir:
            roots = []
            for name in ("root_a", "root_b"):
                root = Path(temp_dir) / name
                root.mkdir()
                for item in needed:
                    shutil.copy2(ROOT / item, root / item)
                shutil.copytree(ROOT / "contracts", root / "contracts")
                shutil.copytree(ROOT / "calls", root / "calls")
                (root / "out").mkdir()
                roots.append(root)
            outputs = []
            for root in roots:
                out = root / "out"
                build = subprocess.run(
                    [sys.executable, "tools/research/build_relation_index.py",
                     "--root", str(root), "--output-dir", str(out),
                     "--as-of", "2026-09-02"],
                    cwd=ROOT, capture_output=True, text=True,
                )
                self.assertEqual(build.returncode, 0, build.stderr)
                recompute = subprocess.run(
                    [sys.executable, "tools/research/recompute_question_state.py",
                     "--assertion-index", str(out / "relation_assertion_index.jsonl"),
                     "--slot-states", str(out / "relation_slot_states.jsonl"),
                     "--rules", str(root / "contracts/question_generation_rules.yaml"),
                     "--adapters", str(root / "contracts/relation_adapters.yaml"),
                     "--contracts-dir", str(root / "contracts"),
                     "--output", str(out / "generated_diagnostic_questions.jsonl"),
                     "--as-of", "2026-09-02"],
                    cwd=ROOT, capture_output=True, text=True,
                )
                self.assertEqual(recompute.returncode, 0, recompute.stderr)
                outputs.append(out)
            left_root, right_root = roots
            for name in (
                "relation_assertion_index.jsonl",
                "relation_slot_states.jsonl",
                "relation_leads.jsonl",
                "relation_lead_funnel.json",
                "generated_diagnostic_questions.jsonl",
            ):
                left = (outputs[0] / name).read_bytes()
                right = (outputs[1] / name).read_bytes()
                self.assertEqual(
                    hashlib.sha256(left).hexdigest(),
                    hashlib.sha256(right).hexdigest(),
                    f"{name} differs between worktree roots",
                )
                # no absolute path of either root may leak into the projection
                for leaked in (left_root, right_root, ROOT):
                    self.assertNotIn(
                        str(leaked).encode(), left, f"{name} leaks {leaked}"
                    )
                    self.assertNotIn(
                        str(leaked).encode(), right, f"{name} leaks {leaked}"
                    )

    # ------------------------------------------------------------------
    # helpers for the round-2 scenarios
    # ------------------------------------------------------------------
    def _index(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar = Path(temp_dir) / "relation_assertions.yaml"
            sidecar.write_text(
                yaml.safe_dump({"assertions": []}, allow_unicode=True), encoding="utf-8"
            )
            return build_relation_graph(ROOT, CONTRACTS, sidecar, extra_registries=(TEST_REGISTRY,))

    def _build_index(
        self, items: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Run the real sidecar adapter for a controlled assertion set."""
        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar = Path(temp_dir) / "relation_assertions.yaml"
            sidecar.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": "relation_assertions_v1",
                        "fixture_only": True,
                        "assertions": items,
                    },
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )
            return build_relation_graph(
                ROOT, CONTRACTS, sidecar, extra_registries=(TEST_REGISTRY,)
            )

    def _complete_cells(self, assertions: list[dict[str, Any]]) -> list[str]:
        """The minimal cell set that satisfies every LPO requirement group."""
        profile = next(
            item for item in ADAPTERS["route_profiles"]
            if item["route_profile_id"] == EXACT_PROFILE
        )
        group_cells = project_group_cells(assertions, EXACT_PROFILE)
        complete, _groups, reason = evaluate_coverage(profile, set(), group_cells)
        self.assertFalse(complete)
        self.assertEqual(reason, "incomplete_actual_coverage")
        cells: set[str] = set()
        for group in profile["requirement_groups"]:
            projected = sorted(group_cells.get(group["group_id"]) or ())
            self.assertTrue(projected, f"{group['group_id']} has no projected cells")
            if group.get("kind") == "all_of":
                cells.update(projected)
            else:
                cells.add(projected[0])
        complete, groups, reason = evaluate_coverage(profile, cells, group_cells)
        self.assertTrue(complete, reason)
        self.assertTrue(all(item["satisfied"] for item in groups))
        return sorted(cells)

    def _service_assertion(self, service_kind: str, assertion_id: str) -> dict[str, Any]:
        item = copy.deepcopy(load_yaml(FIXTURE)["assertions"][0])
        item["assertion_id"] = assertion_id
        item["scope"]["service_kind"] = service_kind
        return item

    def _pool(
        self,
        cells: list[str],
        modality: str,
        extra: list[dict[str, Any]],
        registry: dict[str, dict[str, Any]] | None = None,
        prior_state: PriorQuestionState | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar = Path(temp_dir) / "relation_assertions.yaml"
            sidecar.write_text(
                yaml.safe_dump({"assertions": extra}, allow_unicode=True), encoding="utf-8"
            )
            assertions, _states = build_relation_graph(
                ROOT, CONTRACTS, sidecar, extra_registries=(TEST_REGISTRY,)
            )
        caps = [
            make_assertion(
                relation_type="company_has_capability_at",
                subject_ref="company:Lumentum",
                object_ref=f"capability_cell:{cell_id}",
                scope={"capability_cell_id": cell_id},
                valid_time={"start": "2026-01-01"},
                modality=modality,
                polarity="supporting",
                epistemic_status="source_encoded",
                origin_group=f"OG-R2-CAP-{index}",
                adapter_version="points_company_capability_v1",
                source_refs=[f"points.csv#R2-{index}"],
                assertion_key=f"r2-cap-{index}-{cell_id}",
            )
            for index, cell_id in enumerate(cells)
        ]
        pool = [
            item for item in assertions if item["relation_type"] != "capability_matches_route"
        ] + caps
        pool = pool + derive_capability_matches(pool, cfg())
        pool.sort(key=lambda item: item["assertion_id"])
        states = compute_slot_states(pool, relation_contract=RELATION_TYPES)
        questions, deferred = generate_diagnostic_questions(
            pool, states, RULES, ADAPTERS, RELATION_TYPES,
            REGISTRY if registry is None else registry, prior_state,
            return_deferred=True,
        )
        return pool, states, questions, deferred

    def _questions_for_cells(
        self, cells: list[str], modality: str
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        _pool, _states, questions, deferred = self._pool(cells, modality, [])
        return questions, deferred

    @staticmethod
    def _for_company(questions: list[dict[str, Any]], subject_ref: str) -> list[dict[str, Any]]:
        return [item for item in questions if item["target"]["subject_ref"] == subject_ref]


if __name__ == "__main__":
    unittest.main()
