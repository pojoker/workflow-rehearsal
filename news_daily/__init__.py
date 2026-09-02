"""Isolated daily news acquisition core."""

from .models import NewsItem, RunRequest, RunResult, Scope, SourceFailure

__all__ = ["NewsItem", "RunRequest", "RunResult", "Scope", "SourceFailure"]
