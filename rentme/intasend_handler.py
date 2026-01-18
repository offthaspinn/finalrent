# intasend_handler.py
# IntaSend webhook handler (LIVE, multi-tenant, reference-based)

import logging
from datetime import datetime

import requests
from flask import Blueprint, request, jsonify, current_app

from rentme.extensions import db, socketio, csrf
from rentme.models import (
    Payment,
    Tenant,
    User,
    Invoice,
    SubscriptionIntent,
    Property,
    Unit,
)
from rentme.services.subscriptions import activate_paid_subscription

# --------------------------------------------------
# Blueprint (PUBLIC — NO AUTH)
# --------------------------------------------------
intasend_bp = Blueprint("intasend_bp", __name__, url_prefix="/intasend")

# --------------------------------------------------
# Logging
# --------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("intasend")

# --------------------------------------------------
# Verify payment with IntaSend API (SERVER TRUST)
# --------------------------------------------------
def verify_intasend_transaction(invoice_id: str) -> bool:
    base_url = current_app.config.get("INTASEND_BASE_URL")
    secret_key = current_app.config.get("INTASEND_SECRET_KEY")

    if not base_url or not secret_key:
        logger.error("❌ IntaSend config missing")
        return False

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
        logger.exception("❌ IntaSend verification request failed")
        return False

    if resp.status_code != 200:
        logger.error("❌ Verification HTTP error: %s", resp.text)
        return False

    data = resp.json()
    return data.get("state") == "COMPLETE"

# --------------------------------------------------
# RENT PAYMENTS WEBHOOK
# --------------------------------------------------
@intasend_bp.route("/webhooks/payment", methods=["POST"])
@csrf.exempt
def intasend_payment_webhook():
    payload = request.get_json(silent=True) or {}
    logger.info("📨 IntaSend payment payload: %s", payload)

    # IntaSend uses `state`
    if payload.get("state") != "COMPLETE":
        return jsonify(ok=True), 200

    invoice_id = payload.get("invoice_id")
    amount = float(payload.get("value", 0))
    reference = payload.get("api_ref") or payload.get("reference")

    if not invoice_id or not reference or amount <= 0:
        logger.warning("❌ Invalid payment payload")
        return jsonify(ok=True), 200

    # 🔐 Server-side verification (REAL security)
    if not verify_intasend_transaction(invoice_id):
        logger.error("❌ Payment verification failed for %s", invoice_id)
        return jsonify(ok=True), 200

    # Idempotency
    if Payment.query.filter_by(transaction_id=invoice_id).first():
        logger.info("🔁 Duplicate payment ignored: %s", invoice_id)
        return jsonify(ok=True), 200

    # Resolve unit via payment reference
    unit = Unit.query.filter_by(payment_ref=reference).first()
    if not unit:
        logger.error("❌ No unit found for reference %s", reference)
        return jsonify(ok=True), 200

    property_obj = Property.query.get(unit.property_id)
    landlord = User.query.get(property_obj.landlord_id)

    payment = Payment(
        provider="INTASEND",
        transaction_id=invoice_id,
        reference=reference,
        amount=amount,
        currency="KES",
        status="CONFIRMED",
        paid_at=datetime.utcnow(),
        user_id=landlord.id,
        property_id=property_obj.id,
        unit_id=unit.id,
        raw_payload=payload,
    )

    try:
        db.session.add(payment)
        unit.last_paid_at = datetime.utcnow()
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("❌ Failed to record rent payment")
        return jsonify(ok=True), 200

    # Realtime notify (optional)
    if socketio:
        socketio.emit(
            "rent_payment_received",
            {
                "unit_id": unit.id,
                "amount": amount,
                "reference": reference,
            },
            broadcast=True,
        )

    logger.info("💰 Rent payment recorded: %s", invoice_id)
    return jsonify(ok=True), 200

# --------------------------------------------------
# SUBSCRIPTION WEBHOOK
# --------------------------------------------------
@intasend_bp.route("/webhook", methods=["POST"])
@csrf.exempt
def intasend_subscription_webhook():
    data = request.get_json(silent=True) or {}
    logger.info("📨 IntaSend subscription payload: %s", data)

    reference = data.get("api_ref")
    invoice_id = data.get("invoice_id")
    state = (data.get("state") or data.get("status") or "").upper()

    if not reference:
        return jsonify(ok=True), 200

    intent = SubscriptionIntent.query.filter_by(reference=reference).first()
    if not intent:
        return jsonify(ok=True), 200

    # Idempotency
    if intent.status == "COMPLETE":
        return jsonify(ok=True), 200

    intent.payment_invoice_id = invoice_id
    intent.transaction_id = data.get("mpesa_reference")
    intent.amount = float(data.get("value", intent.amount))
    intent.updated_at = datetime.utcnow()

    if state != "COMPLETE":
        intent.status = state
        db.session.commit()
        return jsonify(ok=True), 200

    # 🔐 Server-side verification
    if not verify_intasend_transaction(invoice_id):
        intent.status = "FAILED"
        db.session.commit()
        return jsonify(ok=True), 200

    activate_paid_subscription(intent)
    intent.status = "COMPLETE"
    db.session.commit()

    logger.info("🎉 Subscription activated: %s", reference)
    return jsonify(ok=True), 200