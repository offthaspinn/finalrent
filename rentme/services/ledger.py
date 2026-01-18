from sqlalchemy import func
from rentme.extensions import db
from rentme.models import Payment


def get_landlord_ledger_summary(user_id):
    total_received = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(
            Payment.user_id == user_id,
            Payment.status == "CONFIRMED"
        )
        .scalar()
    )

    return {
        "total_received": total_received,
        "total_paid_out": 0,
        "owed": total_received
    }
