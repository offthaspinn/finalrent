from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
from sqlalchemy.exc import SQLAlchemyError

from rentme.extensions import db
from rentme.models import (
    SubscriptionIntent,
    Subscription,
    User,
    Plan
)

import requests

# ------------------------------------------------------------
# Blueprint
# ------------------------------------------------------------
intasend_bp = Blueprint("intasend", __name__, url_prefix="/intasend")


# ------------------------------------------------------------
# Verify IntaSend payment (UNSIGNED WEBHOOKS REQUIRE THIS)
# ------------------------------------------------------------
def verify_intasend_transaction(invoice_id: str) -> dict | None:
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
    except Exception:
        current_app.logger.exception("IntaSend verification request failed")
        return None

    if resp.status_code != 200:
        current_app.logger.error("IntaSend verification failed: %s", resp.text)
        return None

    data = resp.json()

    if data.get("state") != "COMPLETE":
        return None

    return data


# ============================================================
# IntaSend Webhook
# ============================================================
@intasend_bp.route("/webhook", methods=["POST"])
def intasend_webhook():
    payload = request.get_json(silent=True)

    if not payload:
        return jsonify({"ok": False, "error": "empty_payload"}), 400

    # --------------------------------------------------------
    # 1. Extract fields
    # --------------------------------------------------------
    if payload.get("state") != "COMPLETE":
        return jsonify({"ok": True, "ignored": True}), 200

    invoice_id = payload.get("invoice_id")
    mpesa_ref = payload.get("mpesa_reference")

    if not invoice_id:
        current_app.logger.error("Missing invoice_id in webhook")
        return jsonify({"ok": False, "error": "missing_invoice"}), 400

    # --------------------------------------------------------
    # 2. Verify payment with IntaSend
    # --------------------------------------------------------
    verification = verify_intasend_transaction(invoice_id)
    if not verification:
        return jsonify({"ok": False, "error": "verification_failed"}), 400

    # --------------------------------------------------------
    # 3. Load intent (LOCKED)
    # --------------------------------------------------------
    try:
        intent = (
            SubscriptionIntent.query
            .filter_by(invoice_id=invoice_id)
            .with_for_update()
            .first()
        )

        if not intent:
            # Payment is real but intent missing → do not retry
            current_app.logger.error(
                f"No SubscriptionIntent for invoice_id={invoice_id}"
            )
            return jsonify({"ok": True, "intent": "not_found"}), 200

        if intent.status == "completed":
            return jsonify({"ok": True, "already_processed": True}), 200

        # ----------------------------------------------------
        # 4. Load user & plan
        # ----------------------------------------------------
        user = User.query.get(intent.user_id)
        plan = Plan.query.get(intent.plan_id)

        if not user or not plan:
            current_app.logger.error("User or Plan missing")
            return jsonify({"ok": False, "error": "data_integrity"}), 500

        # ----------------------------------------------------
        # 5. Prevent duplicate active subscriptions
        # ----------------------------------------------------
        existing = Subscription.query.filter_by(
            user_id=user.id,
            is_active=True
        ).first()

        if not existing:
            subscription = Subscription(
                user_id=user.id,
                plan_id=plan.id,
                plan_name=plan.name,
                properties_allowed=plan.max_properties,
                amount_paid=plan.price,
                is_active=True,
                mpesa_receipt=mpesa_ref,
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow()
                + timedelta(days=plan.duration_days)
            )
            db.session.add(subscription)

        # ----------------------------------------------------
        # 6. Finalize intent
        # ----------------------------------------------------
        intent.status = "completed"
        intent.completed_at = datetime.utcnow()
        intent.payment_reference = mpesa_ref

        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            f"Webhook DB failure invoice_id={invoice_id}"
        )
        return jsonify({"ok": False, "error": "db_failure"}), 500

    # --------------------------------------------------------
    # 7. Success
    # --------------------------------------------------------
    return jsonify({"ok": True, "subscription": "activated"}), 200