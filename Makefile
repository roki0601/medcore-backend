SHELL := /bin/bash

UV ?= uv
PYTHON := $(UV) run python

.PHONY: install up compose-up compose-down compose-migrate compose-logs migrate \
        makemigrations makemigrations-check check lint format test shell \
        pre-commit-install pre-commit ci

install:
	$(UV) sync

up:
	$(PYTHON) manage.py runserver 127.0.0.1:8000

compose-up:
	docker compose up -d

compose-down:
	docker compose down

compose-migrate:
	docker compose run --rm migrate

compose-logs:
	docker compose logs -f web

migrate:
	$(PYTHON) manage.py migrate

makemigrations:
	$(PYTHON) manage.py makemigrations

makemigrations-check:
	$(PYTHON) manage.py makemigrations --check --dry-run

check:
	$(PYTHON) manage.py check

lint:
	$(UV) run ruff check .

format:
	$(UV) run ruff format .

test:
	$(UV) run pytest

shell:
	$(PYTHON) manage.py shell

pre-commit-install:
	$(UV) run pre-commit install

pre-commit:
	$(UV) run pre-commit run --all-files

ci: check makemigrations-check lint format test
