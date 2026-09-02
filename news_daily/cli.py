"""Small command-line interface for the deep news_daily module."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ConfigurationError, load_config
from .models import RunRequest, Scope
from .runner import run, status
from .storage import IsolationError, resolve_output_root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m news_daily")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--scope", choices=("domestic", "overseas", "all"), required=True)
    run_parser.add_argument("--date", required=True)
    run_parser.add_argument("--config", type=Path, required=True)
    run_parser.add_argument("--output-root", type=Path)
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--fixture-dir", type=Path)
    status_parser = commands.add_parser("status")
    status_parser.add_argument("--date", required=True)
    status_parser.add_argument("--output-root", type=Path, default=Path("tmp/news-daily-v2"))
    return parser


def _scopes(value: str) -> tuple[Scope, ...]:
    if value == "all":
        return (Scope.DOMESTIC, Scope.OVERSEAS)
    return (Scope(value),)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "status":
            payload = status(args.output_root, args.date)
            print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
            return 0
        config = load_config(args.config)
        output_root = args.output_root or Path(config.output_root)
        resolved_root = resolve_output_root(output_root)
        request = RunRequest(
            scopes=_scopes(args.scope),
            as_of_date=args.date,
            config_path=args.config,
            output_root=resolved_root,
            dry_run=args.dry_run,
            fixture_dir=(args.fixture_dir.resolve() if args.fixture_dir else None),
        )
        result = run(request)
        print(json.dumps(result.to_dict(), ensure_ascii=True, sort_keys=True))
        if result.status == "partial":
            return 2
        if result.status == "failed":
            return 4
        return 0
    except RuntimeError as exc:
        if str(exc).startswith("already_running:"):
            print(json.dumps({"status": "already_running", "error": str(exc)}, sort_keys=True))
            return 3
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True))
        return 4
    except (ConfigurationError, IsolationError, ValueError, OSError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True))
        return 4


if __name__ == "__main__":
    sys.exit(main())
