from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from news_daily.storage import IsolationError, RunLock, resolve_output_root


ROOT = Path(__file__).resolve().parents[2]


class StorageSafetyTests(unittest.TestCase):
    def test_default_subtree_is_allowed(self) -> None:
        self.assertEqual(
            resolve_output_root(ROOT / "tmp/news-daily-v2" / "nested"),
            ROOT / "tmp/news-daily-v2/nested",
        )

    def test_arbitrary_in_repo_outputs_are_rejected(self) -> None:
        for path in (
            ROOT,
            ROOT / "docs/news-output",
            ROOT / "tmp/other-output",
            ROOT / "corpus/news-output",
            ROOT / "calls/news-output",
            ROOT / "out/news-output",
        ):
            with self.subTest(path=path), self.assertRaises(IsolationError):
                resolve_output_root(path)

    def test_external_temp_output_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "news-output"
            self.assertEqual(resolve_output_root(output), output.resolve())

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
            with self.assertRaises(IsolationError):
                resolve_output_root(link / "nested")

    def test_stale_dead_lock_is_recovered_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            locks = root / ".locks"
            locks.mkdir()
            lock = locks / "2026-09-02-domestic.lock"
            lock.write_text(json.dumps({"pid": 424242, "scope": "domestic"}), encoding="utf-8")
            with patch("news_daily.storage.os.kill", side_effect=ProcessLookupError):
                with RunLock(root, "2026-09-02", ("domestic",)):
                    self.assertEqual(json.loads(lock.read_text())["pid"], os.getpid())

    def test_malformed_lock_remains_already_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            locks = root / ".locks"
            locks.mkdir()
            lock = locks / "2026-09-02-domestic.lock"
            lock.write_text("not-json", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "already_running"):
                with RunLock(root, "2026-09-02", ("domestic",)):
                    pass
            self.assertTrue(lock.exists())

    def test_live_lock_remains_already_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            locks = root / ".locks"
            locks.mkdir()
            lock = locks / "2026-09-02-domestic.lock"
            lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "already_running"):
                with RunLock(root, "2026-09-02", ("domestic",)):
                    pass
            self.assertTrue(lock.exists())


if __name__ == "__main__":
    unittest.main()
