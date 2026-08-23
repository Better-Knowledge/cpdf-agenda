.PHONY: dev-db migrate migrate-canal test test-agenda test-canal test-agente test-mcp lint openapi credencial credenciais migrar-chaves revogar mcp-dev mcp-atendimento up down

dev-db:            ## sobe Postgres local de desenvolvimento
	docker compose --profile dev up -d db

migrate:           ## aplica migrations do agenda-service
	cd agenda-service && uv run alembic upgrade head

migrate-canal:     ## aplica migrations do canal-service
	cd canal-service && uv run alembic upgrade head

test: test-agenda test-canal test-agente test-mcp

test-agenda:
	cd agenda-service && uv run pytest -q

test-canal:
	cd canal-service && uv run pytest -q

test-agente:       ## agente do inbound — roda sem banco
	cd agente-service && uv run pytest -q

test-mcp:          ## conectores MCP (atendimento e administrativo) — sem banco
	cd agenda-admin-mcp && uv run pytest -q
	cd agenda-mcp && uv run pytest -q

lint:
	cd agenda-service && uv run ruff check app tests
	cd canal-service && uv run ruff check app tests
	cd agente-service && uv run ruff check app tests
	cd agenda-admin-mcp && uv run ruff check app tests
	cd agenda-mcp && uv run ruff check app tests

openapi:           ## exporta o contrato para docs/openapi.json (RF-17)
	cd agenda-service && uv run python scripts/exportar_openapi.py

credencial:        ## emite credencial de agente: make credencial ORG=<uuid> NOME="Bot" PAPEL=atendimento
	cd agenda-service && uv run python -m app.admin_cli emitir "$(ORG)" "$(NOME)" "$(PAPEL)"

credenciais:       ## lista as credenciais de uma org: make credenciais ORG=<uuid>
	cd agenda-service && uv run python -m app.admin_cli listar "$(ORG)"

migrar-chaves:     ## move AGENT_API_KEYS do .env para agent_credentials (preserva o valor)
	cd agenda-service && uv run python -m app.admin_cli importar-env

revogar:           ## revoga uma credencial: make revogar ID=<uuid>
	cd agenda-service && uv run python -m app.admin_cli revogar "$(ID)"

mcp-dev:           ## conector administrativo em http://127.0.0.1:8100/mcp
	cd agenda-admin-mcp && APP_ENV=dev uv run uvicorn app.main:app --port 8100

mcp-atendimento:   ## conector de atendimento em http://127.0.0.1:8101/mcp
	cd agenda-mcp && APP_ENV=dev uv run uvicorn app.main:app --port 8101

web-dev:           ## UI em modo dev (proxy para a API local)
	cd web && npm install && npm run dev

web-build:
	cd web && npm install && npm run build

up:                ## produção no VPS
	docker compose up -d --build

down:
	docker compose down
