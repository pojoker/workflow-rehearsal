"""CNInfo (巨潮资讯网) announcement adapter.

The adapter pages through the ``/new/hisAnnouncement/query`` endpoint, which
only answers ``POST`` with a form-encoded body (the ``GET`` variants answer
HTTP 500), and normalizes every ``announcements`` payload into deterministic
:class:`NewsItem` candidates.

The transport is supplied by the caller as ``client(url, form, headers,
timeout)`` returning already-parsed JSON, so the adapter is offline-testable
and performs no writes at runtime.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Callable, Iterable, Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from ..models import FetchContext, NewsItem, Scope

QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
STATIC_BASE_URL = "https://static.cninfo.com.cn/"
DETAIL_URL = "https://www.cninfo.com.cn/new/disclosure/detail"
ALLOWED_HOSTS = frozenset({"cninfo.com.cn", "static.cninfo.com.cn", "www.cninfo.com.cn"})
ORIGIN = "https://www.cninfo.com.cn"
REFERER = "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice"

# Announcement timestamps are published in Beijing time, so the calendar day of
# a disclosure must be resolved in that offset rather than in UTC.
ANNOUNCEMENT_TIMEZONE = timezone(timedelta(hours=8))

# ``client(url, form, headers, timeout) -> parsed JSON``; the form is posted as
# an application/x-www-form-urlencoded body rather than a URL query string.
HttpClient = Callable[[str, Mapping[str, str], Mapping[str, str], float], Any]

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


class CninfoPayloadError(ValueError):
    """A CNInfo payload whose top level cannot be interpreted."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    """Flatten CNInfo string fields: drop highlight tags, unescape, squeeze."""
    if value is None:
        return ""
    return _SPACE_RE.sub(" ", html.unescape(_TAG_RE.sub("", str(value)))).strip()


def _normalized_url(url: str) -> str:
    split = urlsplit(url.strip())
    path = split.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(sorted(parse_qsl(split.query, keep_blank_values=True)))
    return urlunsplit((split.scheme.lower(), split.netloc.lower(), path, query, ""))


def _from_epoch(millis: float) -> tuple[str, str] | None:
    try:
        moment = datetime.fromtimestamp(millis / 1000.0, tz=ANNOUNCEMENT_TIMEZONE)
    except (OverflowError, OSError, ValueError):
        return None
    return moment.date().isoformat(), moment.isoformat(timespec="seconds")


def _published(value: Any) -> tuple[str, str] | None:
    """Return ``(announcement_date, published_time)`` or ``None`` if unusable."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _from_epoch(float(value))
    text = _text(value)
    if not text:
        return None
    if text.isdigit() and len(text) >= 10:
        return _from_epoch(float(text))
    day = text[:10]
    try:
        date.fromisoformat(day)
    except ValueError:
        return None
    clock = text[11:19] if len(text) >= 19 else "00:00:00"
    return day, f"{day}T{clock}+08:00"


def _announcements(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        raise CninfoPayloadError(
            f"cninfo payload must be a JSON object, got {type(payload).__name__}"
        )
    if "announcements" not in payload:
        raise CninfoPayloadError("cninfo payload is missing the 'announcements' key")
    announcements = payload["announcements"]
    if not isinstance(announcements, list):
        raise CninfoPayloadError(
            f"cninfo 'announcements' must be a list, got {type(announcements).__name__}"
        )
    return announcements


def _total_pages(payload: Mapping[str, Any]) -> int:
    """Reported page count, defaulting to a single page when unusable."""
    value = payload.get("totalpages")
    if isinstance(value, bool):
        return 1
    if isinstance(value, (int, float)):
        pages = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        pages = int(value.strip())
    else:
        return 1
    return pages if pages >= 1 else 1


class CninfoAnnouncementsAdapter:
    """Normalize one day of CNInfo announcements into candidate news items."""

    def __init__(
        self,
        *,
        client: HttpClient,
        source_id: str = "cninfo-announcements",
        scope: Scope = Scope.DOMESTIC,
        query_url: str = QUERY_URL,
        static_base_url: str = STATIC_BASE_URL,
        column: str = "szse",
        category: str | None = None,
        search_key: str | None = None,
        page_size: int = 30,
        max_pages: int = 20,
    ) -> None:
        self.source_id = source_id
        self.scope = scope
        self._client = client
        self.query_url = query_url
        self.static_base_url = static_base_url
        self.column = column
        self.category = category
        self.search_key = search_key
        self.page_size = page_size
        self.max_pages = max_pages

    def _request_form(self, as_of_date: str, page_num: int) -> dict[str, str]:
        """Build the POST body for one page; field order is deterministic."""
        form = {
            "column": self.column,
            "isHLtitle": "true",
            "pageNum": str(page_num),
            "pageSize": str(self.page_size),
            "seDate": f"{as_of_date}~{as_of_date}",
            "tabName": "fulltext",
        }
        if self.category:
            form["category"] = self.category
        if self.search_key:
            form["searchkey"] = self.search_key
        return form

    def _headers(self, context: FetchContext) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": ORIGIN,
            "Referer": REFERER,
            "User-Agent": context.user_agent,
            "X-Requested-With": "XMLHttpRequest",
        }

    def _url(self, announcement_id: str, adjunct_url: str) -> str:
        if adjunct_url:
            candidate = urljoin(self.static_base_url, adjunct_url.lstrip("/"))
        elif announcement_id:
            candidate = f"{DETAIL_URL}?{urlencode({'announcementId': announcement_id})}"
        else:
            return ""
        host = (urlsplit(candidate).hostname or "").lower()
        if host not in ALLOWED_HOSTS:
            return ""
        return candidate

    def _item(self, record: Any, context: FetchContext) -> NewsItem | None:
        """Build one item, or ``None`` when the record is unusable."""
        if not isinstance(record, dict):
            return None
        title = _text(record.get("announcementTitle"))
        if not title:
            return None
        announcement_id = _text(record.get("announcementId"))
        url = self._url(announcement_id, _text(record.get("adjunctUrl")))
        if not url:
            return None
        published = _published(record.get("announcementTime"))
        if published is None:
            return None
        announcement_date, published_time = published
        if announcement_date != context.as_of_date:
            return None

        sec_code = _text(record.get("secCode"))
        sec_name = _text(record.get("secName"))
        announcement_type = _text(record.get("announcementTypeName"))
        content = {
            "announcement_id": announcement_id,
            "announcement_type": announcement_type,
            "column": _text(record.get("pageColumn")),
            "org_id": _text(record.get("orgId")),
            "published_time": published_time,
            "sec_code": sec_code,
            "sec_name": sec_name,
            "title": title,
            "url": url,
        }
        content_hash = _sha256(_canonical_json(content))
        snippet = " · ".join(part for part in (sec_code, sec_name, announcement_type) if part)
        return NewsItem(
            item_id=_sha256(
                "\x1f".join([self.source_id, _normalized_url(url), published_time, content_hash])
            ),
            scope=self.scope,
            source_id=self.source_id,
            publisher=sec_name or sec_code or self.source_id,
            title=title,
            url=url,
            published_time=published_time,
            retrieved_time=context.retrieved_at,
            source_kind="cninfo-announcement",
            language="zh",
            content_hash=content_hash,
            snippet=snippet or None,
        )

    def fetch(self, context: FetchContext) -> Iterable[NewsItem]:
        items: list[NewsItem] = []
        total_pages = 1
        page_num = 1
        while page_num <= self.max_pages:
            payload = self._client(
                self.query_url,
                self._request_form(context.as_of_date, page_num),
                self._headers(context),
                context.timeout_seconds,
            )
            records = _announcements(payload)
            if not records:
                break
            for record in records:
                item = self._item(record, context)
                if item is not None:
                    items.append(item)
            if page_num == 1:
                total_pages = _total_pages(payload)
            if page_num >= total_pages:
                break
            page_num += 1
        items.sort(key=lambda item: (item.published_time, item.title, item.url, item.content_hash))
        return items


__all__ = ["ALLOWED_HOSTS", "CninfoAnnouncementsAdapter", "CninfoPayloadError", "HttpClient"]
