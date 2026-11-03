.PHONY: setup backend frontend test lint

setup:
	cd backend && uv sync
	cd frontend && npm install

backend:
	cd backend && uv run python -m ew_core

frontend:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -q
	cd frontend && npm test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run typecheck
