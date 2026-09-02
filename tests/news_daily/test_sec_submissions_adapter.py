from __future__ import annotations

import unittest

from news_daily.adapters.sec_submissions import SECSubmissionsAdapter
from news_daily.models import FetchContext, Scope


class SECSubmissionsAdapterTests(unittest.TestCase):
    def context(self, date: str = "2026-09-02") -> FetchContext:
        return FetchContext(date, "2026-09-03T00:00:00Z", None, 7.25, "research-agent/2.0")

    def test_parallel_arrays_filter_and_construct_archive_url(self) -> None:
        calls: list[tuple[str, dict[str, str], float]] = []
        payload = {
            "name": "Example Corp",
            "filings": {
                "recent": {
                    "form": ["10-K", "8-K", "10-Q", "8-K"],
                    "filingDate": ["2026-09-02", "2026-09-01", "2026-09-02", "2026-09-02"],
                    "accessionNumber": ["0000320193-26-000001", "0000320193-26-000002", None, "bad"],
                    "primaryDocument": ["example-10k.htm", "example-8k.htm", "example-10q.htm", "example-8k.htm"],
                    "reportDate": ["2026-06-30", "2026-09-01", "2026-06-30", "2026-09-02"],
                }
            },
        }

        def get_json(url: str, headers: dict[str, str], timeout: float) -> dict:
            calls.append((url, headers, timeout))
            return payload

        adapter = SECSubmissionsAdapter("sec-source", "320193", get_json)
        items = list(adapter.fetch(self.context()))
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.scope, Scope.OVERSEAS)
        self.assertEqual(item.title, "10-K filing: Example Corp")
        self.assertEqual(item.publisher, "Example Corp")
        self.assertEqual(item.snippet, "form=10-K; company=Example Corp; reportDate=2026-06-30")
        self.assertEqual(item.url, "https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/example-10k.htm")
        self.assertEqual(item.published_time, "2026-09-02T00:00:00Z")
        self.assertEqual(calls, [("https://data.sec.gov/submissions/CIK0000320193.json", {"User-Agent": "research-agent/2.0"}, 7.25)])

    def test_primary_document_subpath_preserves_separators_and_encodes_segments(self) -> None:
        payload = {
            "name": "Example Corp",
            "filings": {"recent": {
                "form": ["4"],
                "filingDate": ["2026-09-02"],
                "accessionNumber": ["0000320193-26-000003"],
                "primaryDocument": ["xslF345X06/form 4.xml"],
                "reportDate": [""],
            }},
        }
        adapter = SECSubmissionsAdapter("sec", "320193", lambda *_: payload)
        item = list(adapter.fetch(self.context()))[0]
        self.assertEqual(item.url, "https://www.sec.gov/Archives/edgar/data/320193/000032019326000003/xslF345X06/form%204.xml")

    def test_primary_document_traversal_and_unsafe_values_are_rejected_or_skipped(self) -> None:
        invalid_documents = ("/absolute.xml", "../parent.xml", "x/../parent.xml", "x//empty.xml", "x/./dot.xml", "x\\backslash.xml", "x.xml?query", "x.xml#fragment", None)
        for document in invalid_documents:
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    SECSubmissionsAdapter._archive_url("0000320193", "0000320193-26-000003", document)  # type: ignore[arg-type]
        payload = {
            "name": "Example Corp",
            "filings": {"recent": {
                "form": ["4", "4"],
                "filingDate": ["2026-09-02", "2026-09-02"],
                "accessionNumber": ["0000320193-26-000004", "0000320193-26-000005"],
                "primaryDocument": ["xslF345X06/form4.xml", "../parent.xml"],
                "reportDate": ["", ""],
            }},
        }
        items = list(SECSubmissionsAdapter("sec", "320193", lambda *_: payload).fetch(self.context()))
        self.assertEqual(len(items), 1)
        self.assertIn("/xslF345X06/form4.xml", items[0].url)

    def test_empty_report_date_keeps_valid_filing_and_omits_snippet_field(self) -> None:
        payload = {
            "name": "Example Corp",
            "filings": {"recent": {
                "form": ["8-K"],
                "filingDate": ["2026-09-02"],
                "accessionNumber": ["0000320193-26-000006"],
                "primaryDocument": ["example.xml"],
                "reportDate": [""],
            }},
        }
        item = list(SECSubmissionsAdapter("sec", "320193", lambda *_: payload).fetch(self.context()))[0]
        self.assertEqual(item.snippet, "form=8-K; company=Example Corp")
        self.assertEqual(len(item.content_hash), 64)

    def test_ciks_are_normalized_and_duplicate_ciks_are_fetched_once(self) -> None:
        calls: list[str] = []
        payload = {"name": "Corp", "filings": {"recent": {field: [] for field in ("form", "filingDate", "accessionNumber", "primaryDocument", "reportDate")}}}

        def get_json(url: str, headers: dict[str, str], timeout: float) -> dict:
            calls.append(url)
            return payload

        adapter = SECSubmissionsAdapter("sec", ["  320193", "0000320193", 789], get_json)
        self.assertEqual(adapter.ciks, ("0000320193", "0000000789"))
        list(adapter.fetch(self.context()))
        self.assertEqual(calls, ["https://data.sec.gov/submissions/CIK0000320193.json", "https://data.sec.gov/submissions/CIK0000000789.json"])

    def test_malformed_rows_are_skipped_but_top_level_failures_raise(self) -> None:
        malformed_row = {
            "name": "Corp",
            "filings": {"recent": {
                "form": ["8-K"], "filingDate": ["2026-09-02"],
                "accessionNumber": ["bad"], "primaryDocument": ["x.htm"], "reportDate": ["2026-09-02"],
            }},
        }
        adapter = SECSubmissionsAdapter("sec", "1", lambda *_: malformed_row)
        self.assertEqual(list(adapter.fetch(self.context())), [])
        for payload in ({}, {"filings": {}}, {"filings": {"recent": {"form": []}}}, []):
            with self.subTest(payload=payload):
                failing = SECSubmissionsAdapter("sec", "1", lambda *_payload, payload=payload: payload)
                with self.assertRaisesRegex(ValueError, "CIK 0000000001"):
                    list(failing.fetch(self.context()))

    def test_invalid_cik_and_injected_request_failure_are_clear(self) -> None:
        for cik in ("", "abc", "12345678901", True):
            with self.subTest(cik=cik):
                with self.assertRaises(ValueError):
                    SECSubmissionsAdapter("sec", cik, lambda *_: {})
        adapter = SECSubmissionsAdapter("sec", "1", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
        with self.assertRaisesRegex(ValueError, "request failed for CIK 0000000001"):
            list(adapter.fetch(self.context()))


if __name__ == "__main__":
    unittest.main()
