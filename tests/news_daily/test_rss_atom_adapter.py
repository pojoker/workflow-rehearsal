from __future__ import annotations

import unittest

from news_daily.adapters.rss_atom import RSSAtomAdapter
from news_daily.models import FetchContext, Scope


class RSSAtomAdapterTests(unittest.TestCase):
    def context(self, date: str = "2026-09-02") -> FetchContext:
        return FetchContext(date, "2026-09-03T00:00:00Z", None, 4.5, "test-agent/1.0")

    def test_rss_filters_date_normalizes_fields_and_passes_request_options(self) -> None:
        calls: list[tuple[str, dict[str, str], float]] = []
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item><title>  A   headline </title><link>/story#fragment</link>
            <pubDate>Wed, 02 Sep 2026 10:30:00 +0200</pubDate>
            <description> A useful summary. </description></item>
          <item><title>Old</title><link>https://example.test/old</link>
            <pubDate>Tue, 01 Sep 2026 23:59:00Z</pubDate></item>
        </channel></rss>"""

        def get_text(url: str, headers: dict[str, str], timeout: float) -> str:
            calls.append((url, headers, timeout))
            return xml

        adapter = RSSAtomAdapter("rss-source", "https://feed.test/news.xml", "Publisher", get_text)
        items = list(adapter.fetch(self.context()))
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.scope, Scope.OVERSEAS)
        self.assertEqual(item.title, "A headline")
        self.assertEqual(item.url, "https://feed.test/story")
        self.assertEqual(item.published_time, "2026-09-02T08:30:00Z")
        self.assertEqual(item.snippet, "A useful summary.")
        self.assertEqual(item.source_kind, "rss")
        self.assertEqual(calls, [("https://feed.test/news.xml", {"User-Agent": "test-agent/1.0"}, 4.5)])

    def test_atom_supports_namespaces_and_timezone_filtering(self) -> None:
        xml = """<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><title>Atom story</title><link rel="alternate" href="/atom/1"/>
            <updated>2026-09-02T10:00:00-04:00</updated>
            <summary>Atom summary</summary></entry>
          <entry><title>UTC previous day</title><link href="https://example.test/old"/>
            <published>2026-09-02T00:30:00+02:00</published>
            <updated>2026-09-02T01:30:00+02:00</updated></entry>
        </feed>"""
        adapter = RSSAtomAdapter("atom-source", "https://feed.test/feed", "Atom Publisher", lambda *_: xml)
        items = list(adapter.fetch(self.context()))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].published_time, "2026-09-02T14:00:00Z")
        self.assertEqual(items[0].url, "https://feed.test/atom/1")

    def test_malformed_entries_are_skipped_and_hashes_are_deterministic(self) -> None:
        xml = """<rss><channel>
          <item><title>Good</title><link>https://example.test/good</link>
            <pubDate>Wed, 02 Sep 2026 12:00:00 GMT</pubDate></item>
          <item><title>No link</title><pubDate>Wed, 02 Sep 2026 12:00:00 GMT</pubDate></item>
          <item><title>Bad date</title><link>https://example.test/bad</link><pubDate>not a date</pubDate></item>
        </channel></rss>"""
        first = list(RSSAtomAdapter("source", "https://feed.test", "Pub", lambda *_: xml).fetch(self.context()))[0]
        second = list(RSSAtomAdapter("source", "https://feed.test", "Pub", lambda *_: xml).fetch(self.context()))[0]
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertEqual(first.item_id, second.item_id)
        self.assertEqual(len(first.content_hash), 64)

    def test_malformed_xml_and_unsupported_root_raise_value_error(self) -> None:
        for payload in ("<rss>", "<html><item /></html>"):
            with self.subTest(payload=payload):
                adapter = RSSAtomAdapter("source", "https://feed.test", "Pub", lambda *_: payload)
                with self.assertRaises(ValueError):
                    list(adapter.fetch(self.context()))

    def test_adapter_does_not_use_network_without_injected_callable(self) -> None:
        with self.assertRaises(ValueError):
            RSSAtomAdapter("source", "https://feed.test", "Pub", None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
