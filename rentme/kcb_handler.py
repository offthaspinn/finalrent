# kcb_handler.py — Flask blueprint for KCB Paybill callbacks

import os
import logging
import sys
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from rentme.models import User, Tenant, LandlordSettings, Payment, Plan, Subscription
from rentme.extensions import db
from kcb_core import initiate_stk_push, simulate_payment

KCB_LIVE = os.getenv("KCB_LIVE", "0") == "1"

# Blueprint
kcb_bp = Blueprint("kcb_bp", __name__)

# Logging
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LOG_FILE = os.path.join(BASE_DIR, "kcb.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(console)


def _normalize_phone(msisdn):
    """Normalize Kenyan phone number to 2547XXXXXXXX format."""
    if not msisdn:
        return None
    s = str(msisdn).strip().replace("+", "").replace("-", "").replace(" ", "")
    if s.startswith("0") and len(s) == 10:
        return "254" + s[1:]
    if s.startswith("7") and len(s) == 9:
        return "254" + s
    if s.startswith("254") and len(s) >= 12:
        return s
    return s

def process_payment(account, amount, tx_id, msisdn=None, note="KCB Payment"):
    """Process a payment in ORM mode."""
    if Payment.query.filter_by(transaction_id=tx_id).first():
        logger.info("Duplicate tx ignored: %s", tx_id)
        return {"ok": False, "reason": "duplicate_tx"}

    # Resolve tenant
    tenant = None
    if msisdn:
        last6 = _normalize_phone(msisdn)[-6:]
        tenant = Tenant.query.filter(Tenant.phone.like(f"%{last6}%")).first()

    if not tenant:
        logger.warning("Tenant not found for tx=%s", tx_id)
        return {"ok": False, "reason": "tenant_not_found"}

    payment = Payment(
        transaction_id=tx_id,
        tenant_id=tenant.id,
        amount=float(amount),
        paid_at=datetime.utcnow(),
        note=note,
    )

    try:
        db.session.add(payment)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Payment insert failed")
        return {"ok": False, "reason": "insert_failed"}

    return {"ok": True, "tenant_id": tenant.id, "amount": amount, "tx_id": tx_id}


@kcb_bp.route("/kcb_callback", methods=["POST"])
def kcb_confirmation():
    """
    KCB payment confirmation callback.
    """
    payload = request.get_json() or {}
    logger.info("KCB CALLBACK PAYLOAD: %s", payload)

    tx_id = payload.get("transactionId")
    amount = float(payload.get("amount", 0))
    phone = payload.get("phoneNumber")
    account_ref = payload.get("accountReference")

    if not tx_id or amount <= 0:
        return jsonify({"ResultCode": 1, "ResultDesc": "Invalid data"}), 200

    msisdn = _normalize_phone(phone)

    result = process_payment(account=account_ref, amount=amount, tx_id=tx_id, msisdn=msisdn)

    return jsonify({"ResultCode": 0, "ResultDesc": "Payment recorded" if result["ok"] else "Failed"}), 200
