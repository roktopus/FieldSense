# ADR 0001 — Stack

## Status
Accepted

## Decision
Modular monolith: FastAPI + PostgreSQL 16/pgvector + React/Vite/Tailwind.
Compose services: `db`, `api`, `worker`, `web`.
One orchestrator agent; typed tools; deterministic analytics in Python/SQL.

## Consequences
No Kubernetes, graph DB, Redis requirement, or multi-agent fleet for the Hack Day build.
