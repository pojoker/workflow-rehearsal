"""Output-root isolation, locks, and atomic publication."""

from __future__ import annotations

import json
import errno
import os
import re
import stat
import shutil
import uuid
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Iterator


class IsolationError(ValueError):
    """An output path is not safe for this isolated module."""


def resolve_output_root(value: str | Path) -> Path:
    supplied = Path(value).expanduser()
    absolute = supplied if supplied.is_absolute() else Path.cwd() / supplied
    # A symlink in the requested path is rejected rather than guessed about.
    current = Path(absolute.anchor or "/")
    for part in absolute.parts[1:] if absolute.is_absolute() else absolute.parts:
        current /= part
        if current.is_symlink() and current.parent != Path("/"):
            raise IsolationError("output root may not contain symlink components")
    resolved = absolute.resolve(strict=False)
    repo = Path(__file__).resolve().parents[1]
    allowed_in_repo = repo / "tmp" / "news-daily-v2"
    try:
        resolved.relative_to(repo)
    except ValueError:
        pass
    else:
        try:
            resolved.relative_to(allowed_in_repo)
        except ValueError as exc:
            raise IsolationError(f"forbidden output root: {resolved}") from exc
    if resolved.exists() and not resolved.is_dir():
        raise IsolationError("output root is not a directory")
    return resolved


class RunLock(AbstractContextManager["RunLock"]):
    def __init__(self, root: Path, date: str, scopes: tuple[str, ...]) -> None:
        self.root = root
        self.date = date
        self.scopes = scopes
        self.paths: list[Path] = []

    def __enter__(self) -> "RunLock":
        locks = self.root / ".locks"
        locks.mkdir(parents=True, exist_ok=True)
        try:
            for scope in self.scopes:
                path = locks / f"{self.date}-{scope}.lock"
                fd = self._acquire(path, scope)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps({"pid": os.getpid(), "date": self.date, "scope": scope}))
                self.paths.append(path)
        except Exception:
            self._release()
            raise
        return self

    @staticmethod
    def _acquire(path: Path, scope: str) -> int:
        for attempt in range(2):
            try:
                return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as exc:
                if attempt == 0 and _recover_stale_lock(path):
                    continue
                raise RuntimeError(f"already_running: {path.name.removesuffix('.lock')}/{scope}") from exc
        raise AssertionError("lock acquisition loop did not return")

    def _release(self) -> None:
        for path in reversed(self.paths):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self.paths.clear()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._release()


def _recover_stale_lock(path: Path) -> bool:
    """Remove one unchanged lock only when its PID is certainly dead."""
    try:
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            return False
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    pid = payload.get("pid") if isinstance(payload, dict) else None
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pass
    except OSError as exc:
        if exc.errno != errno.ESRCH:
            return False
    except (OverflowError, ValueError):
        return False
    else:
        return False

    try:
        after = path.stat()
    except FileNotFoundError:
        return True
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def new_run_id(date: str, scopes: tuple[str, ...]) -> str:
    return f"{date}-{'-'.join(scopes)}-{uuid.uuid4().hex[:12]}"


def make_stage(root: Path, date: str, scope: str, run_id: str) -> Path:
    stage = root / ".staging" / f"{date}-{scope}-{run_id}-{uuid.uuid4().hex[:8]}"
    stage.mkdir(parents=True, exist_ok=False)
    return stage


def publish(stage: Path, root: Path, date: str, scope: str, run_id: str) -> Path:
    destination = root / date / scope / "runs" / run_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(stage, destination)
    try:
        stage.parent.rmdir()
    except OSError:
        pass
    latest = destination.parent.parent / "latest.json"
    temporary = latest.with_name(f".{latest.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps({"run_id": run_id}, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, latest)
    return destination


def cleanup_stage(stage: Path | None) -> None:
    if stage is not None and stage.exists():
        shutil.rmtree(stage)


def read_latest(root: Path, date: str, scope: str) -> tuple[Path, dict[str, Any]] | None:
    latest = root / date / scope / "latest.json"
    if not latest.is_file():
        return None
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
        run_id = str(payload["run_id"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
        return None
    manifest = root / date / scope / "runs" / run_id / "manifest.json"
    try:
        return manifest, json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
