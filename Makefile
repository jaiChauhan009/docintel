.PHONY: help up down logs build test lint migrate revision seed fmt shell-api

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

up: ## Start the whole stack
	docker compose up --build

down: ## Stop and remove containers
	docker compose down

down-v: ## Stop and wipe volumes
	docker compose down -v

logs: ## Tail api + worker logs
	docker compose logs -f api worker

build: ## Build images
	docker compose build

test: ## Run the test suite (sqlite, no infra needed)
	.venv/bin/python -m pytest

migrate: ## Apply migrations locally (needs a reachable Postgres / DATABASE_URL)
	.venv/bin/alembic upgrade head

revision: ## Autogenerate a migration: make revision m="add x"
	.venv/bin/alembic revision --autogenerate -m "$(m)"

seed: ## Seed the running API with demo data
	.venv/bin/python scripts/seed.py

shell-api: ## Shell into the running api container
	docker compose exec api bash
