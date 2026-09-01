from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

from tools.research.build_relation_index import (
    ROOT,
    assertions_conflict,
    build_relation_graph,
    compute_slot_states,
    load_yaml,
    make_assertion,
)
from tools.research.recompute_question_state import generate_diagnostic_questions


CONTRACTS = ROOT / "contracts"
RULES = load_yaml(CONTRACTS / "question_generation_rules.yaml")
ADAPTERS = load_yaml(CONTRACTS / "relation_adapters.yaml")
EXACT_PROFILE = "RPF-800G-DR8-LPO-SIPH-FPP-V1"
OTHER_PROFILE = "RPF-800G-DR8-FRO-DISCRETE-FPP-V1"
FIXTURE = (
    ROOT
    / "tests/fixtures/research_graph/relation_assertions_exact_support.yaml"
)


class RelationGraphClosureTests(unittest.TestCase):
    def explicit_support(self) -> dict[str, Any]:
        return copy.deepcopy(load_yaml(FIXTURE)["assertions"][0])

    def build_with(
        self, items: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
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
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            assertions, states = build_relation_graph(ROOT, CONTRACTS, sidecar)
        questions = generate_diagnostic_questions(assertions, states, RULES, ADAPTERS)
        return assertions, states, questions

    @staticmethod
    def question_for(questions: list[dict[str, Any]], company: str) -> dict[str, Any]:
        target = f"company:{company}"
        return next(item for item in questions if item["target"]["subject_ref"] == target)

    def test_capability_and_requirement_only_make_match_and_candidate_question(self) -> None:
        assertions, _, questions = self.build_with([])
        relation_types = {item["relation_type"] for item in assertions}
        self.assertIn("company_has_capability_at", relation_types)
        self.assertIn("route_requires_capability", relation_types)
        self.assertIn("capability_matches_route", relation_types)
        self.assertNotIn("company_serves_route", relation_types)

        question = self.question_for(questions, "Lumentum")
        self.assertEqual(question["workflow_status"], "candidate")
        self.assertEqual(question["resolution_status"], "open")
        self.assertEqual(question["generated_by"]["reason"], "missing_relation")
        self.assertEqual(question["target"]["scope"]["route_profile_id"], EXACT_PROFILE)
        self.assertIn("800G DR8", question["question_text"])
        self.assertNotIn("DR4", question["question_text"])

    def test_component_product_evidence_cannot_close_service_question(self) -> None:
        assertions, _, questions = self.build_with([])
        self.assertTrue(
            any(item["relation_type"] == "product_has_lifecycle_stage" for item in assertions)
        )
        question = self.question_for(questions, "Lumentum")
        self.assertEqual(question["resolution_status"], "open")
        self.assertFalse(question["acceptance"]["component_product_evidence_is_sufficient"])

    def test_exact_reviewed_service_assertion_satisfies_question(self) -> None:
        _, _, questions = self.build_with([self.explicit_support()])
        question = self.question_for(questions, "Lumentum")
        self.assertEqual(question["resolution_status"], "satisfied")
        self.assertEqual(
            question["state_basis"]["qualified_assertion_ids"],
            ["RA-TEST-LITE-EXACT-SERVICE"],
        )

    def test_different_route_profile_does_not_close_question(self) -> None:
        assertion = self.explicit_support()
        assertion["assertion_id"] = "RA-TEST-LITE-OTHER-PROFILE"
        assertion["object_ref"] = f"route_profile:{OTHER_PROFILE}"
        assertion["scope"]["route_profile_id"] = OTHER_PROFILE
        _, _, questions = self.build_with([assertion])
        question = self.question_for(questions, "Lumentum")
        self.assertEqual(question["resolution_status"], "open")

    def test_withdrawal_reopens_and_same_condition_conflict_is_open_conflict(self) -> None:
        support = self.explicit_support()
        withdrawal = copy.deepcopy(support)
        withdrawal.update(
            {
                "assertion_id": "RA-TEST-LITE-WITHDRAWAL",
                "polarity": "withdrawn",
                "origin_group": "OG-TEST-LITE-WITHDRAWAL",
                "source_refs": ["test_fixture:withdrawal"],
                "withdraws_assertion_ids": [support["assertion_id"]],
            }
        )
        _, _, questions = self.build_with([support, withdrawal])
        self.assertEqual(
            self.question_for(questions, "Lumentum")["resolution_status"], "reopened"
        )

        contradiction = copy.deepcopy(support)
        contradiction.update(
            {
                "assertion_id": "RA-TEST-LITE-CONTRADICTION",
                "polarity": "contradicting",
                "origin_group": "OG-TEST-LITE-CONTRADICTION",
                "source_refs": ["test_fixture:contradiction"],
            }
        )
        _, _, questions = self.build_with([support, contradiction])
        self.assertEqual(
            self.question_for(questions, "Lumentum")["resolution_status"], "conflicted"
        )

    def test_planned_ramp_and_current_demonstrated_are_not_automatic_conflict(self) -> None:
        demonstrated = make_assertion(
            relation_type="product_has_lifecycle_stage",
            subject_ref="product_or_program:TEST-PRODUCT",
            object_ref="lifecycle_stage:demonstrated",
            scope={"program_id": "TEST-PRODUCT"},
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
            scope={"program_id": "TEST-PRODUCT"},
            valid_time={"start": "2027-01-01", "end": None},
            modality="planned",
            polarity="contradicting",
            epistemic_status="source_encoded",
            origin_group="OG-TEST-RAMP",
            adapter_version="test_v1",
            source_refs=["test:ramp"],
            assertion_key="ramp",
        )
        self.assertFalse(assertions_conflict(demonstrated, ramp))
        self.assertTrue(all(item["effective_status"] != "conflicted" for item in compute_slot_states([demonstrated, ramp])))

    def test_same_origin_duplicates_do_not_raise_independent_evidence_count(self) -> None:
        first = self.explicit_support()
        duplicate = copy.deepcopy(first)
        duplicate["assertion_id"] = "RA-TEST-LITE-DUPLICATE"
        duplicate["source_refs"] = ["test_fixture:same_origin_duplicate"]
        assertions, states, _ = self.build_with([first, duplicate])
        target_assertion = next(
            item for item in assertions if item["assertion_id"] == first["assertion_id"]
        )
        state = next(item for item in states if item["slot_id"] == target_assertion["slot_id"])
        self.assertEqual(state["independent_origin_counts"]["supporting"], 1)
        self.assertEqual(len(state["supporting_assertion_ids"]), 2)

    def test_repeated_run_is_deterministic_and_questions_are_deduplicated(self) -> None:
        assertions_a, states_a, questions_a = self.build_with([])
        assertions_b, states_b, questions_b = self.build_with([])
        self.assertEqual(assertions_a, assertions_b)
        self.assertEqual(states_a, states_b)
        self.assertEqual(questions_a, questions_b)
        fingerprints = [item["dedupe_fingerprint"] for item in questions_a]
        self.assertEqual(len(fingerprints), len(set(fingerprints)))


if __name__ == "__main__":
    unittest.main()
