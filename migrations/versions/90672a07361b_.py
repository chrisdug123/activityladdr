"""empty message

Revision ID: 90672a07361b
Revises: 32c8262e5349
Create Date: 2024-11-30 06:42:27.657570

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '90672a07361b'
down_revision = '32c8262e5349'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('latitude', sa.Float(), nullable=False))
        batch_op.add_column(sa.Column('longitude', sa.Float(), nullable=False))
        batch_op.add_column(sa.Column('radius', sa.Float(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_column('radius')
        batch_op.drop_column('longitude')
        batch_op.drop_column('latitude')

    # ### end Alembic commands ###
