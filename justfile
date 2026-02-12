default: check

install:
    poetry install

check: lint test

fmt:
    poetry run black src/ tests/

lint:
    poetry run black --check src/ tests/
    poetry run ruff check src/ tests/

test:
    poetry run pytest

clean:
    rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache
    find . -type d -name __pycache__ -exec rm -rf {} +
