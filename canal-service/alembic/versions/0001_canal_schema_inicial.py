# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Schema inicial do canal-service (PRD §10 — contrato em `00` §4.8).

RLS por org em todas as tabelas (o canal incluído — PRD §13). As funções
app.current_org_id()/app.is_worker() são compartilhadas com o agenda-service
quando os dois usam o mesmo banco — por isso `create or replace`.

Revision ID: 0001
Revises:
Create Date: 2026-08-22
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TABELAS_RLS = ["channel_configs", "channel_templates", "channel_messages", "channel_optouts"]

SCHEMA = """
create schema if not exists app;

create or replace function app.current_org_id() returns uuid
language plpgsql stable as $$
declare v text;
begin
  v := nullif(current_setting('app.org_id', true), '');
  if v is null then
    begin
      v := nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'org_id';
    exception when others then
      v := null;
    end;
  end if;
  return v::uuid;
end $$;

create or replace function app.is_worker() returns boolean
language sql stable as $$
  select current_setting('app.role', true) = 'worker'
$$;

create table channel_configs (        -- driver é configuração por org
  org_id uuid primary key,
  driver text not null constraint driver_valido check (driver in ('evolution','zapi','meta')),
  credenciais jsonb not null,         -- cifrado na aplicação; write-only na API
  numero text not null,               -- número dedicado (nunca o pessoal)
  instancia text not null,            -- roteia o webhook inbound até a org
  webhook_token text not null,        -- segredo do webhook inbound (PRD §9)
  ativo boolean not null default true,
  constraint instancia_unica_por_driver unique (driver, instancia)
);

create table channel_templates (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  nome text not null,
  corpo text not null,                -- com {{variaveis}}
  versao int not null default 1,
  aprovado_meta boolean not null default false,
  ativo boolean not null default true,
  constraint template_versionado unique (org_id, nome, versao)
);

create table channel_messages (
  id bigserial primary key,
  org_id uuid not null,
  direcao text not null constraint direcao_valida check (direcao in ('saida','entrada')),
  telefone text not null,
  tipo text constraint tipo_valido check (tipo in ('sessao','template')),
  template_id uuid,
  corpo_renderizado text,
  driver text not null,
  driver_message_id text,
  status text not null default 'pendente' constraint status_valido
    check (status in ('pendente','enviada','entregue','lida','falha')),
  custo numeric(10,4),
  erro text,
  idempotency_key text,
  created_at timestamptz not null default now(),
  constraint inbound_idempotente unique (driver, driver_message_id)
);

create table channel_optouts (
  org_id uuid not null,
  telefone text not null,
  origem text,                        -- palavra_chave|pedido_humano
  em timestamptz not null default now(),
  primary key (org_id, telefone)
);

create index channel_messages_conversa_idx
  on channel_messages (org_id, telefone, created_at desc);
create index channel_messages_idem_idx
  on channel_messages (org_id, idempotency_key) where idempotency_key is not null;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    for tabela in TABELAS_RLS:
        op.execute(f"alter table {tabela} enable row level security")
        op.execute(f"alter table {tabela} force row level security")
        op.execute(
            f"""
            create policy {tabela}_org_isolation on {tabela}
              for all
              using ((select app.is_worker())
                     or org_id = (select app.current_org_id()))
              with check ((select app.is_worker())
                          or org_id = (select app.current_org_id()))
            """
        )


def downgrade() -> None:
    op.execute(
        """
        drop table if exists channel_optouts, channel_messages, channel_templates,
          channel_configs cascade;
        """
    )
