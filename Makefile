.PHONY: setup dev api web worker infra-up infra-down seed test test-api test-web lint build validate openapi demo

setup:
	python3 -m venv .venv
	.venv/bin/pip install -e '.[dev]'
	npm install

infra-up:
	docker compose -f infra/docker-compose.yml up -d --build

infra-down:
	docker compose -f infra/docker-compose.yml down

api:
	PYTHONPATH=apps/api uvicorn app.main:app --reload --port 8000

worker:
	PYTHONPATH=apps/api:apps/worker celery -A worker.celery_app worker --loglevel=INFO

web:
	npm run dev

seed:
	PYTHONPATH=apps/api python3 datasets/seed.py

test-api:
	pytest apps/api/tests tests/integration

test-web:
	npm run test:web

test: test-api test-web

lint:
	ruff check apps/api apps/worker datasets tests
	npm run lint

build:
	npm run build

openapi:
	PYTHONPATH=apps/api python3 packages/contracts/generate.py

validate:
	./scripts/validate.sh

demo:
	docker compose -f infra/docker-compose.yml up --build

