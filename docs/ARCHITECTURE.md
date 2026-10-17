# FieldSense Architecture

Modular monolith for the FlytBase Asset Intelligence Copilot challenge.

![Asset Intelligence Copilot architecture](./assets/architecture.png)

## Runtime

- `web` — React/Vite SPA (nginx) on `:5173`
- `api` — FastAPI on `:8000`
- `worker` — Postgres job/outbox consumer
- `db` — PostgreSQL 16 + pgvector image

## Request path

1. Demo user selected → server session / `X-User-Id`
2. Chat run → deterministic intent router (+ optional LLM later)
3. Typed analytics/compliance/feedback services
4. Effective-inspection layer applies formal corrections
5. Answer envelope with visuals bound to result rows + evidence items

## Domain invariants

- Production from ΔT vs manual thresholds (T200 15°C, T350 20°C)
- Downtime = 7 × non-producing inspections in window
- Eval answer sheets never indexed
- Private memory filtered by owner before retrieval

See `docs/decisions/` and `.plans/` for detailed contracts.
