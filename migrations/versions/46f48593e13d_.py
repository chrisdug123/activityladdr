"""empty message

Revision ID: 46f48593e13d
Revises: 1136b512bc89
Create Date: 2024-12-11 19:49:32.831597

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '46f48593e13d'
down_revision = '1136b512bc89'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('strava_refresh_token', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('strava_expires_at', sa.Integer(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('strava_expires_at')
        batch_op.drop_column('strava_refresh_token')

    # ### end Alembic commands ###
