from datetime import datetime, timedelta
from uuid import uuid4

from rentme.extensions import db
from rentme.models import Subscription, SubscriptionIntent, Plan


# ----------------------------------------------------
# INTERNAL: deactivate existing subscriptions
# ----------------------------------------------------
def _deactivate_existing(user_id: int):
    Subscription.query.filter_by(
        user_id=user_id,
        is_active=True,
    ).update(
        {
            "is_active": False,
            "is_grace": False,
        },
        synchronize_session=False,
    )


# ----------------------------------------------------
# PAID SUBSCRIPTION (Webhook-driven)
def activate_paid_subscription(intent: SubscriptionIntent) -> Subscription | None:
    """
    Finalizes a paid subscription intent into an active subscription.
    MUST be idempotent.
    """

    # ------------------------------------
    # Idempotency guard (CORRECT)
    # ------------------------------------
    existing = Subscription.query.filter_by(intent_id=intent.id).first()
    if existing:
        return existing

    plan = intent.plan or Plan.query.get(intent.plan_id)
    if not plan:
        return None

    now = datetime.utcnow()

    # ------------------------------------
    # Deactivate existing subscriptions
    # ------------------------------------
    _deactivate_existing(intent.user_id)

    # ------------------------------------
    # Create subscription snapshot
    # ------------------------------------
    subscription = Subscription(
        user_id=intent.user_id,
        plan_id=plan.id,
        intent_id=intent.id,
        plan_name=plan.name,
        properties_allowed=plan.max_properties,
        amount_paid=intent.amount,
        payment_invoice_id=intent.payment_invoice_id,
        is_active=True,
        is_trial=False,
        is_grace=False,
        created_at=now,
        expires_at=now + timedelta(days=plan.duration_days),
        grace_expires_at=now + timedelta(days=plan.duration_days + 3),
    )

    # ------------------------------------
    # Finalize intent
    # ------------------------------------
    intent.status = "COMPLETE"
    intent.updated_at = now

    db.session.add(subscription)
    db.session.commit()

    return subscription
# ----------------------------------------------------
# FREE TRIAL
# ----------------------------------------------------
def create_free_trial(user, days: int = 7, grace_days: int = 3) -> Subscription | None:
    """
    Auto-creates a free trial subscription.
    """

    trial_plan = Plan.query.filter_by(name="Trial").first()
    if not trial_plan:
        return None

    now = datetime.utcnow()

    _deactivate_existing(user.id)

    sub = Subscription(
        user_id=user.id,
        plan_id=trial_plan.id,
        plan_name="Free Trial",
        properties_allowed=trial_plan.max_properties or 1,
        amount_paid=0,
        is_trial=True,
        is_active=True,
        is_grace=False,
        created_at=now,
        expires_at=now + timedelta(days=days),
        grace_expires_at=now + timedelta(days=days + grace_days),
    )

    db.session.add(sub)
    db.session.commit()
    return sub


# ----------------------------------------------------
# ADMIN FORCE ACTIVATE
# ----------------------------------------------------
def admin_force_activate(user, plan: Plan, days: int = 30) -> Subscription:
    """
    Force-activates a subscription (admin override).
    """

    now = datetime.utcnow()

    _deactivate_existing(user.id)

    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        plan_name=plan.name,
        properties_allowed=plan.max_properties,
        amount_paid=0,
        payment_invoice_id=f"ADMIN-{uuid4().hex[:8]}",
        is_active=True,
        is_trial=False,
        is_grace=False,
        forced_by_admin=True,
        created_at=now,
        expires_at=now + timedelta(days=days),
        grace_expires_at=now + timedelta(days=days + 5),
    )

    db.session.add(sub)
    db.session.commit()
    return sub
