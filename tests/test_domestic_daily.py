import json
import tempfile
import unittest
from pathlib import Path

from domestic_daily import DailyMirror, FixtureClient


ROOT = Path(__file__).parents[1]


class MirrorTests(unittest.TestCase):
    def run_mirror(self, client, date="2026-09-01"):
        state = Path(tempfile.mkdtemp())
        return state, DailyMirror(ROOT, state, client).run(date)

    def test_watched_union_and_protected_source(self):
        client = FixtureClient(qa={}, announcements={}, ir={"relation": [], "fulltext": []})
        state, result = self.run_mirror(client)
        self.assertIn("300308", result["manifest"]["watched_codes"])
        self.assertIn("600114", result["manifest"]["watched_codes"])
        self.assertTrue((state / "daily/2026-09-01.txt").exists())

    def test_qa_union_does_not_shrink_and_fixture_filters(self):
        source = ROOT / "corpus/qa/300308/qa.jsonl"
        old = json.loads(source.read_text().splitlines()[0])
        client = FixtureClient(qa={"300308": [dict(old, answer="new metadata"), {**old, "index_id": "fixture-new"}]}, announcements={})
        state, result = self.run_mirror(client)
        rows = [json.loads(x) for x in (state / "qa/300308/qa.jsonl").read_text().splitlines()]
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(result["manifest"]["digest"]["qa_new"][0][1], 1)

    def test_announcement_restart_and_atomic_repeat(self):
        client = FixtureClient(
            ir={"relation": [{"secCode": "300308", "secName": "中际旭创", "announcementTitle": "投资者关系活动记录表", "adjunctUrl": "x.pdf", "text": "自研硅光芯片"}], "fulltext": []},
            downloads={"x.pdf": b"%PDF-fixture"},
            announcements={"300308": [{"secCode": "300308", "announcementTitle": "重大合同公告", "announcementTime": "2026-09-01", "adjunctUrl": "a.pdf"}, {"secCode": "300308", "announcementTitle": "普通公告", "announcementTime": "2026-09-01", "adjunctUrl": "b.pdf"}]}, qa={})
        state, first = self.run_mirror(client)
        daily = (state / "daily/2026-09-01.txt").read_bytes()
        self.assertIn("公告流(关注公司) 1 条", daily.decode())
        self.assertIn("机械匹配，不构成判定", daily.decode())
        second = DailyMirror(ROOT, state, client).run("2026-09-01")
        self.assertEqual(daily, (state / "daily/2026-09-01.txt").read_bytes())
        self.assertEqual(first["manifest"]["watched_codes"], second["manifest"]["watched_codes"])

    def test_lock_rejects_concurrent_run(self):
        import fcntl
        state = Path(tempfile.mkdtemp())
        lock = (state / ".lock"); lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open("w") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(RuntimeError):
                DailyMirror(ROOT, state, FixtureClient()).run("2026-09-01")


if __name__ == "__main__":
    unittest.main()
