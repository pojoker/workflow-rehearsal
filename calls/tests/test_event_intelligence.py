from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from calls.event_intelligence import EventLedgerError, derive_event_projection, load_event_facts
from calls.renderer import render
from calls.schema import FILES
from calls.validator import validate
from calls.workbuddy import render_intelligence_section


ROOT = Path(__file__).resolve().parents[2]


class EventIntelligenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "calls").mkdir()
        for filename in FILES:
            shutil.copy2(ROOT / "calls" / filename, self.root / "calls" / filename)
        for filename in ("tree.yaml", "route_bom.csv", "points.csv"):
            shutil.copy2(ROOT / filename, self.root / filename)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _rows(self, filename: str) -> tuple[list[str], list[dict[str, str]]]:
        path = self.root / "calls" / filename
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), list(reader)

    def _write(self, filename: str, fields: list[str], rows: list[dict[str, str]]) -> None:
        path = self.root / "calls" / filename
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def mutate(self, filename: str, row_id: str, changes: dict[str, str]) -> None:
        fields, rows = self._rows(filename)
        id_field = fields[0]
        row = next(item for item in rows if item[id_field] == row_id)
        row.update(changes)
        self._write(filename, fields, rows)

    def append(self, filename: str, row: dict[str, str]) -> None:
        fields, rows = self._rows(filename)
        rows.append({field: row.get(field, "") for field in fields})
        self._write(filename, fields, rows)

    def add_independent_support(self, origin_group: str = "OG_CSCO_CONFIRM") -> None:
        self.append("disclosures.csv", {
            "disclosure_id": "D_CSCO_CONFIRM",
            "publisher_entity_id": "CSCO",
            "title": "Customer confirmation",
            "disclosure_type": "customer_release",
            "content_class": "commercial_disclosure",
            "provenance_class": "counterparty",
            "canonical_url": "https://investor.cisco.com/example-confirmation",
            "origin_group": origin_group,
            "published_at": "2026-03-10",
            "discovered_at": "2026-08-09",
            "retrieved_at": "2026-08-09",
            "reviewed_at": "2026-08-09",
            "retrieval_status": "retrieved",
            "processing_status": "anchor_reviewed",
            "review_scope": "customer confirmation paragraph",
        })
        self.append("event_claims.csv", {
            "event_claim_id": "ECL900",
            "disclosure_id": "D_CSCO_CONFIRM",
            "claimant_entity_id": "CSCO",
            "claimant_role": "customer",
            "statement_kind": "fact_assertion",
            "quote": "Customer independently confirms the order.",
            "anchor": "opening paragraph",
            "summary": "独立客户确认",
            "review_status": "anchor_reviewed",
            "reviewed_at": "2026-08-09",
        })
        self.append("event_evidence.csv", {
            "evidence_id": "EE900",
            "event_id": "EV001",
            "event_claim_id": "ECL900",
            "relationship": "supports",
            "independence_class": "counterparty",
            "origin_group": origin_group,
        })

    def test_migration_samples_and_expansion_events_are_source_traced(self) -> None:
        projection = derive_event_projection(load_event_facts(self.root))
        self.assertEqual(len(projection["radar_events"]), 21)
        event_by_id = {row["event_id"]: row for row in projection["radar_events"]}
        self.assertEqual(set(event_by_id), {f"EV{number:03d}" for number in range(1, 22)})
        aaoi, lite = event_by_id["EV001"], event_by_id["EV002"]
        self.assertEqual((aaoi["lifecycle_stage"], aaoi["event_status"]), ("volume_order", "asserted"))
        self.assertEqual(aaoi["evidence"][0]["published_at"], "2026-03-09")
        self.assertEqual((lite["lifecycle_stage"], lite["evidence"][0]["event_claim_id"]), ("demonstrated", "ECL002"))
        self.assertEqual(
            {row["primary_subject_id"] for row in projection["radar_events"]},
            {"AAOI", "LITE", "AVGO", "MRVL", "NOK", "CIEN", "MTSI", "CRDO"},
        )
        self.assertEqual(projection["coverage_summary"]["disclosure_count"], 38)
        self.assertEqual(
            projection["coverage_summary"]["processing_status_counts"],
            {"anchor_reviewed": 30, "no_relevant_claims": 8},
        )
        self.assertEqual(projection["discovery_queue"], [])

    def test_expanded_event_regressions_preserve_stages_evidence_and_watch_boundary(self) -> None:
        facts = load_event_facts(self.root)
        projection = derive_event_projection(facts)
        event_by_id = {row["event_id"]: row for row in projection["radar_events"]}

        vesta = event_by_id["EV012"]
        self.assertEqual((vesta["event_category"], vesta["lifecycle_stage"]), ("product_stage", "announced"))
        self.assertNotEqual(vesta["lifecycle_stage"], "demonstrated")

        for event_id, category in (("EV013", "capital_relationship"), ("EV014", "supply_chain_arrangement")):
            event = event_by_id[event_id]
            self.assertEqual((event["event_category"], event["event_status"]), (category, "corroborated"))
            self.assertEqual(len(event["evidence"]), 2)
            self.assertEqual(len({item["evidence_id"] for item in event["evidence"]}), 2)
            self.assertEqual(len({item["origin_group"] for item in event["evidence"]}), 2)

        self.assertEqual(event_by_id["EV015"]["lifecycle_stage"], "sampling")
        self.assertEqual(event_by_id["EV008"]["previous_event_id"], "EV015")
        self.assertEqual(event_by_id["EV016"]["lifecycle_stage"], "sampling")

        acquisition, completion = event_by_id["EV017"], event_by_id["EV018"]
        self.assertEqual(acquisition["program_id"], completion["program_id"])
        self.assertEqual(completion["previous_event_id"], "EV017")
        self.assertEqual(
            (acquisition["event_category"], acquisition["lifecycle_stage"], completion["event_category"], completion["lifecycle_stage"]),
            ("capital_relationship", "announced", "capital_relationship", "not_applicable"),
        )

        ciena_transcript_events = {
            "EV019": (
                "CL063",
                "commercial_adoption",
                "first_shipment",
                "https://s25.q4cdn.com/550667411/files/doc_financials/2025/q3/Transcript-Cienas-Fiscal-Third-Quarter-2025-Financial-Results-Conference-Call.pdf",
            ),
            "EV020": (
                "CL068",
                "capacity_constraint",
                "not_applicable",
                "https://s25.q4cdn.com/550667411/files/doc_events/2026/03/Q1-2026-Earnings-Call-Transcript.pdf",
            ),
            "EV021": (
                "CL072",
                "commercial_adoption",
                "announced",
                "https://s25.q4cdn.com/550667411/files/content_files/Ciena-Fiscal-Q2-2026-Financial-Results-Call.pdf",
            ),
        }
        for event_id, (legacy_claim_id, category, stage, official_transcript_url) in ciena_transcript_events.items():
            event = event_by_id[event_id]
            self.assertEqual((event["event_category"], event["lifecycle_stage"]), (category, stage))
            evidence = event["evidence"]
            self.assertEqual(len(evidence), 1)
            self.assertEqual(facts["event_claims"][evidence[0]["event_claim_id"]]["legacy_claim_id"], legacy_claim_id)
            self.assertEqual(evidence[0]["url"], official_transcript_url)

        _, universe = self._rows("universe.csv")
        quarterly_company_ids = {
            row["company_id"] for row in universe if row["enabled"] == "yes"
        }
        self.assertNotIn("WATCH_IQE", quarterly_company_ids)

    def test_nokia_quarterly_sequence_keeps_actual_guidance_and_constraint_distinct(self) -> None:
        projection = derive_event_projection(load_event_facts(self.root))
        event_by_id = {row["event_id"]: row for row in projection["radar_events"]}
        self.assertEqual(event_by_id["EV009"]["lifecycle_stage"], "announced")
        self.assertEqual(
            event_by_id["EV009"]["evidence"][0]["statement_kind"],
            "fact_assertion",
        )
        self.assertEqual(event_by_id["EV010"]["lifecycle_stage"], "announced")
        self.assertEqual(
            event_by_id["EV010"]["evidence"][0]["statement_kind"],
            "forward_looking",
        )
        self.assertEqual(event_by_id["EV011"]["event_category"], "capacity_constraint")
        self.assertEqual(event_by_id["EV011"]["lifecycle_stage"], "not_applicable")
        self.assertEqual(
            event_by_id["EV011"]["evidence"][0]["statement_kind"],
            "corporate_narrative",
        )

    def test_expanded_companies_have_four_available_official_quarters(self) -> None:
        _, universe = self._rows("universe.csv")
        _, sources = self._rows("sources.csv")
        expanded = {"AVGO", "MRVL", "NOK", "CIEN", "MTSI", "CRDO"}
        enabled = {row["company_id"] for row in universe if row["enabled"] == "yes"}
        self.assertTrue(expanded <= enabled)
        for company_id in expanded:
            quarterly = [
                row for row in sources
                if row["company_id"] == company_id and row["source_scope"] == "quarterly"
            ]
            self.assertEqual(len(quarterly), 4, company_id)
            self.assertTrue(all(row["availability"] == "available" for row in quarterly))
            self.assertTrue(all(row["source_grade"] == "A" for row in quarterly))

    def test_second_batch_is_partitioned_by_disclosure_signal(self) -> None:
        _, universe = self._rows("universe.csv")
        _, sources = self._rows("sources.csv")
        _, watch_rows = self._rows("watch_entities.csv")
        _, candidates = self._rows("company_candidates.csv")
        quarterly_ids = {
            "SOI", "SUMITOMO", "FURUKAWA", "POET", "SIVERS", "SANM",
            "CLS", "MYCRONIC", "OXIG", "VIAV", "ADTN", "WIWYNN", "GLW",
        }
        watch_ids = {
            "WATCH_FUJIKURA", "WATCH_MELCO", "WATCH_ASE", "WATCH_SUSS",
            "WATCH_SAMCO", "WATCH_KEYS", "WATCH_ACCTON",
        }
        enabled = {row["company_id"] for row in universe if row["enabled"] == "yes"}
        active_watch = {
            row["entity_id"] for row in watch_rows
            if row["monitoring_status"] == "active"
        }
        self.assertTrue(quarterly_ids <= enabled)
        self.assertTrue(watch_ids <= active_watch)
        self.assertFalse(watch_ids & enabled)
        for company_id in quarterly_ids:
            quarterly = [
                row for row in sources
                if row["company_id"] == company_id and row["source_scope"] == "quarterly"
            ]
            self.assertEqual(len(quarterly), 4, company_id)
            self.assertTrue(all(row["availability"] == "available" for row in quarterly))
            self.assertTrue(all(row["source_grade"] == "A" for row in quarterly))
        promoted = {
            row["promoted_entity_id"] for row in candidates
            if row["priority"] == "P2" and row["verification_status"] == "promoted"
        }
        self.assertEqual(promoted, quarterly_ids | watch_ids)

    def test_first_party_cannot_self_corroborate(self) -> None:
        self.mutate("events.csv", "EV001", {"event_status": "corroborated"})
        with self.assertRaisesRegex(EventLedgerError, "lacks independent supporting origin"):
            load_event_facts(self.root)

    def test_corroborated_requires_first_party_asserted_origin(self) -> None:
        self.add_independent_support()
        self.mutate("event_evidence.csv", "EE001", {"relationship": "contradicts"})
        self.mutate("events.csv", "EV001", {"event_status": "corroborated"})
        # A contradictory first-party row still identifies the first-party
        # origin, so remove it entirely to exercise the required asserted base.
        fields, rows = self._rows("event_evidence.csv")
        self._write("event_evidence.csv", fields, [row for row in rows if row["evidence_id"] != "EE001"])
        with self.assertRaisesRegex(EventLedgerError, "lacks first-party asserted origin"):
            load_event_facts(self.root)

    def test_independent_counterparty_origin_can_corroborate(self) -> None:
        self.add_independent_support()
        self.mutate("events.csv", "EV001", {"event_status": "corroborated"})
        projection = derive_event_projection(load_event_facts(self.root))
        event = next(row for row in projection["radar_events"] if row["event_id"] == "EV001")
        self.assertEqual(event["event_status"], "corroborated")
        self.assertEqual(len(event["evidence"]), 2)

    def test_same_origin_cannot_count_as_independent(self) -> None:
        self.add_independent_support("OG_AAOI_20260309_ORDER")
        self.mutate("events.csv", "EV001", {"event_status": "corroborated"})
        with self.assertRaisesRegex(EventLedgerError, "lacks independent supporting origin"):
            load_event_facts(self.root)

    def test_supply_chain_arrangement_lacks_corroboration_without_counterparty_evidence(self) -> None:
        self.mutate("events.csv", "EV014", {"event_status": "corroborated"})
        fields, rows = self._rows("event_evidence.csv")
        self._write(
            "event_evidence.csv",
            fields,
            [row for row in rows if row["evidence_id"] != "EE016"],
        )
        with self.assertRaisesRegex(EventLedgerError, "lacks independent supporting origin"):
            load_event_facts(self.root)

    def test_first_party_provenance_cannot_spoof_counterparty_independence(self) -> None:
        self.mutate("event_evidence.csv", "EE001", {"independence_class": "counterparty"})
        self.mutate("events.csv", "EV001", {"event_status": "corroborated"})
        with self.assertRaisesRegex(EventLedgerError, "conflicts with disclosure provenance"):
            load_event_facts(self.root)

    def test_technical_blog_alone_cannot_support_scaled_stage(self) -> None:
        self.mutate("events.csv", "EV002", {"lifecycle_stage": "scaled"})
        with self.assertRaisesRegex(EventLedgerError, "technical blog alone"):
            load_event_facts(self.root)

    def test_retrieval_time_is_required_but_never_used_as_event_time(self) -> None:
        projection = derive_event_projection(load_event_facts(self.root))
        event = next(row for row in projection["radar_events"] if row["event_id"] == "EV001")
        self.assertEqual(event["occurred_start"], "2026-03-09")
        self.assertEqual(event["evidence"][0]["retrieved_at"], "2026-08-04")
        self.assertNotEqual(event["occurred_start"], event["evidence"][0]["retrieved_at"])
        self.mutate("disclosures.csv", "D_AAOI_20260309_ORDER", {"retrieved_at": ""})
        with self.assertRaisesRegex(EventLedgerError, "lacks retrieval time"):
            load_event_facts(self.root)

    def test_no_relevant_claims_requires_traceable_review(self) -> None:
        self.mutate("disclosures.csv", "D_AAOI_20260309_ORDER", {
            "processing_status": "no_relevant_claims",
            "reviewed_at": "",
            "review_scope": "",
        })
        with self.assertRaisesRegex(EventLedgerError, "lacks reviewed_at/review_scope"):
            load_event_facts(self.root)

    def test_origin_group_must_match_disclosure(self) -> None:
        self.mutate("event_evidence.csv", "EE001", {"origin_group": "OG_DRIFT"})
        with self.assertRaisesRegex(EventLedgerError, "differs from disclosure"):
            load_event_facts(self.root)

    def test_legacy_claim_mapping_is_machine_checkable(self) -> None:
        self.mutate("event_claims.csv", "ECL002", {"legacy_claim_id": "CL001"})
        with self.assertRaisesRegex(EventLedgerError, "legacy claim/source mismatch"):
            load_event_facts(self.root)

    def test_projection_is_independent_of_dictionary_order(self) -> None:
        facts = load_event_facts(self.root)
        reversed_facts = {
            key: dict(reversed(list(value.items()))) if isinstance(value, dict) else value
            for key, value in facts.items()
        }
        self.assertEqual(derive_event_projection(facts), derive_event_projection(reversed_facts))

    def test_previous_event_chain_cannot_cycle(self) -> None:
        self.mutate("events.csv", "EV001", {"program_id": "PRG_SHARED", "previous_event_id": "EV002"})
        self.mutate("events.csv", "EV002", {"program_id": "PRG_SHARED", "previous_event_id": "EV001"})
        with self.assertRaisesRegex(EventLedgerError, "cycle detected"):
            load_event_facts(self.root)

    def test_main_validator_includes_event_ledger(self) -> None:
        messages = validate(self.root)
        self.assertIn("21 reviewed radar events", messages[-1])
        self.mutate("events.csv", "EV001", {"primary_subject_id": "UNKNOWN"})
        with self.assertRaisesRegex(Exception, "unknown primary_subject_id"):
            validate(self.root)

    def test_workbuddy_event_radar_exposes_status_quote_anchor_and_links(self) -> None:
        render(self.root)
        section = render_intelligence_section(
            self.root / "calls" / "out" / "panorama-intelligence.csv",
            positioning_path=self.root / "calls" / "out" / "positioning.json",
            event_path=self.root / "calls" / "out" / "event-intelligence.json",
        )
        self.assertIn("本期公司事件", section)
        self.assertIn("asserted", section)
        self.assertIn("Actual", section)
        self.assertIn("Demo", section)
        self.assertIn("Narrative", section)
        self.assertIn("原文短引", section)
        self.assertIn("数据版本：", section)
        self.assertIn("official blog lines 24-30", section)
        self.assertIn('href="https://investors.ao-inc.com/node/16751"', section)

    def test_event_radar_does_not_depend_on_legacy_panorama_file(self) -> None:
        render(self.root)
        section = render_intelligence_section(
            self.root / "calls" / "out" / "missing-panorama.csv",
            event_path=self.root / "calls" / "out" / "event-intelligence.json",
        )
        self.assertIn("本期公司事件", section)
        self.assertIn("数据版本：", section)

    def test_tracking_tiers_are_counted_without_promoting_candidates_to_radar(self) -> None:
        baseline = derive_event_projection(load_event_facts(self.root))["coverage_summary"]
        self.append("company_candidates.csv", {
            "candidate_id": "CAND_TEST",
            "entity_name": "Test Photonics",
            "entity_type": "company",
            "suggested_role": "upstream_enabler",
            "suggested_tier": "quarterly",
            "priority": "P1",
            "capability_scope": "M1/C1",
            "inclusion_reason": "test fixture",
            "source_ref": "https://example.com/investors",
            "verification_status": "source_verified",
            "reviewed_at": "2026-08-13",
        })
        projection = derive_event_projection(load_event_facts(self.root))
        coverage = projection["coverage_summary"]
        self.assertEqual(coverage["quarterly_company_count"], baseline["quarterly_company_count"])
        self.assertEqual(coverage["four_slot_complete_count"], baseline["four_slot_complete_count"])
        self.assertEqual(
            coverage["four_available_slot_complete_count"],
            baseline["four_available_slot_complete_count"],
        )
        self.assertEqual(coverage["active_watch_entity_count"], baseline["active_watch_entity_count"])
        self.assertEqual(
            coverage["candidate_status_counts"]["source_verified"],
            baseline["candidate_status_counts"]["source_verified"] + 1,
        )
        self.assertIn(
            "CAND_TEST",
            {row["candidate_id"] for row in projection["company_candidates"]},
        )
        self.assertNotIn(
            "CAND_TEST",
            {row["primary_subject_id"] for row in projection["radar_events"]},
        )

    def test_candidate_promotion_and_review_require_traceable_state(self) -> None:
        fixture = {
            "candidate_id": "CAND_TEST",
            "entity_name": "Test Photonics",
            "entity_type": "company",
            "suggested_role": "upstream_enabler",
            "suggested_tier": "watch",
            "priority": "P2",
            "capability_scope": "C4",
            "inclusion_reason": "test fixture",
            "verification_status": "source_verified",
        }
        self.append("company_candidates.csv", fixture)
        with self.assertRaisesRegex(EventLedgerError, "needs source_ref and reviewed_at"):
            load_event_facts(self.root)
        self.mutate("company_candidates.csv", "CAND_TEST", {
            "verification_status": "promoted",
            "source_ref": "https://example.com/source",
            "reviewed_at": "2026-08-13",
            "promoted_entity_id": "UNKNOWN",
        })
        with self.assertRaisesRegex(EventLedgerError, "known promoted_entity_id"):
            load_event_facts(self.root)

    def test_candidate_promotion_requires_two_formal_period_reviews_with_signal(self) -> None:
        baseline_review_count = len(
            load_event_facts(self.root)["company_tier_reviews"]
        )
        self.append("company_candidates.csv", {
            "candidate_id": "CAND_TEST",
            "entity_name": "Test Photonics",
            "entity_type": "company",
            "suggested_role": "upstream_enabler",
            "suggested_tier": "quarterly",
            "priority": "P2",
            "capability_scope": "C4",
            "inclusion_reason": "test fixture",
            "source_ref": "https://example.com/investors",
            "verification_status": "promotion_ready",
            "reviewed_at": "2026-08-13",
        })
        with self.assertRaisesRegex(EventLedgerError, "needs two formal tier reviews"):
            load_event_facts(self.root)
        review = {
            "candidate_id": "CAND_TEST",
            "published_date": "2026-08-01",
            "source_ref": "https://example.com/results-q2",
            "material_type": "regulatory_filing",
            "signal_class": "no_relevant_signal",
            "signal_summary": "reviewed full filing; no optical signal",
            "reviewed_at": "2026-08-13",
        }
        self.append("company_tier_reviews.csv", {
            **review, "review_id": "TR_TEST_Q2", "period_label": "2026Q2",
        })
        with self.assertRaisesRegex(EventLedgerError, "needs two formal tier reviews"):
            load_event_facts(self.root)
        self.append("company_tier_reviews.csv", {
            **review,
            "review_id": "TR_TEST_Q1",
            "period_label": "2026Q1",
            "published_date": "2026-05-01",
            "source_ref": "https://example.com/results-q1",
        })
        with self.assertRaisesRegex(EventLedgerError, "lacks optical or adjacent signal"):
            load_event_facts(self.root)
        self.mutate("company_tier_reviews.csv", "TR_TEST_Q1", {
            "signal_class": "direct_optical",
            "signal_summary": "formal filing contains an optical product signal",
        })
        facts = load_event_facts(self.root)
        self.assertEqual(
            len(facts["company_tier_reviews"]), baseline_review_count + 2
        )
        self.mutate("company_tier_reviews.csv", "TR_TEST_Q1", {
            "material_type": "official_technical_blog",
        })
        with self.assertRaisesRegex(EventLedgerError, "requires formal disclosure material"):
            load_event_facts(self.root)

    def test_watch_promotion_does_not_require_quarterly_tier_reviews(self) -> None:
        self.append("watch_entities.csv", {
            "entity_id": "WATCH_TEST",
            "entity_name": "Private Photonics",
            "entity_type": "company",
            "inclusion_reason": "event-driven private company",
            "monitoring_status": "active",
            "source_ref": "https://example.com/official-product",
        })
        self.append("company_candidates.csv", {
            "candidate_id": "CAND_TEST",
            "entity_name": "Private Photonics",
            "entity_type": "company",
            "suggested_role": "upstream_enabler",
            "suggested_tier": "watch",
            "priority": "P3",
            "capability_scope": "D12",
            "inclusion_reason": "event-driven private company",
            "source_ref": "https://example.com/official-product",
            "verification_status": "promoted",
            "promoted_entity_id": "WATCH_TEST",
            "reviewed_at": "2026-08-13",
        })
        facts = load_event_facts(self.root)
        self.assertIn("WATCH_TEST", facts["entities"])

    def test_entity_relationships_are_time_aware_and_closed_over_entities(self) -> None:
        fixture = {
            "relationship_id": "REL_TEST",
            "subject_entity_id": "WATCH_DUST",
            "object_entity_id": "CRDO",
            "relationship_type": "acquired_by",
            "effective_from": "2026-05-28",
            "source_ref": "https://example.com/acquisition",
            "review_status": "reviewed",
        }
        self.append("entity_relationships.csv", fixture)
        projection = derive_event_projection(load_event_facts(self.root))
        self.assertEqual(
            next(
                row for row in projection["entity_relationships"]
                if row["relationship_id"] == "REL_TEST"
            )["relationship_id"],
            "REL_TEST",
        )
        self.mutate("entity_relationships.csv", "REL_TEST", {
            "object_entity_id": "WATCH_DUST",
        })
        with self.assertRaisesRegex(EventLedgerError, "self relationship"):
            load_event_facts(self.root)
        self.mutate("entity_relationships.csv", "REL_TEST", {
            "object_entity_id": "UNKNOWN",
        })
        with self.assertRaisesRegex(EventLedgerError, "unknown relationship endpoint"):
            load_event_facts(self.root)

    def test_entity_relationship_date_range_and_review_source_are_validated(self) -> None:
        self.append("entity_relationships.csv", {
            "relationship_id": "REL_TEST",
            "subject_entity_id": "WATCH_DUST",
            "object_entity_id": "CRDO",
            "relationship_type": "acquired_by",
            "effective_from": "2026-06-01",
            "effective_to": "2026-05-01",
            "review_status": "candidate",
        })
        with self.assertRaisesRegex(EventLedgerError, "effective_from is after effective_to"):
            load_event_facts(self.root)
        self.mutate("entity_relationships.csv", "REL_TEST", {
            "effective_to": "",
            "review_status": "reviewed",
        })
        with self.assertRaisesRegex(EventLedgerError, "reviewed relationship needs source_ref"):
            load_event_facts(self.root)


if __name__ == "__main__":
    unittest.main()
