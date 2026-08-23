.PHONY: dev-db migrate migrate-canal test test-agenda test-canal lint up down

dev-db:            ## sobe Postgres local de desenvolvimento
	docker compose --profile dev up -d db

migrate:           ## aplica migrations do agenda-service
	cd agenda-service && uv run alembic upgrade head

migrate-canal:     ## aplica migrations do canal-service
	cd canal-service && uv run alembic upgrade head

test: test-agenda test-canal

test-agenda:
	cd agenda-service && uv run pytest -q

test-canal:
	cd canal-service && uv run pytest -q

lint:
	cd agenda-service && uv run ruff check app tests
	cd canal-service && uv run ruff check app tests

web-dev:           ## UI em modo dev (proxy para a API local)
	cd web && npm install && npm run dev

web-build:
	cd web && npm install && npm run build

up:                ## produção no VPS
	docker compose up -d --build

down:
	docker compose down
