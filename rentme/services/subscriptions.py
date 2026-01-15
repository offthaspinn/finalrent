from datetime import datetime, timedelta
from uuid import uuid4

from rentme.extensions import db
from rentme.models import Subscription, SubscriptionIntent, Plan


# ----------------------------------------------------
# INTERNAL: deactivate existing subscriptions
# ----------------------------------------------------
def _deactivate_existing(user_id):
    Subscription.query.filter_by(
        user_id=user_id,
        is_active=True
    ).update({
        "is_active": False,
        "expires_at": datetime.utcnow()
    })


# ----------------------------------------------------
# PAID SUBSCRIPTION (Webhook-driven)
# ----------------------------------------------------
def activate_paid_subscription(intent: SubscriptionIntent) -> Subscription | None:
    if intent.status == "COMPLETE":
        return None  # idempotent

    plan = intent.plan
    if not plan:
        return None

    _deactivate_existing(intent.user_id)

    subscription = Subscription(
        user_id=intent.user_id,
        plan_id=plan.id,
        intent_id=intent.id,
        plan_name=plan.name,
        properties_allowed=plan.max_properties,
        amount_paid=intent.amount,
        payment_invoice_id=intent.payment_invoice_id,
        is_active=True,
        expires_at=datetime.utcnow() + timedelta(days=plan.duration_days),
        grace_expires_at=datetime.utcnow() + timedelta(days=plan.duration_days + 3),
    )

    intent.status = "COMPLETE"
    intent.updated_at = datetime.utcnow()

    db.session.add(subscription)
    db.session.commit()

    return subscription


# ----------------------------------------------------
# FREE TRIAL
# ----------------------------------------------------
def create_free_trial(user, days=7, grace_days=3) -> Subscription | None:
    trial_plan = Plan.query.filter_by(name="Trial").first()
    if not trial_plan:
        return None

    _deactivate_existing(user.id)

    sub = Subscription(
        user_id=user.id,
        plan_id=trial_plan.id,
        plan_name="Free Trial",
        properties_allowed=trial_plan.max_properties or 1,
        amount_paid=0,
        is_trial=True,
        is_active=True,
        expires_at=datetime.utcnow() + timedelta(days=days),
        grace_expires_at=datetime.utcnow() + timedelta(days=days + grace_days),
    )

    db.session.add(sub)
    db.session.commit()
    return sub


# ----------------------------------------------------
# ADMIN FORCE ACTIVATE
# ----------------------------------------------------
def admin_force_activate(user, plan: Plan, days=30) -> Subscription:
    _deactivate_existing(user.id)

    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        plan_name=plan.name,
        properties_allowed=plan.max_properties,
        amount_paid=0,
        payment_invoice_id=f"ADMIN-{uuid4().hex[:8]}",
        is_active=True,
        forced_by_admin=True,
        expires_at=datetime.utcnow() + timedelta(days=days),
        grace_expires_at=datetime.utcnow() + timedelta(days=days + 5),
    )

    db.session.add(sub)
    db.session.commit()
    return sub
