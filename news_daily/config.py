"""Configuration loading and adapter registry hooks."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import http
from .adapters.cninfo import CninfoAnnouncementsAdapter
from .adapters.fixture import FixtureAdapter
from .adapters.rss_atom import RSSAtomAdapter
from .adapters.sec_submissions import SECSubmissionsAdapter
from .adapters.base import SourceAdapter
from .models import Scope


class ConfigurationError(ValueError):
    """The supplied configuration cannot describe a run."""


@dataclass(frozen=True)
class LoadedConfig:
    output_root: str
    timeout_seconds: float
    user_agent: str
    adapter_specs: tuple[dict[str, Any], ...]


def load_config(path: Path) -> LoadedConfig:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise ConfigurationError(f"cannot read config: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"invalid TOML config: {exc}") from exc
    output = data.get("output", {})
    if not isinstance(output, dict):
        raise ConfigurationError("[output] must be a table")
    try:
        timeout = float(output.get("timeout_seconds", data.get("timeout_seconds", 10)))
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("timeout_seconds must be a number") from exc
    if timeout < 0:
        raise ConfigurationError("timeout_seconds must not be negative")
    adapters = data.get("adapters", {})
    if not isinstance(adapters, dict):
        raise ConfigurationError("[adapters.*] sections are required")
    specs: list[dict[str, Any]] = []
    for name, raw in adapters.items():
        if not isinstance(raw, dict):
            raise ConfigurationError(f"adapter {name} must be a table")
        spec = dict(raw)
        spec.setdefault("source_id", str(name))
        specs.append(spec)
    return LoadedConfig(
        output_root=str(output.get("root", data.get("output_root", "tmp/news-daily-v2"))),
        timeout_seconds=timeout,
        user_agent=str(output.get("user_agent", "news_daily/1.0 (configure-me)")),
        adapter_specs=tuple(specs),
    )


def adapters_for(
    config: LoadedConfig,
    scopes: tuple[Scope, ...],
    fixture_dir: Path | None,
) -> tuple[SourceAdapter, ...]:
    specs = list(config.adapter_specs)
    if not specs and fixture_dir is not None:
        specs = [
            {"source_id": f"fixture-{scope.value}", "scope": scope.value, "kind": "fixture"}
            for scope in scopes
        ]
    result: list[SourceAdapter] = []
    for spec in specs:
        if "enabled" in spec and not isinstance(spec["enabled"], bool):
            raise ConfigurationError("adapter enabled must be a boolean")
        if spec.get("enabled", True) is False:
            continue
        source_id = _string(spec, "source_id", "adapter")
        kind = _string(spec, "kind", f"adapter {source_id}", default="fixture")
        try:
            scope = Scope(str(spec.get("scope", "")))
        except ValueError:
            raise ConfigurationError(f"adapter {source_id} has invalid scope")
        try:
            if kind == "fixture":
                file_name = spec.get("file")
                if file_name is not None and (not isinstance(file_name, str) or not file_name.strip()):
                    raise ConfigurationError(f"adapter {source_id} file must be a non-empty string")
                adapter: SourceAdapter = FixtureAdapter(
                    source_id=source_id,
                    scope=scope,
                    fixture_dir=fixture_dir,
                    file_name=file_name,
                    options=spec,
                )
            elif kind == "cninfo":
                if scope is not Scope.DOMESTIC:
                    raise ConfigurationError(f"adapter {source_id} cninfo scope must be domestic")
                adapter = CninfoAnnouncementsAdapter(
                    client=http.post_form_json,
                    source_id=source_id,
                    scope=scope,
                    query_url=_optional_string(spec, "query_url", source_id),
                    static_base_url=_optional_string(spec, "static_base_url", source_id),
                    column=_optional_string(spec, "column", source_id),
                    category=_optional_string(spec, "category", source_id, allow_none=True),
                    search_key=_optional_string(spec, "search_key", source_id, allow_none=True),
                    page_size=_positive_int(spec, "page_size", source_id, 30),
                    max_pages=_positive_int(spec, "max_pages", source_id, 20),
                )
            elif kind == "rss_atom":
                if scope is not Scope.OVERSEAS:
                    raise ConfigurationError(f"adapter {source_id} rss_atom scope must be overseas")
                adapter = RSSAtomAdapter(
                    source_id,
                    _required_string(spec, "feed_url", source_id),
                    _required_string(spec, "publisher", source_id),
                    http.get_text,
                )
            elif kind == "sec_submissions":
                if scope is not Scope.OVERSEAS:
                    raise ConfigurationError(f"adapter {source_id} sec_submissions scope must be overseas")
                ciks = spec.get("ciks")
                if not isinstance(ciks, list) or not ciks:
                    raise ConfigurationError(f"adapter {source_id} ciks must be a non-empty list")
                adapter = SECSubmissionsAdapter(source_id, ciks, http.get_json)
            else:
                raise ConfigurationError(f"adapter {source_id} has unknown kind: {kind}")
        except ConfigurationError:
            raise
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"adapter {source_id} is invalid: {exc}") from exc
        if scope in scopes:
            result.append(adapter)
    return tuple(sorted(result, key=lambda adapter: (adapter.scope.value, adapter.source_id)))


def _string(
    spec: dict[str, Any], key: str, label: str, default: str | None = None
) -> str:
    value = spec.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{label} {key} must be a non-empty string")
    return value.strip()


def _required_string(spec: dict[str, Any], key: str, source_id: str) -> str:
    return _string(spec, key, f"adapter {source_id}")


def _optional_string(
    spec: dict[str, Any], key: str, source_id: str, allow_none: bool = False
) -> str | None:
    if key not in spec and allow_none:
        return None
    if key not in spec:
        defaults = {
            "query_url": "https://www.cninfo.com.cn/new/hisAnnouncement/query",
            "static_base_url": "https://static.cninfo.com.cn/",
            "column": "szse",
        }
        return defaults[key]
    value = spec[key]
    if allow_none and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"adapter {source_id} {key} must be a non-empty string")
    return value.strip()


def _positive_int(spec: dict[str, Any], key: str, source_id: str, default: int) -> int:
    value = spec.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"adapter {source_id} {key} must be a positive integer")
    return value
