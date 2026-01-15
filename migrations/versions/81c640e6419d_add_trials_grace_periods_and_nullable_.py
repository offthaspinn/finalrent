"""add trials grace periods and nullable intent

Revision ID: 81c640e6419d
Revises: <PUT_PREVIOUS_REVISION_ID_HERE>
Create Date: 2026-01-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "81c640e6419d"
down_revision = "5598e5f7ee68"
branch_labels = None
depends_on = None


def upgrade():
    # -------------------------------------------------
    # Subscription enhancements (SAFE, additive only)
    # -------------------------------------------------

    op.add_column(
        "subscription",
        sa.Column("intent_id", sa.Integer(), nullable=True),
    )

    op.add_column(
        "subscription",
        sa.Column(
            "is_trial",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.add_column(
        "subscription",
        sa.Column(
            "is_grace",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.add_column(
        "subscription",
        sa.Column("grace_expires_at", sa.DateTime(), nullable=True),
    )

    op.create_unique_constraint(
        "uq_subscription_intent_id",
        "subscription",
        ["intent_id"],
    )


def downgrade():
    op.drop_constraint(
        "uq_subscription_intent_id",
        "subscription",
        type_="unique",
    )

    op.drop_column("subscription", "grace_expires_at")
    op.drop_column("subscription", "is_grace")
    op.drop_column("subscription", "is_trial")
    op.drop_column("subscription", "intent_id")
