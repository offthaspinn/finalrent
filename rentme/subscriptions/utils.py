from datetime import datetime
from functools import wraps

from flask import redirect, url_for, flash
from flask_login import current_user

from rentme.models import Subscription


def get_active_subscription(user):
    """
    Returns the user's active, non-expired subscription or None
    """
    if not user or not user.is_authenticated:
        return None

    return (
        Subscription.query
        .filter_by(user_id=user.id, is_active=True)
        .filter(Subscription.expires_at > datetime.utcnow())
        .first()
    )


def subscription_required(f):
    """
    Blocks access if user has no active subscription
    """
    @wraps(f)
    def wrapper(*args, **kwargs):

        # Safety: must be logged in
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))

        sub = get_active_subscription(current_user)

        if not sub:
            flash(
                "🚫 Your subscription is inactive or expired. Please subscribe to continue.",
                "warning",
            )
            return redirect(url_for("subscriptions.list_plans"))

        return f(*args, **kwargs)

    return wrapper
