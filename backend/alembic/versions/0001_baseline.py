"""Establish the migration baseline; domain tables are introduced in T02.

Alembic creates and stamps its version table on an empty PostgreSQL database.
No synthetic product, user, or catalog table is created in this stage.
"""

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
