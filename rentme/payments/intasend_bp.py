from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
import hmac
import hashlib
import json

from rentme.extensions import db
from rentme.models import User, Subscription, Plan

intasend_bp = Blueprint("intasend", __name__, url_prefix="/intasend")


def verify_intasend_signature(payload: dict, signature: str, secret: str) -> bool:
    """
    Verify IntaSend webhook signature using HMAC-SHA256
    """
    computed = hmac.new(
        secret.encode(),
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, signature)


@intasend_bp.route("/webhook", methods=["POST"])
def intasend_webhook():
    payload = request.get_json(silent=True) or {}

    signature = request.headers.get("X-IntaSend-Signature")
    secret = current_app.config.get("INTASEND_WEBHOOK_SECRET")

    if not secret or not signature:
        return jsonify({"error": "Missing signature"}), 403

    if not verify_intasend_signature(payload, signature, secret):
        return jsonify({"error": "Invalid signature"}), 403

    # ------------------------------------------------
    # Accept only completed payments
    # ------------------------------------------------
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

    # ------------------------------------------------
    # 🔁 IDEMPOTENCY: prevent duplicate subscriptions
    # ------------------------------------------------
    existing = Subscription.query.filter_by(
        user_id=user.id,
        plan_id=plan.id,
        is_active=True,
    ).first()

    if existing:
        return jsonify({"ok": True, "reason": "already_active"}), 200

    # ------------------------------------------------
    # Deactivate previous subscriptions
    # ------------------------------------------------
    Subscription.query.filter_by(
        user_id=user.id,
        is_active=True,
    ).update({"is_active": False})

    expires_at = datetime.utcnow() + timedelta(days=plan.duration_days)

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        plan_name=plan.name,
        properties_allowed=plan.max_properties,
        amount_paid=float(amount or 0),
        is_active=True,
        created_at=datetime.utcnow(),
        expires_at=expires_at,
    )

    db.session.add(subscription)
    db.session.commit()

    return jsonify({"ok": True}), 200
