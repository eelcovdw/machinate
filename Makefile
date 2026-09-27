.PHONY: setup lint test

setup:
	uv sync

lint:
	uv run ruff check
	uv run ruff format --check
	uv run basedpyright

test:
	uv run pytest
