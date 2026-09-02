"""Configuration loading and adapter registry hooks."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters.fixture import FixtureAdapter
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
) -> tuple[FixtureAdapter, ...]:
    specs = list(config.adapter_specs)
    if not specs and fixture_dir is not None:
        specs = [
            {"source_id": f"fixture-{scope.value}", "scope": scope.value, "kind": "fixture"}
            for scope in scopes
        ]
    result: list[FixtureAdapter] = []
    for spec in specs:
        kind = str(spec.get("kind", "fixture"))
        if kind != "fixture":
            continue
        try:
            scope = Scope(str(spec.get("scope", "")))
        except ValueError:
            raise ConfigurationError(f"adapter {spec['source_id']} has invalid scope")
        if scope not in scopes:
            continue
        result.append(
            FixtureAdapter(
                source_id=str(spec["source_id"]),
                scope=scope,
                fixture_dir=fixture_dir,
                file_name=(str(spec["file"]) if spec.get("file") is not None else None),
                options=spec,
            )
        )
    return tuple(sorted(result, key=lambda adapter: (adapter.scope.value, adapter.source_id)))
