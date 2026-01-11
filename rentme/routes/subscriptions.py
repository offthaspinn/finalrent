from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    session,
    current_app,
    jsonify,
)
from flask_login import login_required, current_user
from uuid import uuid4

from rentme.models import Plan, Subscription, SubscriptionIntent
from rentme.forms import SubscriptionForm
from rentme.utils import normalize_msisdn
from rentme.payments.intasend_core import create_intasend_payment
from rentme.extensions import db

subscriptions_bp = Blueprint("subscriptions", __name__, url_prefix="/subscriptions")


# -------------------------------------------------------------------
# LIST PLANS
# -------------------------------------------------------------------
@subscriptions_bp.route("/plans", methods=["GET"])
@login_required
def list_plans():
    plans = Plan.query.order_by(Plan.price.asc()).all()
    form = SubscriptionForm()
    return render_template("subscriptions/plans.html", plans=plans, form=form)


# -------------------------------------------------------------------
# START SUBSCRIPTION PAYMENT
# -------------------------------------------------------------------
@subscriptions_bp.route("/pay/<int:plan_id>", methods=["POST"])
@login_required
def pay_plan(plan_id):
    form = SubscriptionForm()
    if not form.validate_on_submit():
        flash("Invalid phone number.", "danger")
        return redirect(url_for("subscriptions.list_plans"))

    plan = Plan.query.get_or_404(plan_id)
    phone = normalize_msisdn(form.phone.data)

    # -------------------------------------------------
    # 🔒 1. CREATE PENDING SUBSCRIPTION INTENT
    # -------------------------------------------------
    intent = SubscriptionIntent(
        user_id=current_user.id,
        plan_id=plan.id,
        status="pending"
    )
    db.session.add(intent)
    db.session.commit()

    # -------------------------------------------------
    # 💳 2. START PAYMENT WITH INTASEND
    # -------------------------------------------------
    # embed intent id in reference so webhook can find it
    tx_ref = f"PLAN-{plan.id}-INTENT-{intent.id}"

    response = create_intasend_payment(
        amount=plan.price,
        email=current_user.email,
        phone=phone,
        tx_ref=tx_ref,
        redirect_url=url_for("subscriptions.payment_status", _external=True),
        description=f"{plan.name} subscription",
    )

    if "url" not in response:
        current_app.logger.error(f"IntaSend error: {response}")
        flash("Payment initiation failed. Try again.", "danger")
        return redirect(url_for("subscriptions.list_plans"))

    # UX-only flag; webhook is source of truth
    session["pending_plan"] = plan.id

    return redirect(response["url"])


# -------------------------------------------------------------------
# PAYMENT STATUS PAGE
# -------------------------------------------------------------------
@subscriptions_bp.route("/payment-status", methods=["GET"])
@login_required
def payment_status():
    # Authoritative check: active subscription for current user
    subscription = (
        Subscription.query
        .filter_by(user_id=current_user.id, is_active=True)
        .order_by(Subscription.created_at.desc())
        .first()
    )

    # If webhook already created subscription, clear UX-only flag
    if subscription and session.get("pending_plan"):
        session.pop("pending_plan", None)

    # If no subscription yet, show the pending plan (if any)
    pending_plan = None
    if not subscription and session.get("pending_plan"):
        pending_plan = Plan.query.get(session["pending_plan"])

    return render_template(
        "subscriptions/payment_status.html",
        subscription=subscription,
        pending_plan=pending_plan,
    )


# -------------------------------------------------------------------
# POLLING ENDPOINT (AJAX)
# -------------------------------------------------------------------
@subscriptions_bp.route("/payment-status/check", methods=["GET"])
@login_required
def payment_status_check():
    """
    Polling endpoint used by the client to detect when the webhook
    has created an active subscription for the current user.
    """
    subscription = (
        Subscription.query
        .filter_by(user_id=current_user.id, is_active=True)
        .order_by(Subscription.created_at.desc())
        .first()
    )

    if subscription:
        return jsonify(
            ok=True,
            plan_name=subscription.plan_name,
            amount_paid=float(subscription.amount_paid or 0),
            expires_at=subscription.expires_at.isoformat()
            if subscription.expires_at else None,
        )

    return jsonify(ok=False)
