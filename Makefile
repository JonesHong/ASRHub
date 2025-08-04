.PHONY: help install install-dev test test-cov lint format type-check clean run docs

# Default target
help:
	@echo "ASR Hub Development Commands"
	@echo "==========================="
	@echo "install      - Install production dependencies"
	@echo "install-dev  - Install development dependencies"
	@echo "test         - Run tests"
	@echo "test-cov     - Run tests with coverage"
	@echo "lint         - Run code linting"
	@echo "format       - Format code with black"
	@echo "type-check   - Run mypy type checking"
	@echo "clean        - Clean build artifacts"
	@echo "run          - Run the application"
	@echo "docs         - Build documentation"
	@echo "yaml2py      - Generate config classes from YAML"

# Install production dependencies
install:
	pip install -r requirements.txt
	pip install -e .

# Install development dependencies
install-dev:
	pip install -r requirements.txt
	pip install -e ".[dev]"
	pre-commit install

# Run tests
test:
	pytest tests/ -v

# Run tests with coverage
test-cov:
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term

# Run linting
lint:
	flake8 src/ tests/
	black --check src/ tests/
	isort --check-only src/ tests/

# Format code
format:
	black src/ tests/
	isort src/ tests/

# Type checking
type-check:
	mypy src/

# Clean build artifacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	rm -rf build/ dist/

# Run the application
run:
	python -m src.core.asr_hub

# Build documentation
docs:
	mkdocs build

# Serve documentation locally
docs-serve:
	mkdocs serve

# Generate config classes from YAML
yaml2py:
	yaml2py --config config/base.yaml --output ./src/config

# Create sample config from base.yaml
sample-config:
	@if [ -f config/base.yaml ]; then \
		cp config/base.yaml config/base.sample.yaml; \
		echo "Created config/base.sample.yaml from config/base.yaml"; \
	else \
		echo "Error: config/base.yaml not found"; \
		exit 1; \
	fi

# Full CI pipeline
ci: lint type-check test

# Development setup
dev-setup: install-dev yaml2py
	@echo "Development environment is ready!"

# Check if all requirements are met
check-env:
	@python --version
	@pip --version
	@echo "Virtual environment: $$VIRTUAL_ENV"
	@which yaml2py || echo "Warning: yaml2py not installed"
	@which pretty-loguru || echo "Warning: pretty-loguru not installed"