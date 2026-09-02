from __future__ import annotations

import unittest

from news_daily.adapters.cninfo import CninfoAnnouncementsAdapter
from news_daily.models import FetchContext, Scope

AS_OF_DATE = "2026-09-02"
RETRIEVED_AT = "2026-09-02T23:59:59Z"
USER_AGENT = "news_daily-test/1.0"

# 2026-09-02 09:30 and 00:30 Beijing time; the latter is still 2026-09-01 in UTC.
ON_DATE_MS = 1788312600000
EARLY_SAME_DAY_MS = 1788280200000
NEXT_DAY_MS = 1788397200000


def context() -> FetchContext:
    return FetchContext(AS_OF_DATE, RETRIEVED_AT, None, 7.5, USER_AGENT)


class RecordingClient:
    """Offline stand-in for the injected transport; no sockets are opened."""

    def __init__(self, payload: object, pages: list[object] | None = None) -> None:
        self.payload = payload
        self.pages = list(pages) if pages is not None else None
        self.calls: list[tuple[str, object, object, float]] = []

    def __call__(
        self, url: str, form: dict[str, str], headers: dict[str, str], timeout: float
    ) -> object:
        self.calls.append((url, form, headers, timeout))
        if self.pages is not None:
            return self.pages.pop(0) if self.pages else {"announcements": []}
        return self.payload


def build(
    payload: object, pages: list[object] | None = None, **kwargs: object
) -> tuple[CninfoAnnouncementsAdapter, RecordingClient]:
    client = RecordingClient(payload, pages)
    return CninfoAnnouncementsAdapter(client=client, **kwargs), client


def announcement(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "announcementId": "1212345678",
        "announcementTitle": "关于子公司签订重大合同的公告",
        "announcementTime": ON_DATE_MS,
        "adjunctUrl": "/finalpage/2026-09-02/1212345678.PDF",
        "secCode": "002792",
        "secName": "嘉友国际",
        "orgId": "9900023475",
        "pageColumn": "szse",
        "announcementTypeName": "临时公告",
    }
    record.update(overrides)
    return record


class CninfoAdapterTests(unittest.TestCase):
    def test_normalizes_announcement_records_into_news_items(self) -> None:
        payload = {
            "totalpages": 1,
            "announcements": [
                announcement(announcementTitle="关于<em>子公司</em>签订重大合同的公告"),
                announcement(
                    announcementId="1212345679",
                    announcementTitle="2026 年半年度报告",
                    announcementTime="2026-09-02 10:15:00",
                    adjunctUrl=None,
                    secCode="600519",
                    secName="贵州茅台",
                    announcementTypeName="定期报告",
                ),
            ],
        }
        adapter, _ = build(payload)
        items = list(adapter.fetch(context()))

        self.assertEqual([item.title for item in items], ["关于子公司签订重大合同的公告", "2026 年半年度报告"])
        first, second = items

        self.assertEqual(first.source_id, "cninfo-announcements")
        self.assertIs(first.scope, Scope.DOMESTIC)
        self.assertEqual(first.publisher, "嘉友国际")
        self.assertEqual(first.url, "https://static.cninfo.com.cn/finalpage/2026-09-02/1212345678.PDF")
        self.assertEqual(first.published_time, "2026-09-02T09:30:00+08:00")
        self.assertEqual(first.retrieved_time, RETRIEVED_AT)
        self.assertEqual(first.source_kind, "cninfo-announcement")
        self.assertEqual(first.language, "zh")
        self.assertEqual(first.snippet, "002792 · 嘉友国际 · 临时公告")
        self.assertEqual(len(first.item_id), 64)
        self.assertEqual(len(first.content_hash), 64)

        # No adjunct URL: fall back to the announcement id.
        self.assertEqual(
            second.url,
            "https://www.cninfo.com.cn/new/disclosure/detail?announcementId=1212345679",
        )
        self.assertEqual(second.published_time, "2026-09-02T10:15:00+08:00")
        self.assertEqual(second.publisher, "贵州茅台")

    def test_hashes_are_stable_and_distinct_per_record(self) -> None:
        payload = {"announcements": [announcement(), announcement(announcementId="1212345679")]}
        adapter, _ = build(payload)
        first_run = [item.to_dict() for item in adapter.fetch(context())]
        second_run = [item.to_dict() for item in adapter.fetch(context())]

        self.assertEqual(first_run, second_run)
        self.assertNotEqual(first_run[0]["content_hash"], first_run[1]["content_hash"])
        self.assertNotEqual(first_run[0]["item_id"], first_run[1]["item_id"])

    def test_filters_records_to_the_as_of_date(self) -> None:
        payload = {
            "announcements": [
                announcement(announcementId="1", announcementTime=ON_DATE_MS),
                announcement(announcementId="2", announcementTime=EARLY_SAME_DAY_MS),
                announcement(announcementId="3", announcementTime=NEXT_DAY_MS),
                announcement(announcementId="4", announcementTime="2026-09-01 10:00:00"),
                announcement(announcementId="5", announcementTime="2026-09-02"),
            ]
        }
        adapter, _ = build(payload)
        items = list(adapter.fetch(context()))
        self.assertEqual([item.title for item in items], ["关于子公司签订重大合同的公告"] * 3)
        self.assertEqual(
            [item.published_time for item in items],
            ["2026-09-02T00:00:00+08:00", "2026-09-02T00:30:00+08:00", "2026-09-02T09:30:00+08:00"],
        )

        later = FetchContext("2026-09-03", RETRIEVED_AT, None, 7.5, USER_AGENT)
        self.assertEqual(len(list(adapter.fetch(later))), 1)

    def test_malformed_records_are_skipped(self) -> None:
        payload = {
            "announcements": [
                "not-a-record",
                None,
                announcement(announcementTitle="   "),
                announcement(announcementTitle=None),
                announcement(adjunctUrl=None, announcementId=""),
                announcement(adjunctUrl="https://evil.example/x.PDF"),
                announcement(announcementTime=None),
                announcement(announcementTime="not-a-date"),
                announcement(announcementTime=True),
                {"announcementTitle": "无日期", "adjunctUrl": "/finalpage/2026-09-02/9.PDF"},
                announcement(announcementId="1212345679"),
            ]
        }
        adapter, _ = build(payload)
        items = list(adapter.fetch(context()))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://static.cninfo.com.cn/finalpage/2026-09-02/1212345678.PDF")

    def test_empty_announcement_list_yields_no_items(self) -> None:
        adapter, client = build({"announcements": []})
        self.assertEqual(list(adapter.fetch(context())), [])
        self.assertEqual(len(client.calls), 1)

    def test_malformed_top_level_payload_raises_value_error(self) -> None:
        cases = {
            "list": [{"announcementTitle": "x"}],
            "string": "unexpected",
            "none": None,
            "missing_key": {"items": []},
            "wrong_type": {"announcements": {"0": "x"}},
            "null_list": {"announcements": None},
        }
        for name, payload in cases.items():
            with self.subTest(payload=name):
                adapter, _ = build(payload)
                with self.assertRaises(ValueError) as raised:
                    adapter.fetch(context())
                self.assertIn("cninfo", str(raised.exception))

        adapter, _ = build({"items": []})
        with self.assertRaises(ValueError) as raised:
            adapter.fetch(context())
        self.assertIn("'announcements'", str(raised.exception))

    def test_injected_client_posts_form_url_headers_and_timeout(self) -> None:
        adapter, client = build({"announcements": []})
        list(adapter.fetch(context()))

        self.assertEqual(len(client.calls), 1)
        url, form, headers, timeout = client.calls[0]
        self.assertEqual(url, "https://www.cninfo.com.cn/new/hisAnnouncement/query")
        self.assertNotIn("?", url)
        self.assertEqual(
            form,
            {
                "column": "szse",
                "isHLtitle": "true",
                "pageNum": "1",
                "pageSize": "30",
                "seDate": "2026-09-02~2026-09-02",
                "tabName": "fulltext",
            },
        )
        self.assertEqual(headers["User-Agent"], USER_AGENT)
        self.assertIn("application/json", headers["Accept"])
        self.assertEqual(headers["Origin"], "https://www.cninfo.com.cn")
        self.assertEqual(
            headers["Referer"],
            "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
        )
        self.assertEqual(headers["X-Requested-With"], "XMLHttpRequest")
        self.assertEqual(timeout, 7.5)

    def test_form_carries_optional_category_and_search_key(self) -> None:
        adapter, client = build(
            {"announcements": []},
            column="sse",
            category="category_ndbg_szsh",
            search_key="年度报告",
            page_size=10,
        )
        self.assertEqual(list(adapter.fetch(context())), [])

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(
            client.calls[0][1],
            {
                "category": "category_ndbg_szsh",
                "column": "sse",
                "isHLtitle": "true",
                "pageNum": "1",
                "pageSize": "10",
                "searchkey": "年度报告",
                "seDate": "2026-09-02~2026-09-02",
                "tabName": "fulltext",
            },
        )

    def test_adapter_shape_matches_source_adapter(self) -> None:
        adapter, client = build(
            {"announcements": []}, source_id="cninfo-sse", column="sse", category="category_ndbg_szsh"
        )
        self.assertEqual(adapter.source_id, "cninfo-sse")
        self.assertIs(adapter.scope, Scope.DOMESTIC)
        self.assertEqual(list(adapter.fetch(context())), [])

        self.assertEqual(client.calls[0][0], "https://www.cninfo.com.cn/new/hisAnnouncement/query")
        self.assertEqual(client.calls[0][1]["column"], "sse")
        self.assertEqual(client.calls[0][1]["category"], "category_ndbg_szsh")

    def test_paginates_two_pages_and_normalizes_both(self) -> None:
        adapter, client = build(
            {"announcements": []},
            pages=[
                {"totalpages": 2, "announcements": [announcement(announcementId="1")]},
                {
                    "totalpages": 2,
                    "announcements": [
                        announcement(
                            announcementId="2",
                            announcementTime="2026-09-02 08:00:00",
                            adjunctUrl="/finalpage/2026-09-02/1212345679.PDF",
                        )
                    ],
                },
            ],
        )
        items = list(adapter.fetch(context()))

        self.assertEqual(len(client.calls), 2)
        self.assertEqual([call[1]["pageNum"] for call in client.calls], ["1", "2"])
        self.assertEqual([item.url for item in items], [
            "https://static.cninfo.com.cn/finalpage/2026-09-02/1212345679.PDF",
            "https://static.cninfo.com.cn/finalpage/2026-09-02/1212345678.PDF",
        ])
        self.assertEqual(
            [item.published_time for item in items],
            ["2026-09-02T08:00:00+08:00", "2026-09-02T09:30:00+08:00"],
        )

    def test_pagination_is_capped_by_max_pages(self) -> None:
        adapter, client = build(
            {"totalpages": 5, "announcements": [announcement()]}, max_pages=2
        )
        items = list(adapter.fetch(context()))

        self.assertEqual(len(client.calls), 2)
        self.assertEqual([call[1]["pageNum"] for call in client.calls], ["1", "2"])
        self.assertEqual(len(items), 2)

    def test_pagination_stops_on_empty_page_and_missing_totalpages(self) -> None:
        adapter, client = build({"announcements": []}, pages=[
            {"totalpages": 3, "announcements": [announcement()]},
            {"totalpages": 3, "announcements": []},
        ])
        items = list(adapter.fetch(context()))

        self.assertEqual(len(items), 1)
        # Page 2 is empty, so page 3 (reported by ``totalpages``) is never requested.
        self.assertEqual(len(client.calls), 2)

        # ``totalpages`` missing (or unusable) means a single page.
        for total in ({}, {"totalpages": None}, {"totalpages": "x"}, {"totalpages": 0}):
            with self.subTest(total=total):
                single, single_client = build({**total, "announcements": [announcement()]})
                self.assertEqual(len(list(single.fetch(context()))), 1)
                self.assertEqual(len(single_client.calls), 1)


if __name__ == "__main__":
    unittest.main()
