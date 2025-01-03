"""empty message

Revision ID: 0f52a6b45f68
Revises: 90672a07361b
Create Date: 2024-11-30 07:58:23.893957

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0f52a6b45f68'
down_revision = '90672a07361b'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('major_city', sa.String(length=100), nullable=False),
    sa.Column('suburb', sa.String(length=100), nullable=False),
    sa.Column('multiplier', sa.Float(), nullable=True),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('start_hour', sa.Integer(), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('radius', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.drop_table('events')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('events',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('user_id', sa.INTEGER(), nullable=False),
    sa.Column('major_city', sa.VARCHAR(length=100), nullable=False),
    sa.Column('suburb', sa.VARCHAR(length=100), nullable=False),
    sa.Column('multiplier', sa.FLOAT(), nullable=False),
    sa.Column('date', sa.DATE(), nullable=False),
    sa.Column('hour', sa.INTEGER(), nullable=False),
    sa.Column('created_at', sa.DATETIME(), nullable=True),
    sa.Column('latitude', sa.FLOAT(), nullable=False),
    sa.Column('longitude', sa.FLOAT(), nullable=False),
    sa.Column('radius', sa.FLOAT(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('date', 'hour', name='unique_date_hour')
    )
    op.drop_table('event')
    # ### end Alembic commands ###
