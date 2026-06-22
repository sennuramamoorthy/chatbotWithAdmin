.DEFAULT_GOAL := help

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
COMPOSE := docker compose

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- Python / tests ---------------------------------------------------------

$(VENV):
	python3 -m venv $(VENV)
	$(PIP) install -U pip

$(VENV)/.installed: pyproject.toml | $(VENV)
	$(PIP) install -e ".[dev]"
	@touch $@

.PHONY: install
install: $(VENV)/.installed ## Create venv + install package (editable) and dev deps

.PHONY: test
test: install ## Run the full test suite
	$(PY) -m pytest

.PHONY: test-unit
test-unit: install ## Run only the deterministic-core unit tests
	$(PY) -m pytest -m unit

.PHONY: cov
cov: install ## Run tests with a coverage report
	$(PY) -m pytest --cov=takshashila_chatbot --cov-report=term-missing

.PHONY: run
run: install ## Run the dev/demo API server (uvicorn, auto-reload)
	$(VENV)/bin/uvicorn takshashila_chatbot.api.main:app --reload --port 8000

.PHONY: run-prod
run-prod: ## Run with REAL adapters (needs DATABASE_URL + LLM_BASE_URL + psycopg + infra)
	$(VENV)/bin/uvicorn takshashila_chatbot.wiring:build_app_from_env --factory --port 8000

.PHONY: worker
worker: install ## Run the background worker (clustering + retention; needs env + infra)
	$(VENV)/bin/python -m takshashila_chatbot.worker

.PHONY: admin
admin: ## Build + serve the admin UI at http://localhost:5173 (run `make run` for the API)
	@[ -d admin/node_modules ] || npm --prefix admin install
	npm --prefix admin run build
	@echo "Admin UI  → http://localhost:5173/"
	@echo "API       → http://127.0.0.1:8000   (demo token: demo-admin-token)"
	python3 -m http.server -d admin 5173

# --- Local infra (docker compose) -------------------------------------------

.PHONY: up
up: ## Start Postgres+pgvector and Redis in the background
	$(COMPOSE) up -d

.PHONY: down
down: ## Stop infra (keeps data volumes)
	$(COMPOSE) down

.PHONY: restart
restart: down up ## Restart infra

.PHONY: logs
logs: ## Tail infra logs
	$(COMPOSE) logs -f

.PHONY: ps
ps: ## Show infra container status
	$(COMPOSE) ps

.PHONY: db-shell
db-shell: ## Open a psql shell in the Postgres container
	$(COMPOSE) exec postgres psql -U takshashila -d takshashila

.PHONY: redis-cli
redis-cli: ## Open a redis-cli shell in the Redis container
	$(COMPOSE) exec redis redis-cli

.PHONY: migrate
migrate: ## Apply db/schema.sql to the running Postgres (auto-applied on fresh `up`)
	$(COMPOSE) exec -T postgres psql -U takshashila -d takshashila < db/schema.sql

# --- Housekeeping -----------------------------------------------------------

.PHONY: clean
clean: ## Remove caches and coverage artifacts
	rm -rf .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

.PHONY: clean-all
clean-all: clean ## Also remove venv and infra volumes (DESTROYS local data)
	-$(COMPOSE) down -v
	rm -rf $(VENV)
