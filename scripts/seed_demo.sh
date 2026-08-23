#!/usr/bin/env bash
# Seed do protótipo — cria catálogo, grade, templates e agendamentos de
# exemplo usando SOMENTE a API pública (API-first até no seed).
# Uso: ./scripts/seed_demo.sh [base_url]   (padrão http://localhost:8100)
set -euo pipefail
cd "$(dirname "$0")/.."

BASE="${1:-http://localhost:8100}"
DEMO_KEY=$(grep '^AGENT_API_KEYS=' .env | sed 's/.*{"\([^"]*\)".*/\1/')
ORG_ID=$(grep '^AGENT_API_KEYS=' .env | sed 's/.*: "\([^"]*\)".*/\1/')
CANAL_KEY=$(grep '^CANAL_SERVICE_KEY=' .env | cut -d= -f2)

api() { # método rota [json]
  curl -sf -X "$1" "$BASE$2" \
    -H "X-Agent-Key: $DEMO_KEY" -H "Content-Type: application/json" \
    -H "Idempotency-Key: seed-$2-$3" -d "${4:-}"
}

echo "== Recursos"
SALA=$(api POST /resources sala '{"nome": "Sala 1", "tipo": "sala"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
PROF=$(api POST /resources prof '{"nome": "Dra. Ana", "tipo": "profissional"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

echo "== Serviços"
CORTE=$(api POST /services corte "{\"nome\": \"Corte\", \"duracao_min\": 60, \"preco\": \"80.00\", \"buffer_depois_min\": 10, \"resource_ids\": [\"$SALA\"]}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
CONSULTA=$(api POST /services consulta "{\"nome\": \"Consulta\", \"duracao_min\": 30, \"preco\": \"150.00\", \"resource_ids\": [\"$PROF\"]}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

echo "== Grade seg–sex 9h–18h"
for R in "$SALA" "$PROF"; do
  for DIA in 0 1 2 3 4; do
    api POST /availability/rules "r$R$DIA" "{\"resource_id\": \"$R\", \"dia_semana\": $DIA, \"hora_inicio\": \"09:00\", \"hora_fim\": \"18:00\"}" > /dev/null
  done
done

echo "== Agendamentos de exemplo (próxima quinta)"
QUINTA=$(python3 -c "
from datetime import date, timedelta
d = date.today()
d += timedelta(days=(3 - d.weekday()) % 7 or 7)
print(d.isoformat())")
api POST /appointments a1 "{\"service_id\": \"$CORTE\", \"inicio\": \"${QUINTA}T10:00:00-03:00\", \"cliente_nome\": \"João Souza\", \"cliente_telefone\": \"+5511999990001\", \"origem\": \"humano\"}" > /dev/null
api POST /appointments a2 "{\"service_id\": \"$CONSULTA\", \"inicio\": \"${QUINTA}T14:00:00-03:00\", \"cliente_nome\": \"Maria Lima\", \"cliente_telefone\": \"+5511999990002\", \"origem\": \"humano\"}" > /dev/null

echo "== Templates sementes do canal (RF-10)"
docker compose exec -T -e CANAL_KEY="$CANAL_KEY" -e ORG_ID="$ORG_ID" canal-service uv run python - <<'PY'
import os
import httpx

TEMPLATES = {
    "confirmacao": "Olá {{nome}}! Seu horário de {{servico}} está confirmado para {{data_hora}}. Responda SAIR para não receber mensagens.",
    "lembrete_24h": "Oi {{nome}}! Lembrete: {{servico}} amanhã, {{data_hora}}. Responda 'confirmo' para confirmar. SAIR para não receber mensagens.",
    "lembrete_2h": "Oi {{nome}}! Seu {{servico}} é daqui a pouco, {{data_hora}}. Até já!",
    "reagendamento": "Olá {{nome}}! Seu {{servico}} foi remarcado para {{data_hora}}. Qualquer dúvida, é só responder.",
    "cancelamento": "Olá {{nome}}, seu {{servico}} de {{data_hora}} foi cancelado. Se quiser remarcar, é só responder aqui.",
    "aviso_cobranca": "Olá {{nome}}! Consta um pagamento em aberto de {{servico}}. Podemos conversar sobre isso? Responda SAIR para não receber mensagens.",
    # RF-14: o texto PRECISA dizer que não há reserva — a fila não promete o
    # que o produto não segura.
    "fila_oferta": "Oi {{nome}}! Vagou um horário de {{servico}}: {{data_hora}}. Responda 'quero' em até {{minutos}} minutos. Atenção: o horário não fica reservado — quem confirmar primeiro leva. SAIR para não receber mensagens.",
    "risco_alto": "Oi {{nome}}! Confirma mesmo o seu {{servico}} de {{data_hora}}? Responda 'confirmo' para garantir. Se não puder vir, é só avisar que liberamos para outra pessoa.",
}
headers = {"X-Service-Key": os.environ["CANAL_KEY"], "X-Org-Id": os.environ["ORG_ID"]}
for nome, corpo in TEMPLATES.items():
    r = httpx.post(
        "http://localhost:8000/canal/templates",
        json={"nome": nome, "corpo": corpo, "aprovado_meta": False},
        headers=headers,
    )
    print(nome, r.status_code)
PY

echo
echo "Seed concluído. Org: $ORG_ID"
echo "Explore: $BASE/docs  (X-Agent-Key: $DEMO_KEY)"
