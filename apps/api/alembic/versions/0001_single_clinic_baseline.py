"""Single-clinic normalized baseline."""

from alembic import op
from app.shared.infrastructure.models import Base

revision = "0001_single_clinic"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        table.create(bind=bind, checkfirst=False)
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        op.execute(
            """
            ALTER TABLE appointments
            ADD CONSTRAINT appointments_doctor_no_overlap
            EXCLUDE USING gist (
              doctor_id WITH =,
              tstzrange(starts_at, ends_at, '[)') WITH &&
            ) WHERE (status = 'confirmed')
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        table.drop(bind=bind, checkfirst=False)
