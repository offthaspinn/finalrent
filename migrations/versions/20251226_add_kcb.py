"""Add KCB columns to landlord_settings and drop old kcb_credential table"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251226_add_kcb_to_landlord_settings'
down_revision = None  # replace with your previous migration ID if any
branch_labels = None
depends_on = None

def upgrade():
    # Add KCB columns to landlord_settings
    op.add_column('landlord_settings', sa.Column('kcb_api_key', sa.String(length=255), nullable=True))
    op.add_column('landlord_settings', sa.Column('kcb_paybill', sa.String(length=32), nullable=True))
    op.add_column('landlord_settings', sa.Column('kcb_env', sa.String(length=20), nullable=False, server_default='sandbox'))
    op.add_column('landlord_settings', sa.Column('kcb_callback_url', sa.String(length=512), nullable=True))

    # Drop old kcb_credential table if it exists
    op.execute('DROP TABLE IF EXISTS kcb_credential')


def downgrade():
    # Recreate old kcb_credential table
    op.create_table(
        'kcb_credential',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, nullable=False),
        sa.Column('paybill_number', sa.String(length=50), nullable=True),
        sa.Column('account_type', sa.String(length=20), nullable=True),
        sa.Column('callback_url', sa.String(length=500), nullable=True),
        sa.Column('kcb_env', sa.String(length=20), nullable=True),
        sa.Column('encrypted_api_key', sa.LargeBinary, nullable=True),
        sa.Column('encrypted_api_secret', sa.LargeBinary, nullable=True),
    )
    # Remove KCB columns from landlord_settings
    op.drop_column('landlord_settings', 'kcb_api_key')
    op.drop_column('landlord_settings', 'kcb_paybill')
    op.drop_column('landlord_settings', 'kcb_env')
    op.drop_column('landlord_settings', 'kcb_callback_url')
