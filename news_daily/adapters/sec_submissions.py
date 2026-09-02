"""Read-only SEC EDGAR submissions adapter for overseas news candidates."""

from __future__ import annotations

import hashlib
import json
import ntpath
from datetime import date
from typing import Any, Callable, Iterable
from urllib.parse import quote, urlsplit

from ..models import FetchContext, NewsItem, Scope


GetJSON = Callable[[str, dict[str, str], float], Any]
SEC_DATA_HOST = "data.sec.gov"
SEC_ARCHIVES_HOST = "www.sec.gov"


def _normalize_cik(value: object) -> str:
    if isinstance(value, bool):
        raise ValueError("CIK must contain only digits")
    text = str(value).strip()
    if not text or not text.isdigit() or len(text) > 10:
        raise ValueError(f"invalid CIK: {value!r}")
    return text.zfill(10)


def _official_url(url: str, host: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != host or parsed.username or parsed.password:
        raise ValueError(f"SEC URL must use official HTTPS host {host}")
    return url


def _hash(fields: dict[str, str]) -> str:
    payload = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _item_id(source_id: str, url: str, published_time: str, content_hash: str) -> str:
    identity = "\x1f".join((source_id, url, published_time, content_hash))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


class SECSubmissionsAdapter:
    """Fetch recent SEC submissions for one or more CIKs."""

    scope = Scope.OVERSEAS

    def __init__(self, source_id: str, ciks: str | int | Iterable[str | int], get_json: GetJSON) -> None:
        self.source_id = str(source_id).strip()
        if isinstance(ciks, (str, int)) and not isinstance(ciks, bool):
            values = [ciks]
        else:
            try:
                values = list(ciks)  # type: ignore[arg-type]
            except TypeError as exc:
                raise ValueError("ciks must contain one or more CIKs") from exc
        if not self.source_id or not values:
            raise ValueError("source_id and at least one CIK are required")
        normalized: list[str] = []
        for value in values:
            cik = _normalize_cik(value)
            if cik not in normalized:
                normalized.append(cik)
        if not callable(get_json):
            raise ValueError("get_json must be callable")
        self.ciks = tuple(normalized)
        self.get_json = get_json

    @staticmethod
    def _headers(context: FetchContext) -> dict[str, str]:
        return {"User-Agent": context.user_agent}

    @staticmethod
    def _submissions_url(cik: str) -> str:
        return _official_url(f"https://{SEC_DATA_HOST}/submissions/CIK{cik}.json", SEC_DATA_HOST)

    @staticmethod
    def _archive_url(cik: str, accession_number: str, primary_document: str) -> str:
        accession = accession_number.replace("-", "")
        if len(accession) != 18 or not accession.isdigit():
            raise ValueError("invalid accession number")
        if not isinstance(primary_document, str):
            raise ValueError("primary document must be a string")
        if (
            not primary_document
            or primary_document.startswith("/")
            or ntpath.isabs(primary_document)
            or "\\" in primary_document
            or "?" in primary_document
            or "#" in primary_document
        ):
            raise ValueError("missing or invalid primary document")
        segments = primary_document.split("/")
        if any(not segment or segment in {".", ".."} for segment in segments):
            raise ValueError("primary document path traversal is not allowed")
        document = "/".join(quote(segment, safe="") for segment in segments)
        return _official_url(
            f"https://{SEC_ARCHIVES_HOST}/Archives/edgar/data/{int(cik)}/{accession}/{document}",
            SEC_ARCHIVES_HOST,
        )

    @staticmethod
    def _recent(payload: Any, cik: str) -> tuple[dict[str, list[Any]], str]:
        if not isinstance(payload, dict):
            raise ValueError(f"SEC submissions payload for CIK {cik} must be an object")
        filings = payload.get("filings")
        recent = filings.get("recent") if isinstance(filings, dict) else None
        if not isinstance(recent, dict):
            raise ValueError(f"SEC submissions payload for CIK {cik} has no filings.recent object")
        required = ("form", "filingDate", "accessionNumber", "primaryDocument")
        arrays: dict[str, list[Any]] = {}
        for field in required:
            value = recent.get(field)
            if not isinstance(value, list):
                raise ValueError(f"SEC submissions payload for CIK {cik} has no recent.{field} array")
            arrays[field] = value
        row_count = max((len(values) for values in arrays.values()), default=0)
        report_dates = recent.get("reportDate")
        if report_dates is None:
            arrays["reportDate"] = [""] * row_count
        elif isinstance(report_dates, list):
            arrays["reportDate"] = list(report_dates) + [""] * max(0, row_count - len(report_dates))
        else:
            raise ValueError(f"SEC submissions payload for CIK {cik} has invalid recent.reportDate array")
        company = payload.get("name", payload.get("companyName", ""))
        return arrays, str(company).strip()

    def _parse(self, payload: Any, cik: str, context: FetchContext) -> list[NewsItem]:
        arrays, company = self._recent(payload, cik)
        try:
            requested = date.fromisoformat(context.as_of_date)
        except ValueError as exc:
            raise ValueError("FetchContext.as_of_date must be YYYY-MM-DD") from exc
        result: list[NewsItem] = []
        row_count = max(len(values) for values in arrays.values())
        for index in range(row_count):
            try:
                raw_form = arrays["form"][index]
                raw_filing_date = arrays["filingDate"][index]
                raw_accession = arrays["accessionNumber"][index]
                raw_primary_document = arrays["primaryDocument"][index]
                raw_report_date = arrays["reportDate"][index]
                values = (raw_form, raw_filing_date, raw_accession, raw_primary_document, raw_report_date)
                if not all(isinstance(value, str) for value in values):
                    continue
                form = raw_form.strip()
                filing_date = raw_filing_date.strip()
                accession = raw_accession.strip()
                primary_document = raw_primary_document.strip()
                report_date = raw_report_date.strip()
                if not form or date.fromisoformat(filing_date) != requested:
                    continue
                url = self._archive_url(cik, accession, primary_document)
            except (IndexError, TypeError, ValueError):
                continue
            title = f"{form} filing: {company or cik}"
            snippet = f"form={form}; company={company}"
            if report_date:
                snippet += f"; reportDate={report_date}"
            content_hash = _hash(
                {
                    "form": form,
                    "company": company,
                    "reportDate": report_date,
                    "filingDate": filing_date,
                    "url": url,
                }
            )
            published_time = f"{filing_date}T00:00:00Z"
            result.append(
                NewsItem(
                    item_id=_item_id(self.source_id, url, published_time, content_hash),
                    scope=self.scope,
                    source_id=self.source_id,
                    publisher=company or self.source_id,
                    title=title,
                    url=url,
                    published_time=published_time,
                    retrieved_time=context.retrieved_at,
                    source_kind="sec_submissions",
                    language="en",
                    content_hash=content_hash,
                    snippet=snippet,
                )
            )
        return result

    def fetch(self, context: FetchContext) -> Iterable[NewsItem]:
        for cik in self.ciks:
            url = self._submissions_url(cik)
            try:
                payload = self.get_json(url, self._headers(context), context.timeout_seconds)
            except Exception as exc:
                raise ValueError(f"SEC submissions request failed for CIK {cik}: {exc}") from exc
            yield from self._parse(payload, cik, context)


__all__ = ["SECSubmissionsAdapter"]
