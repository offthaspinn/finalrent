from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
from rentme.extensions import db
from rentme.models import User, Subscription, Plan

intasend_bp = Blueprint(
    "intasend",
    __name__,
    url_prefix="/intasend"
)


@intasend_bp.route("/webhook", methods=["POST"])
def intasend_webhook():
    """
    IntaSend webhook handler
    """

    signature = request.headers.get("X-IntaSend-Signature")
    secret = current_app.config.get("INTASEND_WEBHOOK_SECRET")

    if not secret or signature != secret:
        return jsonify({"error": "Invalid signature"}), 403

    payload = request.get_json(silent=True) or {}

    if payload.get("state") != "COMPLETE":
        return jsonify({"ok": False}), 200

    api_ref = payload.get("api_ref")
    amount = payload.get("amount")
    email = payload.get("email")

    if not api_ref or "PLAN-" not in api_ref:
        return jsonify({"ok": False}), 200

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"ok": False}), 200

    try:
        plan_id = int(api_ref.split("PLAN-")[1].split("-")[0])
    except Exception:
        return jsonify({"ok": False}), 200

    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"ok": False}), 200

    # 🔁 Deactivate existing subscriptions
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
