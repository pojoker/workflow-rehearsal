from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from daily_intelligence import combine_daily_reports


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CombinedDailyIntelligenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.domestic = self.root / "domestic"
        self.overseas = self.root / "overseas"
        self.output = self.root / "combined"
        (self.domestic / "daily").mkdir(parents=True)
        (self.overseas / "daily").mkdir(parents=True)
        (self.overseas / "staging" / "2026-09-02").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_complete_inputs(self) -> list[Path]:
        domestic_report = self.domestic / "daily" / "2026-09-02.txt"
        domestic_manifest = self.domestic / "manifest.json"
        overseas_report = self.overseas / "daily" / "2026-09-02.txt"
        overseas_summary = self.overseas / "staging" / "2026-09-02" / "run-summary.json"
        domestic_report.write_text("# 国内日报\n\n## 明细\n- 国内事件\n", encoding="utf-8")
        domestic_manifest.write_text(
            json.dumps(
                {
                    "date": "2026-09-02",
                    "watched_codes": 102,
                    "digest": {
                        "ir_new": ["ir"],
                        "qa_new": ["qa1", "qa2"],
                        "ann": [],
                        "q_delta_new": ["queue"],
                        "q_delta_gone": [],
                    },
                    "restart_hits": 0,
                    "outlier_hits": 0,
                    "logs": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        overseas_report.write_text("# 海外日报\n\n## 事件\n- LITE first shipment\n", encoding="utf-8")
        overseas_summary.write_text(
            json.dumps(
                {
                    "run_date": "2026-09-02",
                    "monitored_entity_count": 82,
                    "configured_entity_count": 7,
                    "missing_endpoint_count": 75,
                    "endpoint_failed": 1,
                    "disclosure_candidates": 9,
                    "claim_candidates": 10,
                    "event_candidates": 8,
                    "evidence_candidates": 9,
                    "corroboration_suggestions": 1,
                    "promoted": 0,
                    "failure_types": {"missing_endpoint": 75, "fetch_failure": 1},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return [domestic_report, domestic_manifest, overseas_report, overseas_summary]

    def test_combines_both_reports_and_keeps_inputs_read_only(self) -> None:
        inputs = self._write_complete_inputs()
        before = {path: _sha256(path) for path in inputs}

        result = combine_daily_reports(
            run_date="2026-09-02",
            domestic_state_root=self.domestic,
            overseas_state_root=self.overseas,
            output_root=self.output,
        )

        self.assertEqual(result["assembly_status"], "complete")
        report = Path(result["markdown_path"]).read_text(encoding="utf-8")
        self.assertIn("国内与海外每日情报总览 2026-09-02", report)
        self.assertIn("投关表 +1、互动问答 +2", report)
        self.assertIn("披露 9、主张 10、事件 8、证据 9", report)
        self.assertIn("已配置 7/82 个实体", report)
        self.assertIn("正式账本写入 0 条", report)
        self.assertIn("国内事件", report)
        self.assertIn("LITE first shipment", report)
        self.assertEqual(before, {path: _sha256(path) for path in inputs})

    def test_missing_source_still_writes_an_explicit_partial_report(self) -> None:
        domestic_report = self.domestic / "daily" / "2026-09-02.txt"
        domestic_report.write_text("# 国内日报\n", encoding="utf-8")
        (self.domestic / "manifest.json").write_text(
            json.dumps({"date": "2026-09-02", "digest": {}}), encoding="utf-8"
        )

        result = combine_daily_reports(
            run_date="2026-09-02",
            domestic_state_root=self.domestic,
            overseas_state_root=self.overseas,
            output_root=self.output,
        )

        self.assertEqual(result["assembly_status"], "partial")
        report = Path(result["markdown_path"]).read_text(encoding="utf-8")
        self.assertIn("汇总状态：partial", report)
        self.assertIn("海外输入异常：missing:", report)
        payload = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
        self.assertFalse(payload["overseas"]["available"])

    def test_rejects_invalid_date_and_overlapping_output(self) -> None:
        self._write_complete_inputs()
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            combine_daily_reports(
                run_date="09/02/2026",
                domestic_state_root=self.domestic,
                overseas_state_root=self.overseas,
                output_root=self.output,
            )
        with self.assertRaisesRegex(ValueError, "disjoint"):
            combine_daily_reports(
                run_date="2026-09-02",
                domestic_state_root=self.domestic,
                overseas_state_root=self.overseas,
                output_root=self.domestic / "combined",
            )


if __name__ == "__main__":
    unittest.main()
