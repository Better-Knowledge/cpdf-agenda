"""Schema inicial do agenda-service (PRD §10).

Invariantes que vivem AQUI, no banco — nunca só na aplicação:
- Zero double-booking: EXCLUDE USING gist (resource_id, periodo) em appointments.
- RLS em toda tabela de negócio: org_id = app.current_org_id().
  app.current_org_id() lê o GUC `app.org_id` (setado pela API a cada request)
  e cai para `request.jwt.claims ->> 'org_id'` — o mesmo claim que o
  `auth.jwt()` do Supabase lê, sem depender do schema `auth` (roda em
  Postgres puro nos testes).

Revision ID: 0001
Revises:
Create Date: 2026-08-22
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Toda tabela de negócio (multi-tenant) recebe RLS + política por org.
TABELAS_RLS = [
    "services",
    "resources",
    "service_resources",
    "availability_rules",
    "availability_blocks",
    "appointments",
    "appointment_history",
    "reminders",
    "ics_tokens",
    "google_calendar_links",
    "booking_links",
    "waitlist",
    "recurrence_series",
    "domain_events",
    "idempotency_keys",
]

SCHEMA = """
create extension if not exists btree_gist;

create schema if not exists app;

-- Fonte do org da requisição, nas duas topologias (API própria e PostgREST).
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

-- Caminho de serviço para jobs (lembretes, reconciliação): o worker roda no
-- backend e precisa varrer todas as orgs. O GUC só é setável por quem tem a
-- conexão — ou seja, o próprio backend; clientes autenticados via JWT nunca
-- controlam GUCs. Equivalente ao service_role do Supabase, explícito.
create or replace function app.is_worker() returns boolean
language sql stable as $$
  select current_setting('app.role', true) = 'worker'
$$;

create table services (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  nome text not null,
  duracao_min int not null constraint duracao_positiva check (duracao_min > 0),
  preco numeric(14,2) not null default 0,
  buffer_antes_min int not null default 0,
  buffer_depois_min int not null default 0,
  ativo boolean not null default true,
  created_at timestamptz not null default now()
);

create table resources (              -- profissional, sala, equipamento
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  nome text not null,
  tipo text,
  ativo boolean not null default true
);

create table service_resources (
  service_id uuid not null references services(id),
  resource_id uuid not null references resources(id),
  primary key (service_id, resource_id)
);

create table availability_rules (     -- grade semanal (dia_semana: 0=segunda … 6=domingo)
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  resource_id uuid not null references resources(id),
  dia_semana int not null constraint dia_semana_valido check (dia_semana between 0 and 6),
  hora_inicio time not null,
  hora_fim time not null,
  constraint janela_valida check (hora_fim > hora_inicio)
);

create table availability_blocks (    -- férias, feriado, almoço
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  resource_id uuid not null references resources(id),
  periodo tstzrange not null,
  motivo text
);

create table recurrence_series (      -- RF-15: recorrência simples
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  service_id uuid not null references services(id),
  resource_id uuid not null references resources(id),
  frequencia text not null constraint frequencia_valida
    check (frequencia in ('semanal','quinzenal')),
  dia_semana int not null constraint dia_semana_serie_valido
    check (dia_semana between 0 and 6),
  hora_inicio time not null,
  fim_em date,
  ocorrencias int,
  ativo boolean not null default true,
  created_at timestamptz not null default now()
);

create table appointments (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  service_id uuid not null references services(id),
  resource_id uuid not null references resources(id),
  company_id uuid,
  contact_id uuid,
  cliente_nome text not null,
  cliente_telefone text not null,
  periodo tstzrange not null,
  status text not null default 'agendado' constraint status_valido
    check (status in ('agendado','confirmado','cancelado','realizado','no_show')),
  risco_no_show text,
  risco_detalhe jsonb,
  origem text not null default 'agente',
  observacoes text,
  task_id uuid,
  series_id uuid references recurrence_series(id),
  google_event_id text,
  external_ref text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- RF-04: double-booking impossível no banco
  constraint sem_double_booking exclude using gist (
    resource_id with =,
    periodo with &&
  ) where (status in ('agendado','confirmado'))
);

create table appointment_history (
  id bigserial primary key,
  appointment_id uuid not null references appointments(id),
  acao text not null,
  de tstzrange,
  para tstzrange,
  origem text,
  motivo text,
  por uuid,
  em timestamptz not null default now()
);

create table reminders (
  id bigserial primary key,
  org_id uuid not null,
  appointment_id uuid not null references appointments(id),
  tipo text not null,
  agendado_para timestamptz not null,
  enviado_em timestamptz,
  canal_message_id bigint,
  tentativas int not null default 0,
  erro text,
  constraint lembrete_unico unique (appointment_id, tipo)
);

create table ics_tokens (             -- RF-11
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  resource_id uuid references resources(id),
  token text not null unique,
  modo text not null default 'completo',
  revogado_em timestamptz,
  created_at timestamptz not null default now()
);

create table google_calendar_links (  -- RF-12
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  resource_id uuid not null references resources(id),
  calendar_id text not null,
  credenciais jsonb not null,         -- tokens OAuth cifrados; write-only na API
  ativo boolean not null default true,
  revogado_em timestamptz,
  created_at timestamptz not null default now(),
  constraint um_link_por_recurso unique (org_id, resource_id)
);

create table booking_links (          -- RF-13
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  service_id uuid not null references services(id),
  resource_id uuid references resources(id),
  slug text not null unique,
  exige_caucao boolean not null default false,
  valor_caucao numeric(14,2),
  ativo boolean not null default true,
  created_at timestamptz not null default now()
);

create table waitlist (               -- RF-14
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  service_id uuid not null references services(id),
  resource_id uuid references resources(id),
  cliente_nome text not null,
  cliente_telefone text not null,
  janela_desejada tstzrange not null,
  status text not null default 'aguardando' constraint status_fila_valido
    check (status in ('aguardando','ofertado','aceito','expirado','cancelado')),
  ofertado_em timestamptz,
  expira_em timestamptz,
  created_at timestamptz not null default now()
);

create table domain_events (          -- barramento do programa (00 §4.4)
  id bigserial primary key,
  org_id uuid not null,
  event_type text not null,
  payload jsonb not null,
  occurred_at timestamptz not null default now(),
  processed_at timestamptz,
  attempts int not null default 0,
  last_error text
);

create table idempotency_keys (
  org_id uuid not null,
  chave text not null,
  endpoint text not null,
  resposta jsonb not null,
  status_code int not null default 200,
  created_at timestamptz not null default now(),
  primary key (org_id, chave, endpoint)
);

-- updated_at automático
create or replace function app.tg_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

create trigger appointments_updated_at
  before update on appointments
  for each row execute function app.tg_updated_at();

-- Índices (PRD §10)
create index appointments_org_resource_idx on appointments (org_id, resource_id);
create index appointments_periodo_gist on appointments using gist (periodo);
create index appointments_org_telefone_idx on appointments (org_id, cliente_telefone);
create index appointments_series_idx on appointments (series_id) where series_id is not null;
create index appointments_external_ref_idx on appointments (external_ref)
  where external_ref is not null;
create index reminders_pendentes_idx on reminders (agendado_para) where enviado_em is null;
create index waitlist_ativa_idx on waitlist (org_id, status)
  where status in ('aguardando','ofertado');
create index domain_events_pendentes_idx on domain_events (occurred_at)
  where processed_at is null;
create index availability_rules_resource_idx on availability_rules (resource_id);
create index availability_blocks_resource_idx on availability_blocks (resource_id);
create index appointment_history_appointment_idx on appointment_history (appointment_id);
-- índices das colunas usadas nas políticas RLS
create index services_org_idx on services (org_id);
create index resources_org_idx on resources (org_id);
"""


def upgrade() -> None:
    op.execute(SCHEMA)

    # RLS em toda tabela de negócio — última linha de defesa entre orgs.
    # A função fica embrulhada em (select …) para ser avaliada uma vez por
    # query, não por linha (recomendação Supabase de performance de RLS).
    for tabela in TABELAS_RLS:
        if tabela in ("service_resources", "appointment_history"):
            # tabelas sem org_id próprio: restringe via pai
            continue
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

    op.execute(
        """
        alter table service_resources enable row level security;
        alter table service_resources force row level security;
        create policy service_resources_org_isolation on service_resources
          for all
          using ((select app.is_worker())
                 or exists (select 1 from services s
                            where s.id = service_id
                              and s.org_id = (select app.current_org_id())));

        alter table appointment_history enable row level security;
        alter table appointment_history force row level security;
        create policy appointment_history_org_isolation on appointment_history
          for all
          using ((select app.is_worker())
                 or exists (select 1 from appointments a
                            where a.id = appointment_id
                              and a.org_id = (select app.current_org_id())));
        """
    )


def downgrade() -> None:
    op.execute(
        """
        drop table if exists idempotency_keys, domain_events, waitlist, booking_links,
          google_calendar_links, ics_tokens, reminders, appointment_history,
          appointments, recurrence_series, availability_blocks, availability_rules,
          service_resources, resources, services cascade;
        drop function if exists app.tg_updated_at();
        drop function if exists app.is_worker();
        drop function if exists app.current_org_id();
        """
    )
