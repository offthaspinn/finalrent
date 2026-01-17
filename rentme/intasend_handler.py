# intasend_handler.py — MERGED FINAL (UPDATED & FIXED)
# IntaSend webhook handler (LIVE, multi-tenant, reference-based)

import os
import hmac
import hashlib
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
)
from rentme.services.subscriptions import activate_paid_subscription

# --------------------------------------------------
# Blueprint (PUBLIC — NO AUTH)
# --------------------------------------------------
intasend_bp = Blueprint("intasend_bp", __name__, url_prefix="/intasend")

# --------------------------------------------------
# Config & Logging
# --------------------------------------------------
INTASEND_WEBHOOK_SECRET = os.getenv("INTASEND_WEBHOOK_SECRET")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("intasend")

# --------------------------------------------------
# Security — Signature Verification
# --------------------------------------------------
def verify_intasend_signature(raw_body: bytes, signature: str) -> bool:
    if not signature or not INTASEND_WEBHOOK_SECRET:
        return False

    computed = hmac.new(
        INTASEND_WEBHOOK_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, signature)

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
        logger.exception("❌ IntaSend verification failed")
        return False

    if resp.status_code != 200:
        logger.error("❌ Verification error: %s", resp.text)
        return False

    data = resp.json()
    return data.get("state") == "COMPLETE"

# --------------------------------------------------
# Core webhook — RENT PAYMENTS
# --------------------------------------------------
@intasend_bp.route("/webhooks/payment", methods=["POST"])
@csrf.exempt
def intasend_payment_webhook():
    raw_body = request.get_data()
    signature = request.headers.get("X-IntaSend-Signature")

    if not verify_intasend_signature(raw_body, signature):
        logger.warning("❌ Invalid IntaSend signature")
        return jsonify(ok=False), 401

    payload = request.get_json(silent=True) or {}
    logger.info("✅ IntaSend payload: %s", payload)

    if payload.get("status") != "COMPLETE":
        return jsonify(ok=True), 200

    transaction_id = payload.get("invoice_id")
    amount = float(payload.get("amount", 0))
    reference = payload.get("reference")

    if not transaction_id or not reference or amount <= 0:
        logger.warning("❌ Invalid payload fields")
        return jsonify(ok=False), 200

    # --------------------------------------------------
    # Idempotency
    # --------------------------------------------------
    if Payment.query.filter_by(transaction_id=transaction_id).first():
        logger.info("🔁 Duplicate transaction ignored: %s", transaction_id)
        return jsonify(ok=True), 200

    # --------------------------------------------------
    # Parse reference: RENTA-{landlord_id}-{tenant_id}-{invoice_code}
    # --------------------------------------------------
    try:
        _, landlord_id, tenant_id, invoice_code = reference.split("-")
        landlord_id = int(landlord_id)
        tenant_id = int(tenant_id)
    except Exception:
        logger.error("❌ Invalid reference format: %s", reference)
        return jsonify(ok=False), 200

    landlord = User.query.get(landlord_id)
    tenant = Tenant.query.get(tenant_id)
    invoice = (
        Invoice.query.filter_by(
            tenant_id=tenant.id,
            reference_code=invoice_code,
        ).first()
        if tenant
        else None
    )

    if not landlord or not tenant or not invoice:
        logger.error("❌ Reference resolution failed")
        return jsonify(ok=False), 200

    # --------------------------------------------------
    # Record payment
    # --------------------------------------------------
    payment = Payment(
        provider="INTASEND",
        transaction_id=transaction_id,
        reference=reference,
        amount=amount,
        currency="KES",
        status="CONFIRMED",
        paid_at=datetime.utcnow(),
        tenant_id=tenant.id,
        user_id=landlord.id,
        raw_payload=payload,
    )

    try:
        db.session.add(payment)

        invoice.amount_paid += amount
        invoice.status = (
            "PAID"
            if invoice.amount_paid >= invoice.amount_due
            else "PARTIAL"
        )

        tenant.balance -= amount
        tenant.last_payment_at = datetime.utcnow()

        db.session.commit()

    except Exception:
        db.session.rollback()
        logger.exception("❌ Failed to record payment")
        return jsonify(ok=False), 200

    # --------------------------------------------------
    # Real-time notification
    # --------------------------------------------------
    if socketio:
        socketio.emit(
            "payment_received",
            {
                "tenant_id": tenant.id,
                "amount": amount,
                "invoice": invoice.reference_code,
            },
            broadcast=True,
        )

    logger.info("💰 Payment recorded successfully: %s", transaction_id)
    return jsonify(ok=True), 200

# --------------------------------------------------
# Core webhook — SUBSCRIPTIONS
# --------------------------------------------------
@intasend_bp.route("/webhook", methods=["POST"])
@csrf.exempt
def intasend_subscription_webhook():
    data = request.get_json(silent=True) or {}
    reference = data.get("api_ref")
    invoice_id = data.get("invoice_id")
    status = (data.get("status") or "").upper()

    if not reference:
        return jsonify(ok=True), 200

    intent = SubscriptionIntent.query.filter_by(reference=reference).first()
    if not intent:
        return jsonify(ok=True), 200

    # Idempotency
    if intent.status == "COMPLETE":
        return jsonify(ok=True), 200

    intent.payment_invoice_id = invoice_id
    intent.transaction_id = (
        data.get("transaction_id")
        or data.get("mpesa_reference")
    )
    intent.amount = data.get("amount", intent.amount)
    intent.charge = data.get("charge", 0)
    intent.clearing_status = data.get("clearing_status")
    intent.updated_at = datetime.utcnow()

    if status != "COMPLETE":
        intent.status = status
        db.session.commit()
        return jsonify(ok=True), 200

    # Server-side verification
    if not verify_intasend_transaction(invoice_id):
        intent.status = "FAILED"
        db.session.commit()
        return jsonify(ok=True), 200

    activate_paid_subscription(intent)
    intent.status = "COMPLETE"
    db.session.commit()

    return jsonify(ok=True), 200
