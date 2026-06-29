.PHONY: help install dev test lint format clean run docker-build docker-run

help:
	@echo "Available commands:"
	@echo "  make install      - Install dependencies"
	@echo "  make dev         - Install development dependencies"
	@echo "  make test        - Run tests"
	@echo "  make lint        - Run linters"
	@echo "  make format      - Format code"
	@echo "  make clean       - Clean cache files"
	@echo "  make run         - Run development server"

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	pytest -v --cov=app

test-unit:
	pytest -v --cov=app tests/unit/

test-integration:
	pytest -v --cov=app tests/integration/

lint:
	ruff check .
	mypy .

format:
	ruff format .
	ruff check --fix .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	rm -rf .coverage htmlcov/

run:
	uvicorn app.web.__main__:app --reload --host 0.0.0.0 --port 8000

