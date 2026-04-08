"""recovered missing revision placeholder

Revision ID: 20260307_0006
Revises: 20260306_0005
Create Date: 2026-03-07 00:06:00
"""

# Esta migración se agrega para recuperar consistencia del historial en entornos
# donde la revisión 20260307_0006 ya fue aplicada.

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260307_0006"
down_revision = "20260306_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Placeholder intencional: no cambios de esquema.
    pass


def downgrade() -> None:
    # Placeholder intencional: no cambios de esquema.
    pass
