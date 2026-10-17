DATASET_HOST_PATH ?= /Users/vpix/asset inteligence/flytbase-ahc-swe-asset-intelligence-dataset/sample-data
export DATASET_HOST_PATH

.PHONY: up down build migrate import-data logs test-domain test-api evaluate dev doctor

up:
	@test -f .env || (echo "Missing .env — run: cp .env.example .env" && exit 1)
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

migrate:
	docker compose exec api python -m app.ingestion.cli migrate

import-data:
	docker compose exec api python -m app.ingestion.cli run --path /data/sample-data --dataset-version sample-v1

logs:
	docker compose logs -f api worker web

doctor:
	@echo "Compose services:" && docker compose ps
	@curl -fsS http://localhost:8000/health/live && echo
	@curl -fsS -o /dev/null -w "web %{http_code}\n" http://localhost:5173/

test-domain:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" -q && .venv/bin/pytest tests/domain -q

test-api:
	docker compose exec -u root api sh -c "pip install -q '.[dev]' && pytest tests -q"

evaluate:
	docker compose exec -u root api sh -c "pip install -q '.[dev]' && pytest tests/evaluation -q"

dev:
	docker compose up --build
