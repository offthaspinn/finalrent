from datetime import datetime
from functools import wraps

from flask import redirect, url_for, flash, request, current_app
from flask_login import current_user

from rentme.extensions import db
from rentme.models import Subscription


def get_active_subscription(user):
    if not user or not user.is_authenticated:
        return None

    sub = (
        Subscription.query
        .filter_by(user_id=user.id)
        .order_by(Subscription.created_at.desc())
        .first()
    )

    if not sub:
        return None

    now = datetime.utcnow()

    if sub.expires_at >= now:
        return sub

    if sub.grace_expires_at and sub.grace_expires_at >= now:
        sub.is_grace = True
        db.session.commit()
        return sub

    sub.is_active = False
    sub.is_grace = False
    db.session.commit()
    return None


def subscription_required(f):
    """
    Blocks access if user has no active subscription.
    Safe for webhook/payment flow and prevents redirect loops.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):

        # Must be logged in
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))

        # Allow subscription/payment routes to pass through
        if request.endpoint and request.endpoint.startswith("subscriptions."):
            return f(*args, **kwargs)

        sub = get_active_subscription(current_user)

        if not sub:
            current_app.logger.info(
                "subscription_required: blocked user=%s (no active subscription)",
                current_user.email,
            )
            flash(
                "🚫 Your subscription is inactive or expired. Please subscribe to continue.",
                "warning",
            )
            return redirect(url_for("subscriptions.list_plans"))

        return f(*args, **kwargs)

    return wrapper
