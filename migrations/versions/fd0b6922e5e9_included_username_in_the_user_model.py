"""Included username in the user model

Revision ID: fd0b6922e5e9
Revises: 46f48593e13d
Create Date: 2024-12-16 20:15:13.984088

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fd0b6922e5e9'
down_revision = '46f48593e13d'
branch_labels = None
depends_on = None


def upgrade():
    # Add the username column to the users table
    op.add_column('users', sa.Column('username', sa.String(length=50), nullable=True))
    
    # Add a unique constraint with a name
    op.create_unique_constraint('uq_users_username', 'users', ['username'])

    # Set default values for existing users
    op.execute('UPDATE users SET username = email')  # Example fallback: use email as username

    # Make the column non-nullable
    op.alter_column('users', 'username', nullable=False)

def downgrade():
    # Remove the unique constraint by its name
    op.drop_constraint('uq_users_username', 'users', type_='unique')
    op.drop_column('users', 'username')
