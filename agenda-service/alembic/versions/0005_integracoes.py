# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Integrações da etapa 8: entrega de eventos por consumidor e Calendly.

Duas tabelas novas.

**`event_deliveries`** — o `domain_events` é o barramento do programa
(`00` §4.4) e vai ter mais de um consumidor: o push do Google (RF-12) hoje,
o espelho de tarefas (RF-07) depois. Marcar `domain_events.processed_at`
faria o primeiro consumidor a passar roubar o evento dos outros. O estado de
entrega é, portanto, **por consumidor** — outbox com um cursor cada.
Sem `org_id`: a linha não é dado de negócio, é contabilidade de entrega, e
só o worker a lê.

**`calendly_links`** — o webhook do Calendly (RF-16) chega numa URL pública,
sem sessão: é a chave de assinatura guardada aqui que diz de qual
organização é aquele evento, e para qual serviço/recurso importar. Cifrada,
como todo segredo de terceiro.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-23
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

SCHEMA = """
create table event_deliveries (
  event_id     bigint not null references domain_events(id) on delete cascade,
  consumer     text not null,            -- ex.: google-calendar, tasks-service
  processed_at timestamptz,
  attempts     int not null default 0,
  last_error   text,
  primary key (event_id, consumer)
);

-- O caminho quente do worker: "o que ainda falta entregar para este consumidor".
create index event_deliveries_pendentes on event_deliveries (consumer, event_id)
  where processed_at is null;

create table calendly_links (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null,
  service_id     uuid not null references services(id),
  resource_id    uuid not null references resources(id),
  segredo        jsonb not null,          -- chave de assinatura do webhook, cifrada
  cria_lembretes boolean not null default false,  -- o Calendly já manda os dele
  ativo          boolean not null default true,
  created_at     timestamptz not null default now(),
  constraint um_calendly_por_org unique (org_id)
);

-- Idempotência do webhook: o Calendly reenvia o mesmo evento em caso de falha.
create index appointments_external_ref on appointments (external_ref)
  where external_ref is not null;
"""


def upgrade() -> None:
    op.execute(SCHEMA)

    op.execute("alter table calendly_links enable row level security")
    op.execute("alter table calendly_links force row level security")
    op.execute(
        """
        create policy calendly_links_org_isolation on calendly_links
          for all
          using ((select app.is_worker()) or org_id = (select app.current_org_id()))
          with check ((select app.is_worker()) or org_id = (select app.current_org_id()))
        """
    )

    # event_deliveries não tem org_id — a política é "só o worker", que é o
    # único que a lê. Uma requisição de usuário nunca enxerga esta tabela.
    op.execute("alter table event_deliveries enable row level security")
    op.execute("alter table event_deliveries force row level security")
    op.execute(
        """
        create policy event_deliveries_worker on event_deliveries
          for all
          using ((select app.is_worker()))
          with check ((select app.is_worker()))
        """
    )


def downgrade() -> None:
    op.execute("drop index if exists appointments_external_ref")
    op.execute("drop table if exists calendly_links, event_deliveries cascade")
