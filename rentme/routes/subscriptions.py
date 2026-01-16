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


# ------------------------------------------------------------
# LIST PLANS
# ------------------------------------------------------------
@subscriptions_bp.route("/plans", methods=["GET"])
@login_required
def list_plans():
    plans = Plan.query.order_by(Plan.price.asc()).all()
    form = SubscriptionForm()
    return render_template("subscriptions/plans.html", plans=plans, form=form)


# ------------------------------------------------------------
# START PAYMENT
# ------------------------------------------------------------
@subscriptions_bp.route("/pay/<int:plan_id>", methods=["POST"])
@login_required
def pay_plan(plan_id):
    form = SubscriptionForm()

    if not form.validate_on_submit():
        flash("Invalid phone number.", "danger")
        return redirect(url_for("subscriptions.list_plans"))

    plan = Plan.query.get_or_404(plan_id)
    phone = normalize_msisdn(form.phone.data)

    try:
        intent = SubscriptionIntent(
            user_id=current_user.id,
            plan_id=plan.id,
            reference=f"IPLAN-{plan.id}-{uuid4().hex[:10]}",
            amount=plan.price,
            status="PENDING",
            payer_account=current_user.email,
        )
        db.session.add(intent)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Intent creation failed")
        flash("Unable to start payment.", "danger")
        return redirect(url_for("subscriptions.list_plans"))

    response = create_intasend_payment(
        amount=plan.price,
        phone=phone,
        email=current_user.email,
        api_ref=intent.reference,   # ✅ FIXED
        redirect_url=url_for(
            "subscriptions.payment_status",
            _external=True,
        ),
        description=f"{plan.name} subscription",
    )

    checkout_url = response.get("url") or response.get("checkout_url")
    if not checkout_url:
        flash("Payment initialization failed.", "danger")
        return redirect(url_for("subscriptions.list_plans"))

    session["pending_plan"] = plan.id
    return redirect(checkout_url)


# ------------------------------------------------------------
# PAYMENT STATUS PAGE
# ------------------------------------------------------------
@subscriptions_bp.route("/payment-status", methods=["GET"])
@login_required
def payment_status():
    subscription = (
        Subscription.query
        .filter_by(user_id=current_user.id, is_active=True)
        .order_by(Subscription.created_at.desc())
        .first()
    )

    if subscription:
        session.pop("pending_plan", None)

    pending_plan = None
    if not subscription and session.get("pending_plan"):
        pending_plan = Plan.query.get(session["pending_plan"])

    return render_template(
        "subscriptions/payment_status.html",
        subscription=subscription,
        pending_plan=pending_plan,
    )


# ------------------------------------------------------------
# POLLING ENDPOINT (AJAX)
# ------------------------------------------------------------
@subscriptions_bp.route("/payment-status/check", methods=["GET"])
@login_required
def payment_status_check():
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
            amount_paid=float(subscription.amount_paid),
            expires_at=subscription.expires_at.isoformat(),
        )

    return jsonify(ok=False)
