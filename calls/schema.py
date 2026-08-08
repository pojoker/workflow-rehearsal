"""CSV contracts and controlled vocabularies for the calls intelligence layer."""

FILES = {
    "universe.csv": (
        "company_id", "company_name", "role", "inclusion_reason", "enabled",
    ),
    "sources.csv": (
        "source_id", "company_id", "slot_label", "period_end", "source_scope",
        "material_type", "source_grade", "url", "local_path", "published_date",
        "accessed_date", "availability", "missing_reason", "acquisition_note",
    ),
    "claims.csv": (
        "claim_id", "source_id", "speaker", "speaker_role", "statement_type",
        "event_type", "side", "theme_id", "quote", "anchor", "review_status",
        "mapping_track", "cell_id", "route_item_id", "unmapped_theme",
        "unmapped_reason", "summary",
    ),
    "themes.csv": (
        "theme_id", "theme_type", "theme_name", "parent_theme_id",
        "affected_dimension", "bottleneck_status", "mapping_track", "cell_id",
        "route_item_id", "unmapped_reason", "application_demand", "required_metric",
        "critical_node", "limiting_factor", "constrained_outcome", "candidate_solution",
        "progress_gap", "feasibility", "scarcity", "substitutability",
    ),
    "validations.csv": (
        "validation_id", "theme_id", "claim_a_id", "claim_b_id", "relationship",
        "result_status", "rationale",
    ),
    "commitments.csv": (
        "commitment_id", "claim_id", "target", "due_date", "status",
        "evidence_source_id", "evidence_claim_id", "assessment",
    ),
    "solution_links.csv": (
        "link_id", "bottleneck_theme_id", "solution_theme_id", "required_capability",
        "point_id", "match_stage", "evidence_status", "missing_evidence", "conclusion",
    ),
    "constraint_requirements.csv": (
        "requirement_id", "theme_id", "cell_id", "route_item_id", "dimension",
        "metric_name", "comparator", "target_value", "unit", "evidence_claim_ids",
        "review_status", "notes",
    ),
    "point_metrics.csv": (
        "metric_id", "point_id", "metric_name", "value", "unit", "as_of",
        "review_status", "notes",
    ),
    "technology_feedback.csv": (
        "feedback_id", "technology_claim_id", "commercial_claim_id", "theme_id",
        "feedback_status", "evidence_status", "stage_before", "stage_after", "rationale",
    ),
}

ENUMS = {
    "role": {"core_peer", "downstream"},
    "enabled": {"yes", "no"},
    "source_scope": {"quarterly", "interquarter"},
    "material_type": {"unknown", "transcript", "prepared_remarks", "earnings_presentation", "webcast_transcript", "earnings_release", "official_release", "official_technical_blog"},
    "source_grade": {"unknown", "A", "B", "C"},
    "availability": {"available", "not_collected", "unavailable"},
    "speaker_role": {"management", "analyst", "operator", "corporate_author"},
    "statement_type": {"fact", "forward_looking", "analyst_question", "technical_claim", "technical_demo"},
    "event_type": {"unknown", "announced", "sampling", "qualifying", "volume_order", "first_shipment", "ramping", "scaled", "demonstrated", "delayed", "withdrawn"},
    "side": {"supply", "demand", "both", "unknown"},
    "review_status": {"candidate", "reviewed", "rejected"},
    "mapping_track": {"canonical", "unmapped"},
    "theme_type": {"limited_demand", "bottleneck", "solution", "topic"},
    "affected_dimension": {"performance", "power_thermal", "cost", "yield_capacity", "reliability_operations", "standards_compatibility_certification", "unknown"},
    "bottleneck_status": {"candidate", "binding", "solution_emerging", "partially_relieved", "industry_resolved", "shifted", "not_applicable"},
    "evidence_state": {"verified", "partially_supported", "company_claim_only", "conflicting", "insufficient"},
    "relationship": {"supports", "contradicts", "independent", "same_source", "insufficient"},
    "commitment_status": {"pending", "fulfilled", "partially_fulfilled", "delayed", "withdrawn", "not_observed"},
    "match_stage": {"node_overlap", "mechanism_match", "metric_match", "customer_validation", "volume_validation"},
    "feedback_status": {"confirmed", "partially_confirmed", "not_mentioned", "contradicted", "pending"},
}

PANORAMA_FIELDS = (
    "theme_id", "theme_type", "theme_name", "cell_id", "route_item_id",
    "bottleneck_status", "feasibility", "scarcity", "substitutability",
    "demand_evidence", "supply_evidence", "company_progress", "canonical_point_ids",
    "missing_evidence", "source_ids", "as_of",
)

CANONICAL_FILES = (
    "tree.yaml", "knowledge.yaml", "points.csv", "edges.csv", "route_bom.csv",
    "capability_details.csv", "corpus/_frozen.csv",
)
