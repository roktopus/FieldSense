# ADR 0003 — Corrections and evidence

## Status
Accepted

## Decision
- Single effective-inspection layer applies formal corrections before all metrics.
- Originals are immutable; corrections are append-only with supersession.
- Informal notes/claims never auto-override measurements.
- Evidence documents are untrusted data; citations must resolve.
- Evaluation answer sheets are never indexed for retrieval.

## Consequences
UI may show `applied=true` and `conflict=true` simultaneously.
