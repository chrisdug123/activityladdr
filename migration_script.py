"""Add major_city column to events table

Revision ID: abc123def456
Revises: previous_revision_id
Create Date: YYYY-MM-DD HH:MM:SS

"""
from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision = 'abc123def456'
down_revision = 'previous_revision_id'
branch_labels = None
depends_on = None


def upgrade():
    # Delete all rows from the events table
    op.execute('DELETE FROM events')

    # Add the column with NOT NULL constraint
    op.add_column('events', sa.Column('major_city', sa.String(length=100), nullable=False))


def downgrade():
    # Drop the column if downgrading
    op.drop_column('events', 'major_city')
