"""Single-clinic normalized baseline."""

import sqlalchemy as sa
from alembic import op
from app.shared.infrastructure.models import Base

revision = "0001_single_clinic"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        # The baseline predates ``context_json``.  Creating this table from the
        # current ORM model would leak the column into revision 0001 and make
        # revision 0002 fail with DuplicateColumn on a clean database.
        if table.name == "chat_sessions":
            op.create_table(
                "chat_sessions",
                sa.Column("id", sa.String(length=36), nullable=False),
                sa.Column("patient_id", sa.String(length=36), nullable=True),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
                sa.ForeignKeyConstraint(["patient_id"], ["users.id"]),
                sa.PrimaryKeyConstraint("id"),
            )
            continue
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
