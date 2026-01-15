from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
from sqlalchemy.exc import SQLAlchemyError
import requests

from rentme.extensions import db
from rentme.models import SubscriptionIntent, Subscription, User, Plan

# ============================================================
# Blueprint
# ============================================================
intasend_bp = Blueprint("intasend", __name__, url_prefix="/intasend")


# ============================================================
# IntaSend verification (REQUIRED – unsigned webhooks)
# ============================================================
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
        current_app.logger.exception("IntaSend verification request failed")
        return False

    if resp.status_code != 200:
        current_app.logger.error(
            "IntaSend verification failed: %s", resp.text
        )
        return False

    data = resp.json()
    return data.get("state") == "COMPLETE"
# ============================================================
# IntaSend Webhook
# ============================================================
@intasend_bp.route("/webhook", methods=["POST"])
def intasend_webhook():
    data = request.get_json(silent=True)
    if not data:
        return jsonify(ok=False), 400

    reference = data.get("reference")
    invoice_id = data.get("invoice_id")
    status = data.get("status")

    intent = SubscriptionIntent.query.filter_by(reference=reference).first()
    if not intent:
        return jsonify(ok=True), 200

    intent.payment_invoice_id = invoice_id
    intent.transaction_id = data.get("transaction_id")
    intent.status = status
    intent.amount = data.get("amount")
    intent.charge = data.get("charge", 0)
    intent.clearing_status = data.get("clearing_status")
    intent.updated_at = datetime.utcnow()

    if status != "COMPLETE":
        db.session.commit()
        return jsonify(ok=True), 200

    plan = Plan.query.get(intent.plan_id)

    Subscription.query.filter_by(
        user_id=intent.user_id,
        is_active=True
    ).update({"is_active": False})

    subscription = Subscription(
        user_id=intent.user_id,
        plan_id=plan.id,
        plan_name=plan.name,
        properties_allowed=plan.max_properties,
        amount_paid=intent.amount,
        payment_invoice_id=invoice_id,
        expires_at=datetime.utcnow() + timedelta(days=plan.duration_days),
        is_active=True,
    )

    db.session.add(subscription)
    db.session.commit()

    return jsonify(ok=True), 200
