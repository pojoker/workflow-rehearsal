"""Read-only RSS 2.0 and Atom feeds for overseas news."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Iterable
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

from ..models import FetchContext, NewsItem, Scope


GetText = Callable[[str, dict[str, str], float], str | bytes]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def _child(element: ElementTree.Element, *names: str) -> ElementTree.Element | None:
    for name in names:
        wanted = name.lower()
        for candidate in element:
            if _local_name(candidate.tag) == wanted:
                return candidate
    return None


def _canonical_url(value: str, base_url: str) -> str:
    resolved = urljoin(base_url, value.strip())
    resolved, _ = urldefrag(resolved)
    split = urlsplit(resolved)
    if split.scheme.lower() not in {"http", "https"} or not split.netloc:
        raise ValueError("link is not an HTTP(S) URL")
    return urlunsplit((split.scheme.lower(), split.netloc.lower(), split.path or "/", split.query, ""))


def _parse_datetime(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError("missing publication date")
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"invalid publication date: {text}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp(value: str) -> str:
    return _parse_datetime(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _hash(fields: dict[str, str | None]) -> str:
    payload = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _item_id(source_id: str, url: str, published_time: str, content_hash: str) -> str:
    identity = "\x1f".join((source_id, url, published_time, content_hash))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _date_is_requested(timestamp: str, as_of_date: str) -> bool:
    try:
        requested = date.fromisoformat(as_of_date)
    except ValueError as exc:
        raise ValueError("FetchContext.as_of_date must be YYYY-MM-DD") from exc
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date() == requested


class RSSAtomAdapter:
    """Fetch and normalize one RSS 2.0 or Atom feed without writing files."""

    scope = Scope.OVERSEAS

    def __init__(
        self,
        source_id: str,
        feed_url: str,
        publisher: str,
        get_text: GetText,
    ) -> None:
        self.source_id = str(source_id).strip()
        self.feed_url = str(feed_url).strip()
        self.publisher = str(publisher).strip()
        self.get_text = get_text
        if not self.source_id or not self.publisher:
            raise ValueError("source_id and publisher are required")
        parsed_url = urlsplit(self.feed_url)
        if parsed_url.scheme.lower() not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("feed_url must be an HTTP(S) URL")
        if not callable(get_text):
            raise ValueError("get_text must be callable")

    def _headers(self, context: FetchContext) -> dict[str, str]:
        return {
            "User-Agent": context.user_agent,
        }

    def _parse(self, payload: str | bytes, context: FetchContext) -> list[NewsItem]:
        if not isinstance(payload, (str, bytes)):
            raise ValueError("feed response must be text or bytes")
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            raise ValueError(f"malformed feed XML: {exc}") from exc

        root_name = _local_name(root.tag)
        if root_name == "rss":
            channel = _child(root, "channel")
            if channel is None:
                raise ValueError("RSS feed has no channel")
            return self._parse_rss(channel, context)
        if root_name == "feed":
            return self._parse_atom(root, context)
        raise ValueError(f"unsupported feed root: {root_name}")

    def _parse_rss(self, channel: ElementTree.Element, context: FetchContext) -> list[NewsItem]:
        result: list[NewsItem] = []
        for entry in channel:
            if _local_name(entry.tag) != "item":
                continue
            try:
                title = _text(_child(entry, "title"))
                link = _text(_child(entry, "link"))
                published = _text(_child(entry, "pubDate", "published", "updated", "date"))
                summary = _text(_child(entry, "description", "summary", "content")) or None
                timestamp = _timestamp(published)
                canonical_link = _canonical_url(link, self.feed_url)
                if not title or not _date_is_requested(timestamp, context.as_of_date):
                    continue
            except (ValueError, TypeError):
                continue
            result.append(self._make_item(title, canonical_link, timestamp, summary, context, "rss"))
        return result

    def _parse_atom(self, feed: ElementTree.Element, context: FetchContext) -> list[NewsItem]:
        result: list[NewsItem] = []
        for entry in feed:
            if _local_name(entry.tag) != "entry":
                continue
            try:
                title = _text(_child(entry, "title"))
                date_element = _child(entry, "updated", "published")
                timestamp = _timestamp(_text(date_element))
                links = [candidate for candidate in entry if _local_name(candidate.tag) == "link"]
                link_element = next(
                    (candidate for candidate in links if candidate.attrib.get("rel", "alternate") == "alternate"),
                    links[0] if links else None,
                )
                if link_element is None:
                    raise ValueError("missing Atom link")
                canonical_link = _canonical_url(link_element.attrib.get("href", ""), self.feed_url)
                summary = _text(_child(entry, "summary", "content")) or None
                if not title or not _date_is_requested(timestamp, context.as_of_date):
                    continue
            except (ValueError, TypeError):
                continue
            result.append(self._make_item(title, canonical_link, timestamp, summary, context, "atom"))
        return result

    def _make_item(
        self,
        title: str,
        url: str,
        published_time: str,
        summary: str | None,
        context: FetchContext,
        source_kind: str,
    ) -> NewsItem:
        content_hash = _hash(
            {"title": title, "url": url, "published_time": published_time, "snippet": summary}
        )
        return NewsItem(
            item_id=_item_id(self.source_id, url, published_time, content_hash),
            scope=self.scope,
            source_id=self.source_id,
            publisher=self.publisher,
            title=title,
            url=url,
            published_time=published_time,
            retrieved_time=context.retrieved_at,
            source_kind=source_kind,
            language="en",
            content_hash=content_hash,
            snippet=summary,
        )

    def fetch(self, context: FetchContext) -> Iterable[NewsItem]:
        payload = self.get_text(self.feed_url, self._headers(context), context.timeout_seconds)
        yield from self._parse(payload, context)


__all__ = ["RSSAtomAdapter"]
