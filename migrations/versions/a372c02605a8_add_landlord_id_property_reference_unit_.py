"""Add landlord_id and property reference

Revision ID: a372c02605a8
Revises: a3fdf8444886
Create Date: 2026-01-17
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a372c02605a8'
down_revision = 'a3fdf8444886'
branch_labels = None
depends_on = None


def upgrade():
    # =========================
    # PROPERTY TABLE
    # =========================
    with op.batch_alter_table('property', schema=None) as batch_op:
        # add landlord_id as nullable first
        batch_op.add_column(
            sa.Column('landlord_id', sa.Integer(), nullable=True)
        )

        # add property reference
        batch_op.add_column(
            sa.Column('reference', sa.String(length=50), nullable=True)
        )

        # adjust name length if needed
        batch_op.alter_column(
            'name',
            existing_type=sa.VARCHAR(length=120),
            type_=sa.String(length=150),
            existing_nullable=False
        )

    # backfill landlord_id (ensure user id 1 exists)
    op.execute(
        "UPDATE property SET landlord_id = 1 WHERE landlord_id IS NULL"
    )

    # backfill reference for existing rows
    op.execute(
        "UPDATE property SET reference = 'PR-' || id WHERE reference IS NULL"
    )

    # enforce constraints
    with op.batch_alter_table('property', schema=None) as batch_op:
        batch_op.alter_column(
            'landlord_id',
            existing_type=sa.Integer(),
            nullable=False
        )

        batch_op.create_unique_constraint(
            'uq_property_reference',
            ['reference']
        )

        batch_op.create_foreign_key(
            'fk_property_landlord',
            'user',
            ['landlord_id'],
            ['id']
        )


def downgrade():
    with op.batch_alter_table('property', schema=None) as batch_op:
        batch_op.drop_constraint('fk_property_landlord', type_='foreignkey')
        batch_op.drop_constraint('uq_property_reference', type_='unique')
        batch_op.drop_column('reference')
        batch_op.drop_column('landlord_id')
