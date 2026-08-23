# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""A migration 0004 normaliza endereços já gravados — e precisa mesmo rodar.

O risco específico aqui é a migration passar em silêncio: `appointments` e
`waitlist` têm RLS `force`, que vale até para o dono do banco, então sem
suspender a política o UPDATE não veria linha nenhuma, terminaria com sucesso
e deixaria os endereços como estavam. O teste grava linhas torta antes do
upgrade e confere depois.
"""

import uuid

from .conftest import integracao

pytestmark = integracao

ORG = uuid.UUID("3f6e0000-0000-4000-8000-0000000000aa")
TORTOS = [
    ("+55 11 99876-5432", "+5511998765432"),
    ("(11) 98888-7777", "+11988887777"),
    ("TG: 123456789", "tg:123456789"),
    ("+5511900000000", "+5511900000000"),  # já canônico: não deve mudar
]


def _semear(conn, tabela: str, extra_colunas: str, extra_valores: str):
    from sqlalchemy import text

    conn.execute(text(f"alter table {tabela} no force row level security"))
    conn.execute(text(f"alter table {tabela} disable row level security"))
    for i, (bruto, _) in enumerate(TORTOS):
        conn.execute(
            text(
                f"insert into {tabela} (org_id, cliente_nome, cliente_telefone{extra_colunas}) "
                f"values (:org, :nome, :tel{extra_valores})"
            ),
            {"org": ORG, "nome": f"Cliente {i}", "tel": bruto, "i": i},
        )
    conn.execute(text(f"alter table {tabela} enable row level security"))
    conn.execute(text(f"alter table {tabela} force row level security"))


def test_backfill_normaliza_apesar_do_rls_force(banco_migrado):
    from alembic.config import Config
    from sqlalchemy import text

    from alembic import command
    from app.sessao import engine

    cfg = Config("alembic.ini")
    command.downgrade(cfg, "0003")

    servico, recurso = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as conn:
        # services/resources são tabelas de negócio normais: a RLS por org vale,
        # e o seed precisa se identificar. As duas tabelas do backfill é que
        # ganham a suspensão, dentro de `_semear`.
        conn.execute(text("select set_config('app.org_id', :org, true)"), {"org": str(ORG)})
        conn.execute(
            text(
                "insert into services (id, org_id, nome, duracao_min, preco) "
                "values (:id, :org, 'Corte', 60, 80)"
            ),
            {"id": servico, "org": ORG},
        )
        conn.execute(
            text("insert into resources (id, org_id, nome, tipo) values (:id, :org, 'Sala', 'sala')"),
            {"id": recurso, "org": ORG},
        )
        _semear(
            conn,
            "appointments",
            ", service_id, resource_id, periodo",
            f", '{servico}', '{recurso}', tstzrange(now() + (:i * interval '1 day'), "
            "now() + (:i * interval '1 day') + interval '1 hour')",
        )
        _semear(
            conn,
            "waitlist",
            ", service_id, janela_desejada",
            f", '{servico}', tstzrange(now(), now() + interval '6 hours')",
        )

    command.upgrade(cfg, "head")

    with engine.begin() as conn:
        for tabela in ("appointments", "waitlist"):
            conn.execute(text(f"alter table {tabela} no force row level security"))
            gravados = sorted(
                r[0]
                for r in conn.execute(
                    text(f"select cliente_telefone from {tabela} where org_id = :org"), {"org": ORG}
                )
            )
            conn.execute(text(f"alter table {tabela} force row level security"))
            assert gravados == sorted(esperado for _, esperado in TORTOS), tabela
