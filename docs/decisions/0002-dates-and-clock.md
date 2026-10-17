# ADR 0002 — Dates and analysis clock

## Status
Accepted

## Decision
- Injectable `EVALUATION_AS_OF` (default `2026-10-16T00:00:00Z` — Dataset Guide "today").
- Explicit question ranges override relative windows.
- Date-only inclusive ends normalize to exclusive next-day UTC.
- Q6 uses explicit `2026-06-16` … `2026-10-16` regardless of clock.

## Consequences
Relative phrases resolve against the clock; tests set clock per scenario.
