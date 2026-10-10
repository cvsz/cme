SHELL := /bin/sh
PYTHON ?= python3
API_DIR := apps/api
VENV := $(API_DIR)/.venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff

.PHONY: help validate-template setup format lint test build security ci run-api

help:
	@printf '%s\n' 'CMe: setup format lint test build security ci run-api' 'Repository: validate-template'

validate-template:
	$(PYTHON) scripts/validate_repo.py
	$(PYTHON) -m unittest discover -s tests -v

setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e '$(API_DIR)[dev]'

format:
	$(RUFF) format --check $(API_DIR)

lint:
	$(RUFF) check $(API_DIR)

test:
	cd $(API_DIR) && .venv/bin/pytest

build:
	$(PYTHON) -m compileall -q $(API_DIR)/cme_api

security:
	@echo "Scanning tracked source files for potential secrets..."
	@if git grep -n -I -E -e 'AKIA[0-9A-Z]{16}' -e '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----' -- apps .env.example; then \
		echo "ERROR: Potential secret detected"; \
		exit 1; \
	else \
		echo "Tracked-source secret scan passed"; \
	fi

ci: validate-template lint test build security

run-api:
	cd $(API_DIR) && .venv/bin/uvicorn cme_api.main:app --host 127.0.0.1 --port 8000 --reload
