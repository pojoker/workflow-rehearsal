"""Small, bounded, read-only HTTP transports for live adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def _request(url: str, headers: Mapping[str, str], timeout: float, data: bytes | None = None) -> bytes:
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must use HTTP or HTTPS")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    request = Request(url, data=data, headers=dict(headers), method="POST" if data is not None else "GET")
    with urlopen(request, timeout=timeout) as response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError(f"HTTP response exceeds {MAX_RESPONSE_BYTES} bytes")
    return payload


def get_text(url: str, headers: Mapping[str, str], timeout: float) -> bytes:
    """Fetch a bounded HTTP response without creating or modifying files."""
    return _request(url, headers, timeout)


def _json_response(url: str, payload: bytes) -> object:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"invalid UTF-8 JSON response from {url}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON response from {url}: {exc.msg}") from exc


def get_json(url: str, headers: Mapping[str, str], timeout: float) -> object:
    return _json_response(url, get_text(url, headers, timeout))


def post_form_json(
    url: str,
    form: Mapping[str, str],
    headers: Mapping[str, str],
    timeout: float,
) -> object:
    request_headers = dict(headers)
    request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    payload = urlencode(dict(form)).encode("utf-8")
    return _json_response(url, _request(url, request_headers, timeout, payload))


__all__ = ["MAX_RESPONSE_BYTES", "get_json", "get_text", "post_form_json"]
