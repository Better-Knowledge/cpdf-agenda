"""RF-14: a oferta da fila precisa lembrar QUAL slot foi oferecido.

Sem isso o aceite teria de adivinhar o horário a partir da janela desejada
("quinta à tarde" não é um horário). As colunas guardam o slot exato e o
recurso que a mensagem ofereceu — o aceite agenda aquilo, ou nada. O recurso
precisa ser gravado porque a maioria das entradas na fila não exige um
profissional específico: sem isso, a oferta expirada não saberia para qual
agenda voltar a chamar.

Não é reserva: o slot continua livre na grade durante a janela de aceite
(RF-14 é explícito sobre não haver hold). A coluna só registra a proposta.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-23
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table waitlist add column slot_ofertado tstzrange")
    op.execute(
        "alter table waitlist add column resource_ofertado uuid references resources(id)"
    )
    # Índice para o job de expiração: varre só o que está de fato ofertado.
    op.execute(
        "create index waitlist_ofertas_abertas on waitlist (expira_em) "
        "where status = 'ofertado'"
    )


def downgrade() -> None:
    op.execute("drop index if exists waitlist_ofertas_abertas")
    op.execute("alter table waitlist drop column if exists resource_ofertado")
    op.execute("alter table waitlist drop column if exists slot_ofertado")
