from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
from sqlalchemy.exc import SQLAlchemyError

from rentme.extensions import db
from rentme.models import SubscriptionIntent, Subscription, User, Plan

import requests

# ------------------------------------------------------------
# Blueprint
# ------------------------------------------------------------
intasend_bp = Blueprint("intasend", _name_, url_prefix="/intasend")


# ------------------------------------------------------------
# IntaSend verification
# ------------------------------------------------------------
def verify_intasend_transaction(invoice_id: str) -> bool:
    base_url = current_app.config.get("INTASEND_BASE_URL")
    secret_key = current_app.config.get("INTASEND_SECRET_KEY")

    if not base_url or not secret_key:
        current_app.logger.error("IntaSend config missing")
        return False

    try:
        resp = requests.get(
            f"{base_url}/payment/status/",
            params={"invoice_id": invoice_id},
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=20,
        )
    except Exception:
        current_app.logger.exception("IntaSend verification request failed")
        return False

    if resp.status_code != 200:
        return False

    data = resp.json()
    return data.get("state") == "COMPLETE"


# ============================================================
# IntaSend Webhook
# ============================================================
@intasend_bp.route("/webhook", methods=["POST"])
def intasend_webhook():
    payload = request.get_json(silent=True)

    if not payload:
        return jsonify({"ok": False, "error": "empty_payload"}), 400

    payment_state = payload.get("state")
    invoice_id = payload.get("invoice_id")
    mpesa_reference = payload.get("mpesa_reference")
    amount = payload.get("amount")

    if payment_state != "COMPLETE":
        return jsonify({"ok": True, "ignored": True}), 200

    if not invoice_id:
        return jsonify({"ok": False, "error": "missing_invoice"}), 400

    # --------------------------------------------------------
    # Verify payment with IntaSend
    # --------------------------------------------------------
    if not verify_intasend_transaction(invoice_id):
        current_app.logger.error(
            f"Verification failed for invoice {invoice_id}"
        )
        return jsonify({"ok": False, "error": "verification_failed"}), 400

    # --------------------------------------------------------
    # Locate MOST RECENT pending intent
    # --------------------------------------------------------
    intent = (
        SubscriptionIntent.query
        .filter_by(status="pending")
        .order_by(SubscriptionIntent.created_at.desc())
        .with_for_update()
        .first()
    )

    if not intent:
        current_app.logger.error("No pending SubscriptionIntent found")
        return jsonify({"ok": True, "intent": "not_found"}), 200

    user = User.query.get(intent.user_id)
    plan = Plan.query.get(intent.plan_id)

    if not user or not plan:
        current_app.logger.error("User or Plan missing")
        return jsonify({"ok": False, "error": "invalid_intent"}), 500

    # --------------------------------------------------------
    # Atomic finalize
    # --------------------------------------------------------
    try:
        subscription = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            plan_name=plan.name,
            properties_allowed=plan.properties_allowed,
            amount_paid=amount or plan.price,
            is_active=True,
            mpesa_receipt=mpesa_reference,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=plan.duration_days),
        )

        db.session.add(subscription)

        intent.status = "completed"
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Failed to finalize subscription")
        return jsonify({"ok": False, "error": "db_failure"}), 500

    return jsonify({"ok": True, "subscription": "activated"}), 200