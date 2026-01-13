from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
from sqlalchemy.exc import SQLAlchemyError
import requests

from rentme.extensions import db
from rentme.models import SubscriptionIntent, Subscription, User, Plan

# ============================================================
# Blueprint
# ============================================================
intasend_bp = Blueprint("intasend", _name_, url_prefix="/intasend")


# ============================================================
# IntaSend verification (REQUIRED – unsigned webhooks)
# ============================================================
def verify_intasend_transaction(invoice_id: str) -> dict | None:
    base_url = current_app.config.get("INTASEND_BASE_URL")
    secret_key = current_app.config.get("INTASEND_SECRET_KEY")

    if not base_url or not secret_key:
        current_app.logger.error("IntaSend config missing")
        return None

    try:
        resp = requests.get(
            f"{base_url}/payment/status/",
            params={"invoice_id": invoice_id},
            headers={
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )
    except Exception:
        current_app.logger.exception("IntaSend verification request failed")
        return None

    if resp.status_code != 200:
        current_app.logger.error(
            "IntaSend verification failed: %s", resp.text
        )
        return None

    data = resp.json()
    return data if data.get("state") == "COMPLETE" else None


# ============================================================
# IntaSend Webhook
# ============================================================
@intasend_bp.route("/webhook", methods=["POST"])
def intasend_webhook():
    payload = request.get_json(silent=True)

    if not payload:
        return jsonify({"ok": False, "error": "empty_payload"}), 400

    # --------------------------------------------------------
    # 1. Extract fields (ONLY supported fields)
    # --------------------------------------------------------
    payment_state = payload.get("state")
    invoice_id = payload.get("invoice_id")  # 🔑 THIS IS THE KEY
    mpesa_reference = payload.get("mpesa_reference")
    amount = payload.get("amount")

    if payment_state != "COMPLETE":
        return jsonify({"ok": True, "ignored": True}), 200

    if not invoice_id:
        current_app.logger.error("Missing invoice_id in webhook")
        return jsonify({"ok": False, "error": "missing_invoice_id"}), 400

    # --------------------------------------------------------
    # 2. Verify with IntaSend (AUTHORITATIVE)
    # --------------------------------------------------------
    if not verify_intasend_transaction(invoice_id):
        current_app.logger.error(
            f"Verification failed for invoice_id={invoice_id}"
        )
        return jsonify({"ok": False, "error": "verification_failed"}), 400

    # --------------------------------------------------------
    # 3. Load subscription intent (LOCKED)
    # --------------------------------------------------------
    intent = (
        SubscriptionIntent.query
        .filter_by(api_ref=invoice_id)  # 🔑 api_ref == invoice_id
        .with_for_update()
        .first()
    )

    if not intent:
        current_app.logger.error(
            f"SubscriptionIntent not found for invoice_id={invoice_id}"
        )
        return jsonify({"ok": True, "intent": "not_found"}), 200

    # --------------------------------------------------------
    # 4. Idempotency
    # --------------------------------------------------------
    if intent.status == "completed":
        return jsonify({"ok": True, "already_processed": True}), 200

    # --------------------------------------------------------
    # 5. Load user & plan
    # --------------------------------------------------------
    user = User.query.get(intent.user_id)
    plan = Plan.query.get(intent.plan_id)

    if not user or not plan:
        current_app.logger.error(
            f"User or Plan missing for intent_id={intent.id}"
        )
        return jsonify({"ok": False, "error": "invalid_intent"}), 500

    # --------------------------------------------------------
    # 6. Atomic subscription creation
    # --------------------------------------------------------
    try:
        existing = Subscription.query.filter_by(
            user_id=user.id,
            plan_id=plan.id,
            is_active=True,
        ).first()

        if not existing:
            subscription = Subscription(
                user_id=user.id,
                plan_id=plan.id,
                plan_name=plan.name,
                properties_allowed=plan.max_properties,
                amount_paid=amount or intent.amount,
                is_active=True,
                mpesa_receipt=mpesa_reference,
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow()
                + timedelta(days=plan.duration_days),
            )
            db.session.add(subscription)

        intent.status = "completed"
        intent.completed_at = datetime.utcnow()
        intent.payment_reference = mpesa_reference
        intent.amount = amount or intent.amount

        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            f"DB failure finalizing invoice_id={invoice_id}"
        )
        return jsonify({"ok": False, "error": "db_failure"}), 500

    return jsonify({"ok": True, "subscription": "activated"}), 200