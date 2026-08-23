"""Credenciais de agente com escopo, auditoria, e titular na idempotência.

Por que em tabela e não em variável de ambiente: escopo por credencial só é
útil se o administrador puder emitir e **revogar** sem redeploy, e a auditoria
(`00` §5.8) precisa de um `client_id` estável para responder "quem fez isso".

`agent_credentials` é lida em dois modos:
- **worker**, na autenticação — o lookup é por hash do token e acontece ANTES
  de sabermos a org (é o token que revela a org);
- **por org**, na tela de gestão.

Uma política só cobre os dois, porque `app.is_worker()` já está no `using`.
`force` é obrigatório: a aplicação roda como dona do banco e, sem ele, o dono
ignora a própria política.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-23
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABELAS = ("agent_credentials", "agent_audit_log")

SCHEMA = """
create table agent_credentials (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null,
  nome          text not null,
  papel         text not null constraint papel_valido
                  check (papel in ('atendimento','operacao','administrativo')),
  escopos       text[] not null,
  token_hash    text not null unique,   -- sha256 do token; o claro nunca é gravado
  prefixo       text not null,          -- só para a UI identificar a linha
  ativo         boolean not null default true,
  criada_em     timestamptz not null default now(),
  ultimo_uso_em timestamptz,
  revogada_em   timestamptz
);

-- O lookup de autenticação é sempre por hash; este índice é o caminho quente.
create index agent_credentials_ativas on agent_credentials (token_hash)
  where ativo and revogada_em is null;
create index agent_credentials_org on agent_credentials (org_id);

create table agent_audit_log (
  id             bigserial primary key,
  org_id         uuid not null,
  mcp_server     text not null,
  tool_name      text not null,
  client_id      uuid,
  actor          text,
  titular        text,                  -- em nome de qual cliente o agente agiu
  args_hash      text,                  -- hash dos argumentos, nunca o valor cru
  resultado      text not null constraint resultado_valido
                   check (resultado in ('ok','erro','recusado')),
  error_code     text,
  latencia_ms    int,
  confirmado_por uuid,
  created_at     timestamptz not null default now()
);

create index agent_audit_log_org_data on agent_audit_log (org_id, created_at desc);

-- Titular entra na chave de idempotência. Sem ele, um replay de
-- Idempotency-Key devolve o corpo gravado por outro cliente: `idem.buscar`
-- roda ANTES das guardas de propriedade nos handlers, então a checagem nunca
-- é alcançada. '' = credencial sem titular (operação/administrativo).
alter table idempotency_keys add column titular text not null default '';
alter table idempotency_keys drop constraint idempotency_keys_pkey;
alter table idempotency_keys add primary key (org_id, chave, endpoint, titular);
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    for tabela in TABELAS:
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
    op.execute("drop table if exists agent_audit_log, agent_credentials cascade")
    # Ordem importa: a PK antiga não admite a mesma (org, chave, endpoint) para
    # titulares diferentes. Chave de idempotência é cache de resposta — as
    # linhas por titular são descartáveis, e descartá-las é o que torna o
    # downgrade possível.
    #
    # A RLS de idempotency_keys é `force`, o que vale até para o dono do banco:
    # sem app.org_id definido, o DELETE não veria linha nenhuma e a PK voltaria
    # quebrada. Migration é manutenção de schema — suspende a política pelo
    # tempo da limpeza e devolve exatamente como estava.
    op.execute("alter table idempotency_keys no force row level security")
    op.execute("alter table idempotency_keys disable row level security")
    op.execute("delete from idempotency_keys where titular <> ''")
    op.execute("alter table idempotency_keys enable row level security")
    op.execute("alter table idempotency_keys force row level security")
    op.execute("alter table idempotency_keys drop constraint idempotency_keys_pkey")
    op.execute("alter table idempotency_keys drop column if exists titular")
    op.execute("alter table idempotency_keys add primary key (org_id, chave, endpoint)")
