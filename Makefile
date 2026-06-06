# PolicyIQ Makefile
# Common development commands. Run `make` (or `make help`) to list targets.

.PHONY: help lint format test test-all pre-commit-install pre-commit-run clean

help:
	@echo "PolicyIQ development targets:"
	@echo "  make lint          - Run ruff lint checks"
	@echo "  make format        - Auto-format with ruff"
	@echo "  make test          - Run Django test suite"
	@echo "  make test-all      - Run Django + pytest suites"
	@echo "  make pre-commit-install - Install pre-commit git hooks"
	@echo "  make pre-commit-run - Run all pre-commit hooks on every file"
	@echo "  make clean         - Remove Python build artifacts"

lint:
	python -m ruff check policyiq/

format:
	python -m ruff format policyiq/

test:
	cd policyiq && python manage.py test

test-all:
	cd policyiq && python manage.py test
	python -m pytest

pre-commit-install:
	pre-commit install

pre-commit-run:
	pre-commit run --all-files

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete
