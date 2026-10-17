# Dataset profiles: sample (200 wells, today 2026-10-16) or test (600 wells, today 2027-01-15)
DATASET_PROFILE ?= sample

ifeq ($(DATASET_PROFILE),test)
DATASET_HOST_PATH ?= /Users/vpix/asset inteligence/flytbase-ahc-swe-asset-intelligence-dataset/test-data/dataset
EVALUATION_AS_OF ?= 2027-01-15T00:00:00Z
DATASET_VERSION ?= test-v1
else
DATASET_HOST_PATH ?= /Users/vpix/asset inteligence/flytbase-ahc-swe-asset-intelligence-dataset/sample-data
EVALUATION_AS_OF ?= 2026-10-16T00:00:00Z
DATASET_VERSION ?= sample-v1
endif

export DATASET_HOST_PATH
export EVALUATION_AS_OF
export DATASET_PROFILE

.PHONY: up down build migrate import-data logs test-domain test-api evaluate harness-final harness-sample dev doctor profile-env

profile-env:
	@echo "DATASET_PROFILE=$(DATASET_PROFILE)"
	@echo "DATASET_HOST_PATH=$(DATASET_HOST_PATH)"
	@echo "EVALUATION_AS_OF=$(EVALUATION_AS_OF)"
	@echo "DATASET_VERSION=$(DATASET_VERSION)"

up:
	@test -f .env || (echo "Missing .env — run: cp .env.example .env" && exit 1)
	DATASET_HOST_PATH="$(DATASET_HOST_PATH)" EVALUATION_AS_OF="$(EVALUATION_AS_OF)" DATASET_PROFILE="$(DATASET_PROFILE)" \
		docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

migrate:
	docker compose exec api python -m app.ingestion.cli migrate

import-data:
	docker compose exec api python -m app.ingestion.cli run --path /data/sample-data --dataset-version $(DATASET_VERSION)

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
	docker compose exec -u root -e DATASET_PROFILE=sample api sh -c "pip install -q '.[dev]' && pytest tests/evaluation -q"

harness-final:
	docker compose exec -u root -e DATASET_PROFILE=test api sh -c "pip install -q '.[dev]' && pytest tests/harness -q"

harness-sample:
	docker compose exec -u root -e DATASET_PROFILE=sample api sh -c "pip install -q '.[dev]' && pytest tests/evaluation -q"

dev:
	docker compose up --build
