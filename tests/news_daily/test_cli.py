from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class NewsDailyCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "news_daily", *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def payload(result: subprocess.CompletedProcess[str]) -> dict:
        return json.loads(result.stdout)

    @staticmethod
    def write_jsonl(path: Path, records: list[dict]) -> None:
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    @staticmethod
    def write_config(path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")

    def fixture_dir(self, directory: Path) -> None:
        self.write_jsonl(
            directory / "domestic.jsonl",
            [
                {
                    "publisher": "Domestic Wire",
                    "title": "Domestic headline",
                    "url": "https://example.test/domestic/1/",
                    "published_time": "2026-09-02T08:00:00Z",
                    "snippet": "fixture",
                }
            ],
        )
        self.write_jsonl(
            directory / "overseas.jsonl",
            [
                {
                    "publisher": "Overseas Wire",
                    "title": "Overseas headline",
                    "url": "https://example.test/overseas/1",
                    "published_time": "2026-09-02T09:00:00Z",
                    "language": "en",
                }
            ],
        )

    def test_all_scope_fixture_run_persists_candidate_raw_manifest_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            fixtures = directory / "fixtures"
            fixtures.mkdir()
            self.fixture_dir(fixtures)
            output = directory / "output"
            result = self.run_cli(
                "run", "--scope", "all", "--date", "2026-09-02",
                "--config", "news_daily/config.toml", "--output-root", str(output),
                "--fixture-dir", str(fixtures),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = self.payload(result)
            self.assertEqual(payload["counts_by_scope"], {"domestic": 1, "overseas": 1})
            for path in payload["output_paths"]:
                self.assertTrue(Path(path).exists())
            domestic = output / "2026-09-02" / "domestic" / "latest.json"
            run_dir = output / "2026-09-02" / "domestic" / "runs" / json.loads(domestic.read_text())["run_id"]
            self.assertTrue((run_dir / "raw/envelopes.jsonl").exists())
            candidate = json.loads((run_dir / "candidates.jsonl").read_text().splitlines()[0])
            self.assertEqual(candidate["record_type"], "candidate")
            self.assertEqual(json.loads((run_dir / "manifest.json").read_text())["semantic_state"], "candidate_only")

    def test_identical_rerun_has_identical_candidate_and_report_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            fixtures = directory / "fixtures"
            fixtures.mkdir()
            self.fixture_dir(fixtures)
            output = directory / "output"
            args = (
                "run", "--scope", "domestic", "--date", "2026-09-02",
                "--config", "news_daily/config.toml", "--output-root", str(output),
                "--fixture-dir", str(fixtures),
            )
            first = self.run_cli(*args)
            second = self.run_cli(*args)
            self.assertEqual(first.returncode, 0)
            self.assertEqual(second.returncode, 0)
            first_dir = Path(self.payload(first)["output_paths"][0])
            second_dir = Path(self.payload(second)["output_paths"][0])
            self.assertEqual((first_dir / "candidates.jsonl").read_bytes(), (second_dir / "candidates.jsonl").read_bytes())
            self.assertEqual((first_dir / "report.txt").read_bytes(), (second_dir / "report.txt").read_bytes())

    def test_duplicate_items_collapse_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            fixtures = directory / "fixtures"
            fixtures.mkdir()
            duplicate = {
                "title": "Same story", "url": "https://EXAMPLE.test/story/",
                "published_time": "2026-09-02T08:00:00Z", "content": "same",
            }
            self.write_jsonl(fixtures / "domestic.jsonl", [duplicate, dict(duplicate)])
            output = directory / "output"
            result = self.run_cli(
                "run", "--scope", "domestic", "--date", "2026-09-02",
                "--config", "news_daily/config.toml", "--output-root", str(output),
                "--fixture-dir", str(fixtures),
            )
            self.assertEqual(result.returncode, 0)
            run_dir = Path(self.payload(result)["output_paths"][0])
            self.assertEqual(len((run_dir / "candidates.jsonl").read_text().splitlines()), 1)
            self.assertEqual(len((run_dir / "raw/envelopes.jsonl").read_text().splitlines()), 2)

    def test_one_adapter_failure_is_partial_and_other_source_survives(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            fixtures = directory / "fixtures"
            fixtures.mkdir()
            self.write_jsonl(fixtures / "good.jsonl", [{"title": "Good", "url": "https://example.test/good"}])
            config = directory / "config.toml"
            self.write_config(config, """
[output]
root = "ignored"
[adapters.good]
kind = "fixture"
scope = "domestic"
file = "good.jsonl"
[adapters.bad]
kind = "fixture"
scope = "domestic"
file = "missing.jsonl"
""")
            output = directory / "output"
            result = self.run_cli(
                "run", "--scope", "domestic", "--date", "2026-09-02", "--config", str(config),
                "--output-root", str(output), "--fixture-dir", str(fixtures),
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(self.payload(result)["status"], "partial")
            self.assertEqual(self.payload(result)["counts_by_source"], {"good": 1})

    def test_dry_run_creates_no_output_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            fixtures = directory / "fixtures"
            fixtures.mkdir()
            self.fixture_dir(fixtures)
            output = directory / "output"
            result = self.run_cli(
                "run", "--scope", "all", "--date", "2026-09-02", "--config", "news_daily/config.toml",
                "--output-root", str(output), "--fixture-dir", str(fixtures), "--dry-run",
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(self.payload(result)["status"], "dry_run")
            self.assertFalse(output.exists())

    def test_concurrent_run_returns_already_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            fixtures = directory / "fixtures"
            fixtures.mkdir()
            self.write_jsonl(fixtures / "domestic.jsonl", [{"title": "Slow", "url": "https://example.test/slow"}])
            config = directory / "config.toml"
            self.write_config(config, """
[adapters.slow]
kind = "fixture"
scope = "domestic"
delay_seconds = 0.6
""")
            output = directory / "output"
            command = [sys.executable, "-m", "news_daily", "run", "--scope", "domestic", "--date", "2026-09-02", "--config", str(config), "--output-root", str(output), "--fixture-dir", str(fixtures)]
            first = subprocess.Popen(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            lock = output / ".locks/2026-09-02-domestic.lock"
            for _ in range(50):
                if lock.exists():
                    break
                time.sleep(0.02)
            second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            stdout, stderr = first.communicate(timeout=5)
            self.assertEqual(second.returncode, 3, second.stdout + second.stderr)
            self.assertEqual(first.returncode, 0, stdout + stderr)

    def test_atomic_publish_has_complete_final_output_and_no_staging_remnant(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            fixtures = directory / "fixtures"
            fixtures.mkdir()
            self.fixture_dir(fixtures)
            output = directory / "output"
            result = self.run_cli(
                "run", "--scope", "domestic", "--date", "2026-09-02", "--config", "news_daily/config.toml",
                "--output-root", str(output), "--fixture-dir", str(fixtures),
            )
            self.assertEqual(result.returncode, 0)
            run_dir = Path(self.payload(result)["output_paths"][0])
            for relative in ("raw/envelopes.jsonl", "candidates.jsonl", "manifest.json", "report.txt"):
                self.assertTrue((run_dir / relative).is_file())
            self.assertFalse((output / ".staging").exists())

    def test_forbidden_output_roots_are_rejected(self) -> None:
        forbidden = [ROOT, ROOT / "tmp/daily", ROOT / "corpus", ROOT / "calls", ROOT / "out"]
        for path in forbidden:
            with self.subTest(path=path):
                result = self.run_cli(
                    "run", "--scope", "domestic", "--date", "2026-09-02", "--config", "news_daily/config.toml",
                    "--output-root", str(path), "--dry-run",
                )
                self.assertEqual(result.returncode, 4)

    def test_symlink_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            target = directory / "outside"
            target.mkdir()
            link = directory / "link"
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            result = self.run_cli(
                "run", "--scope", "domestic", "--date", "2026-09-02", "--config", "news_daily/config.toml",
                "--output-root", str(link), "--dry-run",
            )
            self.assertEqual(result.returncode, 4)

    def test_status_reports_present_missing_and_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            output = directory / "output"
            missing = self.run_cli("status", "--date", "2026-09-02", "--output-root", str(output))
            self.assertEqual(self.payload(missing)["status"], "missing")
            fixtures = directory / "fixtures"
            fixtures.mkdir()
            self.fixture_dir(fixtures)
            present = self.run_cli(
                "run", "--scope", "domestic", "--date", "2026-09-02", "--config", "news_daily/config.toml",
                "--output-root", str(output), "--fixture-dir", str(fixtures),
            )
            self.assertEqual(present.returncode, 0)
            self.assertEqual(self.payload(self.run_cli("status", "--date", "2026-09-02", "--output-root", str(output)))["status"], "present")
            config = directory / "partial.toml"
            self.write_config(config, """
[adapters.good]
kind = "fixture"
scope = "domestic"
file = "domestic.jsonl"
[adapters.bad]
kind = "fixture"
scope = "domestic"
file = "not-there.jsonl"
""")
            partial = self.run_cli(
                "run", "--scope", "domestic", "--date", "2026-09-03", "--config", str(config),
                "--output-root", str(output), "--fixture-dir", str(fixtures),
            )
            self.assertEqual(partial.returncode, 2)
            self.assertEqual(self.payload(self.run_cli("status", "--date", "2026-09-03", "--output-root", str(output)))["status"], "partial")


if __name__ == "__main__":
    unittest.main()
