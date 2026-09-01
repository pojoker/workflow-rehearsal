# Research graph closure pilot — GPT Pro review brief

## Review objective

Please review whether this branch establishes a sound minimal seam between the
repository's existing ledgers and a future “question graph + typed relation
graph” closed loop. This is deliberately not a UI or a complete question graph.

Base branch: `codex/industry-chain-v2`
Review branch: `codex/research-graph-closure-pilot`

## What the branch implements

1. A five-type relation registry and legacy-adapter contract.
2. A strict distinction between Relation Slot and immutable Relation Assertion.
3. A disposable, deterministic assertion index and slot-state projection.
4. One diagnostic question-generation rule:

   ```text
   capability_matches_route exists
   + exact company_serves_route slot is not satisfied
   → candidate diagnostic question
   ```

5. Resolution transitions for exact reviewed support, withdrawal and conflict.
6. Frozen route-profile IDs so question text and relation target cannot drift
   between DR4 and DR8.

## Architectural invariants to verify

- `points.csv`, `route_bom.csv` and `calls/*.csv` remain sources of truth.
- `out/*.jsonl` files are projections, never canonical facts.
- `route_bom × points` can only emit `capability_matches_route` with
  `epistemic_status: derived_candidate`.
- Only explicit reviewed assertions can emit `company_serves_route`.
- KN co-reference and component evidence cannot close a service question.
- Assertions preserve scope, valid time, modality, polarity, epistemic status,
  origin group and adapter version.
- Same-origin duplicates do not increase independent-evidence count.
- Historical support, limits, contradictions and withdrawals coexist rather
  than being overwritten by one status field.

## Known limitation that should be challenged

The current 83 questions are 83 object instances of one rule, not 83 distinct
research-question forms.

The trigger is also weaker than its prose: one matching capability cell is
enough to generate a question, while the template says the company “具备路线所需能力”.
That wording may incorrectly imply complete route capability. A likely correction
is to expose matched and unmatched capability cells and say “在该路线所需的若干能力格中已有记录”.

Please assess whether the trigger should be:

- any matching capability cell;
- a configured minimum or required subset;
- an explicit capability-coverage object;
- or different rules for component vendor, module vendor and system vendor.

## High-value review questions

1. Is the slot identity sufficiently scoped, especially for valid time and
   modality, or are those fields incorrectly kept only on assertions?
2. Is withdrawal-by-reference adequate, including correction and supersession?
3. Should conflict be computed only within an identical slot, or through a
   relation-type-specific contradiction key?
4. Is `company_serves_route` too broad and should it split demonstration,
   product listing, qualification, shipment and deployment?
5. Is the frozen route profile a valid identity contract, given that its
   requirement rows come from a broader legacy route framework?
6. Can generated candidates remain stable when adapters or entity aliases
   change?
7. What is the smallest safe interface for candidate → formalized question and
   research result → reviewed assertion?

## Review entry points

- `docs/plans/2026-09-research-graph-closure-pilot.md`
- `contracts/relation_types.yaml`
- `contracts/relation_adapters.yaml`
- `contracts/question_generation_rules.yaml`
- `tools/research/build_relation_index.py`
- `tools/research/recompute_question_state.py`
- `tests/research/test_relation_graph_closure.py`
- `docs/research/relation-closure-pilot-report-2026-09-01.md`

## Reproduction

Use a Python environment with PyYAML installed:

```bash
python tools/research/build_relation_index.py
python tools/research/recompute_question_state.py
python -m unittest tests.research.test_relation_graph_closure -v
python scan.py --check
python -m calls check
```

Expected current-data result:

- 564 assertions;
- 505 relation slots;
- 83 candidate questions, all open;
- zero canonical or explicit `company_serves_route` assertions.
