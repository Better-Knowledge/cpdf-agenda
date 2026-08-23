"""Endereço do cliente numa forma canônica só (RF-19).

Antes do isolamento por titular, a forma de `cliente_telefone` era cosmética:
ninguém comparava dois endereços. Agora ela decide acesso — `_carregar`
compara o endereço gravado com o titular assinado pelo canal, e é isso que
faz o cliente enxergar (ou não) o próprio horário.

O modo de falha sem este backfill é o pior possível: **silencioso e do lado
errado**. `+55 11 99876-5432`, digitado pela UI, nunca casa com o
`+5511998765432` que o driver produz — o cliente pergunta pelo próprio
horário e o agente responde, com toda a confiança, que não há nada no nome
dele. Ninguém abre chamado de "não vazou"; abre-se de "sumiu meu horário".

A regra é a de `app/enderecos.py`, escrita em SQL: endereço com esquema
(`tg:123`) mantém o esquema em minúsculas e perde os espaços; o resto vira
E.164 (`+` mais os dígitos). Idempotente — rodar de novo não muda nada.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-23
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TABELAS = ("appointments", "waitlist")

# Regex do esquema: `tg:`, `mail:` — um prefixo declarado não é telefone.
TEM_ESQUEMA = r"^[a-zA-Z][a-zA-Z0-9+.-]*:"

NORMALIZA_ESQUEMA = """
update {tabela}
   set cliente_telefone =
         lower(substring(cliente_telefone from '^[a-zA-Z][a-zA-Z0-9+.-]*')) || ':' ||
         btrim(substring(cliente_telefone from position(':' in cliente_telefone) + 1))
 where cliente_telefone ~ '{esquema}'
"""

# Só toca em linhas que realmente mudam: `where` estreito evita reescrever a
# tabela inteira (e o WAL junto) num backfill que costuma não ter o que fazer.
NORMALIZA_E164 = r"""
update {tabela}
   set cliente_telefone = '+' || regexp_replace(cliente_telefone, '\D', '', 'g')
 where cliente_telefone !~ '{esquema}'
   and cliente_telefone ~ '\d'
   and cliente_telefone <> '+' || regexp_replace(cliente_telefone, '\D', '', 'g')
"""


def _suspender_rls(tabela: str) -> None:
    """Backfill precisa ver todas as organizações; a RLS é `force`, o que vale
    até para o dono do banco. Sem suspender, o UPDATE não veria linha nenhuma e
    a migration passaria em silêncio sem normalizar nada — de novo, a falha
    silenciosa. Suspende pelo tempo do UPDATE e devolve como estava."""
    op.execute(f"alter table {tabela} no force row level security")
    op.execute(f"alter table {tabela} disable row level security")


def _restaurar_rls(tabela: str) -> None:
    op.execute(f"alter table {tabela} enable row level security")
    op.execute(f"alter table {tabela} force row level security")


def upgrade() -> None:
    for tabela in TABELAS:
        _suspender_rls(tabela)
        try:
            op.execute(NORMALIZA_ESQUEMA.format(tabela=tabela, esquema=TEM_ESQUEMA))
            op.execute(NORMALIZA_E164.format(tabela=tabela, esquema=TEM_ESQUEMA))
        finally:
            _restaurar_rls(tabela)

    # A fila passou a ser consultada por titular (GET /waitlist numa sessão de
    # atendimento). O índice de appointments para isso já existe desde 0001.
    op.execute(
        "create index if not exists waitlist_org_telefone_idx "
        "on waitlist (org_id, cliente_telefone)"
    )


def downgrade() -> None:
    op.execute("drop index if exists waitlist_org_telefone_idx")
    # A normalização não tem volta: a forma original de cada endereço não foi
    # guardada, e inventar uma seria pior do que manter a canônica. O downgrade
    # devolve o schema — os dados ficam normalizados, o que nenhuma versão
    # anterior estranha, porque nenhuma comparava endereços.
