from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from news_daily import http
from news_daily.adapters.cninfo import CninfoAnnouncementsAdapter
from news_daily.adapters.fixture import FixtureAdapter
from news_daily.adapters.rss_atom import RSSAtomAdapter
from news_daily.adapters.sec_submissions import SECSubmissionsAdapter
from news_daily.config import ConfigurationError, adapters_for, load_config
from news_daily.models import RunRequest, Scope
from news_daily.runner import run


class LiveConfigTests(unittest.TestCase):
    @staticmethod
    def write_config(directory: Path, body: str) -> Path:
        path = directory / "config.toml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_composes_all_kinds_with_injected_transports_and_deterministic_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            config_path = self.write_config(directory, """
[adapters.z-fixture]
kind = "fixture"
scope = "domestic"

[adapters.a-cninfo]
kind = "cninfo"
scope = "domestic"
column = "sse"
page_size = 5
max_pages = 2

[adapters.z-rss]
kind = "rss_atom"
scope = "overseas"
feed_url = "https://example.test/feed.xml"
publisher = "Example Publisher"

[adapters.a-sec]
kind = "sec_submissions"
scope = "overseas"
ciks = ["320193"]
""")
            config = load_config(config_path)
            post_form_json = Mock()
            get_text = Mock()
            get_json = Mock()
            with patch.object(http, "post_form_json", post_form_json), patch.object(
                http, "get_text", get_text
            ), patch.object(http, "get_json", get_json):
                adapters = adapters_for(config, (Scope.DOMESTIC, Scope.OVERSEAS), directory)

            self.assertEqual(
                [(adapter.scope.value, adapter.source_id) for adapter in adapters],
                [
                    ("domestic", "a-cninfo"),
                    ("domestic", "z-fixture"),
                    ("overseas", "a-sec"),
                    ("overseas", "z-rss"),
                ],
            )
            self.assertIsInstance(adapters[0], CninfoAnnouncementsAdapter)
            self.assertIs(adapters[0]._client, post_form_json)  # type: ignore[attr-defined]
            self.assertIsInstance(adapters[1], FixtureAdapter)
            self.assertIsInstance(adapters[2], SECSubmissionsAdapter)
            self.assertIs(adapters[2].get_json, get_json)  # type: ignore[attr-defined]
            self.assertIsInstance(adapters[3], RSSAtomAdapter)
            self.assertIs(adapters[3].get_text, get_text)  # type: ignore[attr-defined]

    def test_disabled_specs_are_skipped_even_when_their_kind_is_not_usable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_config(Path(temp), """
[adapters.disabled]
enabled = false
kind = "not-a-kind"
scope = "not-a-scope"
""")
            adapters = adapters_for(load_config(path), (Scope.DOMESTIC,), None)
            self.assertEqual(adapters, ())

    def test_invalid_options_and_unknown_kind_raise_configuration_error(self) -> None:
        cases = (
            """
[adapters.bad]
kind = "unknown"
scope = "domestic"
""",
            """
[adapters.bad]
kind = "cninfo"
scope = "domestic"
page_size = 0
""",
            """
[adapters.bad]
kind = "cninfo"
scope = "domestic"
max_pages = -1
""",
            """
[adapters.bad]
kind = "rss_atom"
scope = "overseas"
publisher = "Publisher"
""",
            """
[adapters.bad]
kind = "sec_submissions"
scope = "overseas"
ciks = "320193"
""",
            """
[adapters.bad]
kind = "fixture"
scope = "sideways"
""",
        )
        for body in cases:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as temp:
                path = self.write_config(Path(temp), body)
                with self.assertRaises(ConfigurationError):
                    adapters_for(load_config(path), (Scope.DOMESTIC, Scope.OVERSEAS), None)

    def test_runner_executes_live_adapters_using_only_mocked_transports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            config_path = self.write_config(directory, """
[adapters.cninfo]
kind = "cninfo"
scope = "domestic"
column = "szse"
page_size = 10
max_pages = 1

[adapters.rss]
kind = "rss_atom"
scope = "overseas"
feed_url = "https://example.test/feed.xml"
publisher = "Example Publisher"

[adapters.sec]
kind = "sec_submissions"
scope = "overseas"
ciks = ["320193"]
""")
            post_form_json = Mock(return_value={"announcements": []})
            get_text = Mock(return_value=b"<rss><channel /></rss>")
            get_json = Mock(
                return_value={
                    "name": "Example Corp",
                    "filings": {
                        "recent": {
                            field: []
                            for field in (
                                "form",
                                "filingDate",
                                "accessionNumber",
                                "primaryDocument",
                                "reportDate",
                            )
                        }
                    },
                }
            )
            request = RunRequest(
                scopes=(Scope.DOMESTIC, Scope.OVERSEAS),
                as_of_date="2026-09-02",
                config_path=config_path,
                output_root=directory / "output",
            )
            with patch.object(http, "post_form_json", post_form_json), patch.object(
                http, "get_text", get_text
            ), patch.object(http, "get_json", get_json):
                result = run(request)

            self.assertEqual(result.status, "success")
            self.assertEqual(result.counts_by_scope, {"domestic": 0, "overseas": 0})
            self.assertEqual(post_form_json.call_count, 1)
            self.assertEqual(get_text.call_count, 1)
            self.assertEqual(get_json.call_count, 1)


if __name__ == "__main__":
    unittest.main()
