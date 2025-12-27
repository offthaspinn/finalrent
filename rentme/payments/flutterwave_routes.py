from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
from rentme.extensions import db
from rentme.models import User, Subscription, Plan

flutterwave_bp = Blueprint(
    "flutterwave",
    __name__,
    url_prefix="/flutterwave"
)


@flutterwave_bp.route("/webhook", methods=["POST"])
def flutterwave_webhook():
    """
    Flutterwave webhook handler
    """

    # 🔐 Verify webhook signature
    signature = request.headers.get("verif-hash")
    webhook_secret = current_app.config.get("FLW_WEBHOOK_SECRET")

    if not webhook_secret or signature != webhook_secret:
        return jsonify({"error": "Invalid signature"}), 403

    payload = request.get_json(silent=True) or {}
    data = payload.get("data", {})

    # Only process successful payments
    if data.get("status") != "successful":
        return jsonify({"ok": False}), 200

    tx_ref = data.get("tx_ref")
    amount = data.get("amount")
    customer = data.get("customer", {})
    email = customer.get("email")

    if not tx_ref or "PLAN-" not in tx_ref or not email:
        return jsonify({"ok": False}), 200

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"ok": False}), 200

    try:
        plan_id = int(tx_ref.split("PLAN-")[1])
    except (IndexError, ValueError):
        return jsonify({"ok": False}), 200

    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"ok": False}), 200

    # 🔁 Deactivate existing active subscriptions
    Subscription.query.filter_by(
        user_id=user.id,
        is_active=True
    ).update({"is_active": False})

    expires_at = datetime.utcnow() + timedelta(days=plan.duration_days)

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        plan_name=plan.name,
        properties_allowed=plan.max_properties,
        amount_paid=amount,
        is_active=True,
        created_at=datetime.utcnow(),
        expires_at=expires_at,
    )

    db.session.add(subscription)
    db.session.commit()

    return jsonify({"ok": True}), 200
