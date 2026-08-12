"""Evidence-gated overseas company event ledger.

The public seam is intentionally small: callers load validated facts once and
derive every reader-facing view from the same deterministic projection.  This
module never reads or writes canonical industry-chain tables or shipments.csv.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from .schema import ENUMS, FILES


class EventLedgerError(ValueError):
    """Raised when the event ledger violates its data contract."""


EVENT_FILES = (
    "watch_entities.csv",
    "disclosures.csv",
    "event_claims.csv",
    "events.csv",
    "event_evidence.csv",
)
MATURE_COMMERCIAL_STAGES = frozenset({
    "volume_order", "first_shipment", "ramping", "scaled",
})
INDEPENDENT_CLASSES = frozenset({
    "counterparty", "regulator", "observable_result",
})


def _read_csv(path: Path, expected: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected:
            raise EventLedgerError(
                f"{path.name}: header mismatch; expected {expected}"
            )
        return list(reader)


def _index(rows: list[dict[str, str]], field: str, filename: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for line, row in enumerate(rows, 2):
        value = row[field].strip()
        if not value:
            raise EventLedgerError(f"{filename}:{line}: empty {field}")
        if value in result:
            raise EventLedgerError(f"{filename}:{line}: duplicate {field} {value}")
        result[value] = row
    return result


def _enum(row: dict[str, str], field: str, enum_name: str, where: str) -> None:
    if row[field] not in ENUMS[enum_name]:
        raise EventLedgerError(f"{where}: invalid {field}={row[field]!r}")


def _split_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def _date(value: str, field: str, where: str) -> None:
    if not value:
        return
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise EventLedgerError(f"{where}: invalid {field}={value!r}") from exc


def _url_ok(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def load_event_facts(root: Path) -> dict:
    """Load and validate event-ledger facts behind one stable interface."""
    calls_dir = root / "calls"
    rows = {
        name: _read_csv(calls_dir / name, FILES[name])
        for name in EVENT_FILES
    }
    universe_rows = _read_csv(calls_dir / "universe.csv", FILES["universe.csv"])
    source_rows = _read_csv(calls_dir / "sources.csv", FILES["sources.csv"])
    claim_rows = _read_csv(calls_dir / "claims.csv", FILES["claims.csv"])
    theme_rows = _read_csv(calls_dir / "themes.csv", FILES["themes.csv"])

    universe = _index(universe_rows, "company_id", "universe.csv")
    watch = _index(rows["watch_entities.csv"], "entity_id", "watch_entities.csv")
    sources = _index(source_rows, "source_id", "sources.csv")
    legacy_claims = _index(claim_rows, "claim_id", "claims.csv")
    themes = _index(theme_rows, "theme_id", "themes.csv")
    disclosures = _index(rows["disclosures.csv"], "disclosure_id", "disclosures.csv")
    event_claims = _index(rows["event_claims.csv"], "event_claim_id", "event_claims.csv")
    events = _index(rows["events.csv"], "event_id", "events.csv")
    evidence = _index(rows["event_evidence.csv"], "evidence_id", "event_evidence.csv")

    overlap = set(universe) & set(watch)
    if overlap:
        raise EventLedgerError(
            f"watch_entities.csv: entity_id collides with universe company_id: {sorted(overlap)}"
        )

    entities = dict(universe)
    for entity_id, row in watch.items():
        where = f"watch_entities:{entity_id}"
        _enum(row, "entity_type", "entity_type", where)
        _enum(row, "monitoring_status", "monitoring_status", where)
        promoted = row["promoted_company_id"]
        if row["monitoring_status"] == "promoted":
            if not promoted or promoted not in universe:
                raise EventLedgerError(f"{where}: promoted entity needs known promoted_company_id")
            continue
        if promoted:
            raise EventLedgerError(f"{where}: only promoted entities may set promoted_company_id")
        entities[entity_id] = row

    for disclosure_id, row in disclosures.items():
        where = f"disclosures:{disclosure_id}"
        if row["publisher_entity_id"] not in entities:
            raise EventLedgerError(f"{where}: unknown publisher_entity_id")
        for field, enum_name in (
            ("disclosure_type", "disclosure_type"),
            ("content_class", "content_class"),
            ("provenance_class", "provenance_class"),
            ("retrieval_status", "retrieval_status"),
            ("processing_status", "processing_status"),
        ):
            _enum(row, field, enum_name, where)
        for field in ("published_at", "updated_at", "discovered_at", "retrieved_at", "reviewed_at"):
            _date(row[field], field, where)
        if row["canonical_url"] and not _url_ok(row["canonical_url"]):
            raise EventLedgerError(f"{where}: invalid canonical_url")
        if not row["origin_group"]:
            raise EventLedgerError(f"{where}: origin_group is required for deduplication")
        if row["local_path"] and not (calls_dir / row["local_path"]).is_file():
            raise EventLedgerError(f"{where}: local_path does not exist")
        if row["retrieval_status"] == "retrieved":
            if not row["retrieved_at"] or not (row["canonical_url"] or row["local_path"]):
                raise EventLedgerError(f"{where}: retrieved disclosure lacks retrieval time or anchor")
        if row["processing_status"] in {"anchor_reviewed", "no_relevant_claims"}:
            if not row["reviewed_at"] or not row["review_scope"]:
                raise EventLedgerError(f"{where}: reviewed processing state lacks reviewed_at/review_scope")
        legacy_source_id = row["legacy_source_id"]
        if legacy_source_id:
            source = sources.get(legacy_source_id)
            if not source:
                raise EventLedgerError(f"{where}: unknown legacy_source_id")
            if source["company_id"] != row["publisher_entity_id"]:
                raise EventLedgerError(f"{where}: legacy source publisher mismatch")

    for event_claim_id, row in event_claims.items():
        where = f"event_claims:{event_claim_id}"
        disclosure = disclosures.get(row["disclosure_id"])
        if not disclosure:
            raise EventLedgerError(f"{where}: unknown disclosure_id")
        if row["claimant_entity_id"] not in entities:
            raise EventLedgerError(f"{where}: unknown claimant_entity_id")
        for field, enum_name in (
            ("claimant_role", "event_claimant_role"),
            ("statement_kind", "event_statement_kind"),
            ("review_status", "event_review_status"),
        ):
            _enum(row, field, enum_name, where)
        _date(row["reviewed_at"], "reviewed_at", where)
        if row["review_status"] == "anchor_reviewed":
            if not row["quote"] or not row["anchor"] or not row["reviewed_at"]:
                raise EventLedgerError(f"{where}: anchor-reviewed claim lacks quote/anchor/reviewed_at")
            if disclosure["processing_status"] != "anchor_reviewed":
                raise EventLedgerError(f"{where}: reviewed claim requires anchor-reviewed disclosure")
        legacy_claim_id = row["legacy_claim_id"]
        if legacy_claim_id:
            legacy = legacy_claims.get(legacy_claim_id)
            if not legacy:
                raise EventLedgerError(f"{where}: unknown legacy_claim_id")
            if legacy["source_id"] != disclosure["legacy_source_id"]:
                raise EventLedgerError(f"{where}: legacy claim/source mismatch")
            if legacy["review_status"] == "reviewed" and row["review_status"] != "anchor_reviewed":
                raise EventLedgerError(f"{where}: reviewed legacy claim must map to anchor_reviewed")

    for event_id, row in events.items():
        where = f"events:{event_id}"
        for field, enum_name in (
            ("event_category", "event_category"),
            ("lifecycle_stage", "lifecycle_stage"),
            ("event_status", "event_status"),
            ("date_precision", "date_precision"),
        ):
            _enum(row, field, enum_name, where)
        if row["primary_subject_id"] not in entities:
            raise EventLedgerError(f"{where}: unknown primary_subject_id")
        for entity_id in _split_ids(row["counterparty_ids"]):
            if entity_id not in entities:
                raise EventLedgerError(f"{where}: unknown counterparty_id {entity_id}")
        for theme_id in _split_ids(row["theme_ids"]):
            if theme_id not in themes:
                raise EventLedgerError(f"{where}: unknown theme_id {theme_id}")
        for field in ("occurred_start", "occurred_end"):
            _date(row[field], field, where)
        if row["occurred_start"] and row["occurred_end"] and row["occurred_start"] > row["occurred_end"]:
            raise EventLedgerError(f"{where}: occurred_start is after occurred_end")
        previous_id = row["previous_event_id"]
        if previous_id:
            previous = events.get(previous_id)
            if not previous:
                raise EventLedgerError(f"{where}: unknown previous_event_id")
            if previous_id == event_id or previous["program_id"] != row["program_id"]:
                raise EventLedgerError(f"{where}: previous event must be distinct and in same program")

    for event_id in events:
        seen: set[str] = set()
        current_id = event_id
        while current_id:
            if current_id in seen:
                raise EventLedgerError(f"events:{event_id}: previous_event_id cycle detected")
            seen.add(current_id)
            current_id = events[current_id]["previous_event_id"]

    evidence_by_event: dict[str, list[dict[str, str]]] = defaultdict(list)
    for evidence_id, row in evidence.items():
        where = f"event_evidence:{evidence_id}"
        event = events.get(row["event_id"])
        claim = event_claims.get(row["event_claim_id"])
        if not event or not claim:
            raise EventLedgerError(f"{where}: broken event/claim reference")
        _enum(row, "relationship", "event_relationship", where)
        _enum(row, "independence_class", "independence_class", where)
        disclosure = disclosures[claim["disclosure_id"]]
        if row["origin_group"] != disclosure["origin_group"]:
            raise EventLedgerError(f"{where}: origin_group differs from disclosure")
        provenance = disclosure["provenance_class"]
        expected_provenance = {
            "first_party": {"first_party"},
            "counterparty": {"counterparty"},
            "regulator": {"regulator", "government"},
            "third_party": {"third_party"},
            "observable_result": {"counterparty", "regulator", "government", "third_party"},
        }.get(row["independence_class"])
        if expected_provenance is not None and provenance not in expected_provenance:
            raise EventLedgerError(
                f"{where}: independence_class conflicts with disclosure provenance"
            )
        evidence_by_event[event["event_id"]].append(row)

    for event_id, event in events.items():
        where = f"events:{event_id}"
        event_links = evidence_by_event.get(event_id, [])
        reviewed_links = [
            link for link in event_links
            if event_claims[link["event_claim_id"]]["review_status"] == "anchor_reviewed"
        ]
        if not reviewed_links:
            # Candidate events remain legal but are excluded from the radar.
            continue
        if event["lifecycle_stage"] in MATURE_COMMERCIAL_STAGES:
            supporting_disclosures = [
                disclosures[event_claims[link["event_claim_id"]]["disclosure_id"]]
                for link in reviewed_links
                if link["relationship"] in {"reports", "supports"}
            ]
            if event["event_status"] in {"asserted", "corroborated"} and not supporting_disclosures:
                raise EventLedgerError(f"{where}: mature commercial stage lacks supporting report")
            if supporting_disclosures and all(item["disclosure_type"] == "technical_blog" for item in supporting_disclosures):
                raise EventLedgerError(f"{where}: technical blog alone cannot support mature commercial stage")
        if event["event_status"] == "corroborated":
            first_party_origins = {
                link["origin_group"] for link in reviewed_links
                if link["independence_class"] in {"first_party", "same_origin"}
                and link["relationship"] in {"reports", "supports"}
            }
            independent = {
                link["origin_group"] for link in reviewed_links
                if link["relationship"] in {"reports", "supports"}
                and link["independence_class"] in INDEPENDENT_CLASSES
                and link["origin_group"] not in first_party_origins
            }
            if not first_party_origins:
                raise EventLedgerError(f"{where}: corroborated event lacks first-party asserted origin")
            if not independent:
                raise EventLedgerError(f"{where}: corroborated event lacks independent supporting origin")

    return {
        "entities": entities,
        "universe": universe,
        "watch_entities": watch,
        "disclosures": disclosures,
        "event_claims": event_claims,
        "events": events,
        "evidence": evidence,
        "themes": themes,
    }


def derive_event_projection(facts: dict) -> dict:
    """Derive deterministic radar, timeline, theme, queue and coverage views."""
    disclosures = facts["disclosures"]
    claims = facts["event_claims"]
    events = facts["events"]
    evidence = facts["evidence"]

    evidence_by_event: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in evidence.values():
        evidence_by_event[row["event_id"]].append(row)

    radar: list[dict] = []
    queue: list[dict] = []
    for event_id in sorted(events):
        event = events[event_id]
        links = sorted(evidence_by_event.get(event_id, []), key=lambda row: row["evidence_id"])
        unique_links: list[dict[str, str]] = []
        seen_origins: set[str] = set()
        for link in links:
            if link["origin_group"] in seen_origins:
                continue
            seen_origins.add(link["origin_group"])
            unique_links.append(link)
        reviewed = [
            link for link in unique_links
            if claims[link["event_claim_id"]]["review_status"] == "anchor_reviewed"
        ]
        if not reviewed:
            queue.append({
                "queue_type": "event_pending_anchor_review",
                "event_id": event_id,
                "summary": event["summary"],
            })
            continue

        evidence_rows = []
        for link in reviewed:
            claim = claims[link["event_claim_id"]]
            disclosure = disclosures[claim["disclosure_id"]]
            evidence_rows.append({
                "evidence_id": link["evidence_id"],
                "event_claim_id": claim["event_claim_id"],
                "relationship": link["relationship"],
                "independence_class": link["independence_class"],
                "origin_group": link["origin_group"],
                "statement_kind": claim["statement_kind"],
                "quote": claim["quote"],
                "anchor": claim["anchor"],
                "claim_reviewed_at": claim["reviewed_at"],
                "disclosure_id": disclosure["disclosure_id"],
                "title": disclosure["title"],
                "url": disclosure["canonical_url"],
                "disclosure_type": disclosure["disclosure_type"],
                "content_class": disclosure["content_class"],
                "provenance_class": disclosure["provenance_class"],
                "published_at": disclosure["published_at"],
                "retrieved_at": disclosure["retrieved_at"],
                "disclosure_reviewed_at": disclosure["reviewed_at"],
            })
        row = {
            "event_id": event_id,
            "program_id": event["program_id"],
            "event_category": event["event_category"],
            "lifecycle_stage": event["lifecycle_stage"],
            "event_status": event["event_status"],
            "primary_subject_id": event["primary_subject_id"],
            "counterparty_ids": _split_ids(event["counterparty_ids"]),
            "theme_ids": _split_ids(event["theme_ids"]),
            "occurred_start": event["occurred_start"],
            "occurred_end": event["occurred_end"],
            "date_precision": event["date_precision"],
            "previous_event_id": event["previous_event_id"],
            "summary": event["summary"],
            "evidence": evidence_rows,
        }
        radar.append(row)

    for disclosure_id in sorted(disclosures):
        disclosure = disclosures[disclosure_id]
        if disclosure["processing_status"] in {"unprocessed", "candidate_extracted"}:
            queue.append({
                "queue_type": "disclosure_processing",
                "disclosure_id": disclosure_id,
                "processing_status": disclosure["processing_status"],
                "title": disclosure["title"],
            })

    timelines: dict[str, list[dict]] = defaultdict(list)
    theme_impacts: dict[str, list[dict]] = defaultdict(list)
    for row in radar:
        timelines[row["primary_subject_id"]].append(row)
        for theme_id in row["theme_ids"]:
            theme_impacts[theme_id].append(row)
    timeline_rows = [
        {"primary_subject_id": entity_id, "events": sorted(items, key=lambda item: (item["occurred_start"], item["event_id"]))}
        for entity_id, items in sorted(timelines.items())
    ]
    theme_rows = [
        {"theme_id": theme_id, "events": sorted(items, key=lambda item: (item["occurred_start"], item["event_id"]))}
        for theme_id, items in sorted(theme_impacts.items())
    ]

    status_counts: dict[str, int] = defaultdict(int)
    for row in disclosures.values():
        status_counts[row["processing_status"]] += 1
    published = [row["published_at"] for row in disclosures.values() if row["published_at"]]
    retrieved = [row["retrieved_at"] for row in disclosures.values() if row["retrieved_at"]]
    reviewed = [row["reviewed_at"] for row in disclosures.values() if row["reviewed_at"]]
    coverage = {
        "disclosure_count": len(disclosures),
        "processing_status_counts": dict(sorted(status_counts.items())),
        "latest_disclosure_at": max(published) if published else "",
        "latest_retrieved_at": max(retrieved) if retrieved else "",
        "latest_reviewed_at": max(reviewed) if reviewed else "",
    }
    return {
        "radar_events": radar,
        "company_timelines": timeline_rows,
        "theme_impacts": theme_rows,
        "discovery_queue": sorted(queue, key=lambda item: (item["queue_type"], item.get("event_id", ""), item.get("disclosure_id", ""))),
        "coverage_summary": coverage,
    }
