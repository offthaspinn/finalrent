from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import requests

from rentme.extensions import db
from rentme.models import SubscriptionIntent
from rentme.services.subscriptions import activate_paid_subscription

intasend_bp = Blueprint("intasend", __name__, url_prefix="/intasend")


# ------------------------------------------------------------
# VERIFY PAYMENT WITH INTASEND (MANDATORY)
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
            headers={
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )
    except Exception:
        current_app.logger.exception("IntaSend verification failed")
        return False

    if resp.status_code != 200:
        current_app.logger.error("Verification error: %s", resp.text)
        return False

    data = resp.json()
    return data.get("state") == "COMPLETE"


# ------------------------------------------------------------
# INTA SEND WEBHOOK
# ------------------------------------------------------------
@intasend_bp.route("/webhook", methods=["POST"])
def intasend_webhook():
    data = request.get_json(silent=True)
    if not data:
        return jsonify(ok=False), 400

    # ✅ IntaSend sends api_ref
    reference = data.get("api_ref")
    invoice_id = data.get("invoice_id")
    status = (data.get("status") or "").upper()

    intent = SubscriptionIntent.query.filter_by(reference=reference).first()
    if not intent:
        # Unknown reference → ACK to stop retries
        return jsonify(ok=True), 200

    # --------------------------------------------------------
    # IDEMPOTENCY GUARD
    # --------------------------------------------------------
    if intent.status == "COMPLETE":
        return jsonify(ok=True), 200

    # --------------------------------------------------------
    # UPDATE INTENT SNAPSHOT
    # --------------------------------------------------------
    intent.payment_invoice_id = invoice_id
    intent.transaction_id = data.get("transaction_id")
    intent.amount = data.get("amount", intent.amount)
    intent.charge = data.get("charge", 0)
    intent.clearing_status = data.get("clearing_status")
    intent.updated_at = datetime.utcnow()

    if status != "COMPLETE":
        intent.status = status
        db.session.commit()
        return jsonify(ok=True), 200

    # --------------------------------------------------------
    # VERIFY WITH INTASEND (SECURITY)
    # --------------------------------------------------------
    if not verify_intasend_transaction(invoice_id):
        intent.status = "FAILED"
        db.session.commit()
        return jsonify(ok=True), 200

    # --------------------------------------------------------
    # ✅ FINAL ACTIVATION (SINGLE SOURCE OF TRUTH)
    # --------------------------------------------------------
    activate_paid_subscription(intent)

    return jsonify(ok=True), 200
