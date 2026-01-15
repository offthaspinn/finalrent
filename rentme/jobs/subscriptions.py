from datetime import datetime
from rentme.extensions import db
from rentme.models import Subscription

def expire_subscriptions():
    Subscription.query.filter(
        Subscription.is_active == True,
        Subscription.expires_at < datetime.utcnow()
    ).update({"is_active": False})

    db.session.commit()
