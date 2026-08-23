# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Telegram entra como driver do canal.

A regra "driver é configuração" vive no banco: a constraint enumera os
drivers aceitos, então incluir um novo canal é uma migration — barata e
reversível, sem tocar em nenhuma linha de lógica dos módulos.

**Atenção no downgrade:** reverter tira 'telegram' da lista de drivers
aceitos, então as configurações de canal que usam Telegram são apagadas
(inclusive as credenciais cifradas). É o significado de reverter isto —
essas organizações precisam ser reconfiguradas em outro driver.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-23
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

DRIVERS_ANTES = "('evolution','zapi','meta')"
DRIVERS_DEPOIS = "('evolution','zapi','telegram','meta')"


def _trocar_constraint(drivers: str) -> None:
    op.execute("alter table channel_configs drop constraint driver_valido")
    op.execute(
        f"alter table channel_configs add constraint driver_valido check (driver in {drivers})"
    )


def upgrade() -> None:
    _trocar_constraint(DRIVERS_DEPOIS)


def downgrade() -> None:
    # channel_configs tem RLS FORCE (vale até para o dono da tabela): sem
    # app.org_id definido, o DELETE não veria linha nenhuma e a constraint
    # voltaria a falhar. Migration é manutenção de schema — suspende a política
    # pelo tempo da limpeza e devolve exatamente como 0001 deixou.
    op.execute("alter table channel_configs no force row level security")
    op.execute("alter table channel_configs disable row level security")
    op.execute("delete from channel_configs where driver = 'telegram'")
    op.execute("alter table channel_configs enable row level security")
    op.execute("alter table channel_configs force row level security")
    _trocar_constraint(DRIVERS_ANTES)
