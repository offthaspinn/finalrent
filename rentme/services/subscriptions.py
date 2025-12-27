from datetime import datetime, timedelta
from rentme.extensions import db
from rentme.models import Subscription


def activate_subscription(user_id: int, plan_id: int):
    """
    Deactivate any existing subscription and activate a new one
    for 30 days.
    """

    Subscription.query.filter_by(user_id=user_id, is_active=True).update(
        {"is_active": False}
    )

    sub = Subscription(
        user_id=user_id,
        plan_id=plan_id,
        started_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=30),
        is_active=True,
    )

    db.session.add(sub)
    db.session.commit()

    return sub
