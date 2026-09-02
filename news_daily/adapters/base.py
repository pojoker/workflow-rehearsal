"""The intentionally small seam between orchestration and sources."""

from __future__ import annotations

from typing import Iterable, Protocol

from ..models import FetchContext, NewsItem, Scope


class SourceAdapter(Protocol):
    source_id: str
    scope: Scope

    def fetch(self, context: FetchContext) -> Iterable[NewsItem]:
        """Fetch normalized candidate items from one source."""
