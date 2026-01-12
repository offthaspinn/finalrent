from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
from sqlalchemy.exc import SQLAlchemyError

from rentme.extensions import db
from rentme.models import (
    SubscriptionIntent,
    Subscription,
    User
)

intasend_bp = Blueprint("intasend", __name__, url_prefix="/intasend")


# ============================================================
# IntaSend Webhook
# ============================================================
@intasend_bp.route("/intasend", methods=["POST"])
def intasend_webhook():
    """
    IntaSend M-Pesa webhook handler

    FINAL, AUTHORITATIVE FLOW:
    subscription_intents (pending)
        ↓
    IntaSend payment COMPLETE
        ↓
    subscription created
        ↓
    intent marked completed
    """

    payload = request.get_json(silent=True)

    if not payload:
        current_app.logger.error("IntaSend webhook: empty payload")
        return jsonify({"ok": False, "error": "empty_payload"}), 400

    # --------------------------------------------------------
    # 1. Validate payment state
    # --------------------------------------------------------
    payment_state = payload.get("state")
    if payment_state != "COMPLETE":
        # Ignore non-complete payments safely
        return jsonify({"ok": True, "ignored": True}), 200

    invoice_id = payload.get("invoice_id")
    mpesa_reference = payload.get("mpesa_reference")
    amount = payload.get("amount")

    if not invoice_id:
        current_app.logger.error("IntaSend webhook: missing invoice_id")
        return jsonify({"ok": False, "error": "missing_invoice_id"}), 400

    # --------------------------------------------------------
    # 2. Load subscription intent
    # --------------------------------------------------------
    intent = SubscriptionIntent.query.filter_by(
        invoice_id=invoice_id
    ).with_for_update().first()

    if not intent:
        current_app.logger.error(
            f"IntaSend webhook: intent not found for invoice_id={invoice_id}"
        )
        # Return 200 to prevent IntaSend retries
        return jsonify({"ok": True, "intent": "not_found"}), 200

    # --------------------------------------------------------
    # 3. Idempotency protection
    # --------------------------------------------------------
    if intent.status == "completed":
        return jsonify({"ok": True, "already_processed": True}), 200

    # --------------------------------------------------------
    # 4. Validate user exists
    # --------------------------------------------------------
    user = User.query.get(intent.user_id)
    if not user:
        current_app.logger.error(
            f"IntaSend webhook: user not found (user_id={intent.user_id})"
        )
        return jsonify({"ok": False, "error": "user_not_found"}), 500

    # --------------------------------------------------------
    # 5. Create subscription (ATOMIC)
    # --------------------------------------------------------
    try:
        # Safety: ensure no duplicate active subscription
        existing_subscription = Subscription.query.filter_by(
            user_id=intent.user_id,
            plan_id=intent.plan_id,
            is_active=True
        ).first()

        if not existing_subscription:
            subscription = Subscription(
                user_id=intent.user_id,
                plan_id=intent.plan_id,
                plan_name=intent.plan_name,
                properties_allowed=intent.properties_allowed,
                amount_paid=amount or intent.amount,
                is_active=True,
                started_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=intent.duration_days)
            )
            db.session.add(subscription)

        # ----------------------------------------------------
        # 6. Finalize intent
        # ----------------------------------------------------
        intent.status = "completed"
        intent.completed_at = datetime.utcnow()
        intent.payment_reference = mpesa_reference
        intent.amount_paid = amount or intent.amount

        db.session.commit()

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception(
            f"IntaSend webhook DB failure for invoice_id={invoice_id}"
        )
        return jsonify({"ok": False, "error": "db_failure"}), 500

    # --------------------------------------------------------
    # 7. Success
    # --------------------------------------------------------
    return jsonify({"ok": True, "status": "subscription_activated"}), 200