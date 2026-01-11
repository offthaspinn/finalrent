from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
import requests

from rentme.extensions import db
from rentme.models import User, Subscription, Plan

intasend_bp = Blueprint("intasend", __name__, url_prefix="/intasend")


def verify_intasend_transaction(invoice_id: str) -> dict | None:
    """
    Verify IntaSend payment by querying IntaSend API.
    This is REQUIRED because your account uses UNSIGNED webhooks.
    """
    base_url = current_app.config.get("INTASEND_BASE_URL")
    secret_key = current_app.config.get("INTASEND_SECRET_KEY")

    if not base_url or not secret_key:
        current_app.logger.error("IntaSend config missing")
        return None

    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.get(
            f"{base_url}/payment/status/",
            params={"invoice_id": invoice_id},
            headers=headers,
            timeout=20,
        )
    except Exception as e:
        current_app.logger.exception("IntaSend verification request failed")
        return None

    if resp.status_code != 200:
        current_app.logger.error(
            "IntaSend verification failed: %s", resp.text
        )
        return None

    data = resp.json()

    if data.get("state") != "COMPLETE":
        return None

    return data


@intasend_bp.route("/webhook", methods=["POST"])
def intasend_webhook():
    """
    IntaSend Collection Webhook (UNSIGNED)
    Security is enforced by server-to-server verification.
    """
    payload = request.get_json(silent=True) or {}

    invoice_id = payload.get("invoice_id")
    if not invoice_id:
        return jsonify({"ok": False}), 200

    # ------------------------------------------------
    # 🔐 VERIFY PAYMENT VIA INTASEND API (SOURCE OF TRUTH)
    # ------------------------------------------------
    verified = verify_intasend_transaction(invoice_id)
    if not verified:
        return jsonify({"ok": False}), 200

    api_ref = verified.get("api_ref")
    amount = verified.get("amount")
    email = verified.get("email")

    # ------------------------------------------------
    # Accept only subscription payments
    # ------------------------------------------------
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

