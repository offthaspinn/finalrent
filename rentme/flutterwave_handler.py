import os
import uuid
import logging
import hashlib
import hmac
import sqlite3
import psycopg2
import psycopg2.extras

from typing import Optional
from datetime import datetime, timedelta

import requests
from flask import request, jsonify, current_app, Blueprint

from rentme.extensions import db
from rentme.models import Payment, User, Subscription, Plan

logger = logging.getLogger(__name__)
bp = Blueprint("payments", __name__)

# ---------------------------------------------------------------------
# Config / feature flags (adjust or set in Flask config)
# ---------------------------------------------------------------------
# Example fallbacks; prefer setting these in Flask config
DB_SQLITE_PATH = os.environ.get("DB_SQLITE_PATH", "rentme.sqlite3")
_USE_PG = os.environ.get("USE_PG", "0") in ("1", "true", "True")

# ---------------------------------------------------------------------
# Database connection helpers (Postgres / SQLite)
# ---------------------------------------------------------------------
def _pg_conn():
    return psycopg2.connect(
        os.environ["DATABASE_URL"], cursor_factory=psycopg2.extras.RealDictCursor
    )


def _sqlite_conn():
    conn = sqlite3.connect(
        DB_SQLITE_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    return conn


def _connect():
    if _USE_PG:
        return _pg_conn()
    return _sqlite_conn()

# ---------------------------------------------------------------------
# Phone normalization helpers
# ---------------------------------------------------------------------
def _norm_phone_db(p: Optional[str]) -> str:
    """
    Normalize phone for DB storage: return digits in '2547XXXXXXXX' form when possible.
    """
    if not p:
        return ""
    digits = "".join(ch for ch in str(p) if ch.isdigit())
    if len(digits) == 10 and digits.startswith("0"):
        digits = "254" + digits[1:]
    if len(digits) == 9 and digits.startswith("7"):
        digits = "254" + digits
    return digits


def _normalize_msisdn(msisdn):
    """
    Normalize incoming msisdn to a consistent format used by your User.login_phone.
    Returns None if input is falsy.
    """
    if not msisdn:
        return None
    s = str(msisdn).strip()
    if s.startswith("+"):
        s = s[1:]
    s = s.replace(" ", "").replace("-", "")
    # Accept E.164-like local format (2547...)
    if s.startswith("254") and len(s) >= 12:
        return s
    if s.startswith("0") and len(s) == 10:
        return "254" + s[1:]
    if s.startswith("7") and len(s) == 9:
        return "254" + s
    return s

# ---------------------------------------------------------------------
# Flutterwave charge + webhook
# ---------------------------------------------------------------------
def flutterwave_charge(phone, amount, account_reference, transaction_desc, email=None):
    """
    Initiates a Flutterwave M-PESA charge for subscriptions.
    Returns the parsed JSON response (or an empty dict on failure).
    """
    # Prefer config value if available at runtime
    FLW_SECRET_KEY = current_app.config.get("FLW_SECRET_KEY", os.environ.get("FLW_SECRET_KEY", ""))
    tx_ref = f"PLAN-{account_reference}-{uuid.uuid4().hex[:8]}"
    url = "https://api.flutterwave.com/v3/charges?type=mpesa"
    payload = {
        "tx_ref": tx_ref,
        "amount": str(amount),
        "currency": "KES",
        "phone_number": phone,
        "email": email or "no-reply@example.com",
        "fullname": transaction_desc,
        "meta": {"account_reference": account_reference},
    }
    headers = {"Authorization": f"Bearer {FLW_SECRET_KEY}", "Content-Type": "application/json"}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json() if resp.content else {}
    except Exception as exc:
        logger.exception("Flutterwave charge failed: %s", exc)
        data = {}

    # Save pending payment (use tx_ref as fallback)
    try:
        payment = Payment(
            transaction_id=data.get("data", {}).get("id") or tx_ref,
            amount=amount,
            paid_at=datetime.utcnow(),
            note="Subscription payment (flutterwave)",
            checkout_request_id=data.get("data", {}).get("flw_ref") or tx_ref,
        )
        db.session.add(payment)
        db.session.commit()
    except Exception:
        logger.exception("Failed to save pending payment (flutterwave_charge)")

    return data


def verify_flw_signature(body_bytes, header_signature, secret):
    """
    Verify Flutterwave webhook signature (verif-hash header).
    `body_bytes` must be raw request.get_data() bytes.
    """
    if not secret:
        logger.warning("No FLW webhook secret configured")
        return False
    computed = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, header_signature)


@bp.route("/flutterwave/webhook", methods=["POST"])
def flutterwave_webhook():
    """
    Single webhook endpoint to handle Flutterwave events.
    Verifies signature, records payments idempotently, and activates subscriptions.
    """
    secret = current_app.config.get("FLW_WEBHOOK_SECRET", os.environ.get("FLW_WEBHOOK_SECRET", ""))
    signature = request.headers.get("verif-hash", "")
    raw = request.get_data()

    # Verify signature
    try:
        if not verify_flw_signature(raw, signature, secret):
            logger.warning("Invalid Flutterwave signature")
            return jsonify({"status": "error", "message": "invalid signature"}), 400
    except Exception:
        logger.exception("Signature verification error")
        return jsonify({"status": "error", "message": "signature verification failed"}), 400

    event = request.json or {}
    event_type = event.get("event")
    data = event.get("data", {}) or {}

    # Only handle successful charge completion
    if event_type == "charge.completed" and data.get("status") == "successful":
        try:
            tx_ref = data.get("tx_ref")
            amount = float(data.get("amount", 0))
            phone = (data.get("customer") or {}).get("phone_number")
            meta = data.get("meta") or {}
            account_ref = meta.get("account_reference") or tx_ref
            flw_ref = data.get("flw_ref") or data.get("id")

            if not tx_ref or amount <= 0:
                logger.warning("Invalid charge.completed payload: tx_ref=%s amount=%s", tx_ref, amount)
                return jsonify({"status": "error", "message": "invalid data"}), 200

            # Normalize phone using helper
            msisdn = _normalize_msisdn(phone)

            # Idempotent payment record: check by checkout_request_id (flw_ref) or transaction_id (tx_ref)
            existing = None
            if flw_ref:
                existing = Payment.query.filter_by(checkout_request_id=flw_ref).first()
            if not existing and tx_ref:
                existing = Payment.query.filter_by(transaction_id=tx_ref).first()

            if not existing:
                payment = Payment(
                    transaction_id=data.get("id") or tx_ref,
                    amount=amount,
                    paid_at=datetime.utcnow(),
                    note="Flutterwave confirmation",
                    checkout_request_id=flw_ref or tx_ref,
                )
                db.session.add(payment)
                db.session.commit()
                logger.info("Recorded payment flw_ref=%s tx_ref=%s amount=%s", flw_ref, tx_ref, amount)
            else:
                logger.info("Duplicate payment ignored flw_ref=%s tx_ref=%s", flw_ref, tx_ref)

            # Activate subscription only if account_ref contains PLAN-
            if not account_ref or "PLAN-" not in account_ref:
                logger.info("No PLAN reference in account_ref=%s; skipping subscription activation", account_ref)
                return jsonify({"status": "success", "message": "payment recorded"}), 200

            # Lookup user by phone (assumes login_phone stored in same normalized format)
            user = None
            if msisdn:
                user = User.query.filter_by(login_phone=msisdn).first()
            if not user:
                logger.warning("No user found for phone %s; subscription not activated", msisdn)
                return jsonify({"status": "success", "message": "payment recorded"}), 200

            # Parse plan id from account_ref (expecting "PLAN-<id>")
            try:
                plan_id = int(account_ref.split("PLAN-")[1])
            except Exception:
                logger.error("Invalid PLAN reference: %s", account_ref)
                return jsonify({"status": "success", "message": "payment recorded"}), 200

            plan = Plan.query.get(plan_id)
            if not plan:
                logger.error("Plan not found: %s", plan_id)
                return jsonify({"status": "success", "message": "payment recorded"}), 200

            # Deactivate previous active subscriptions for this user
            try:
                Subscription.query.filter_by(user_id=user.id, is_active=True).update({"is_active": False})
                db.session.flush()
            except Exception:
                logger.exception("Failed to deactivate previous subscriptions")

            expires_at = datetime.utcnow() + timedelta(days=plan.duration_days)

            subscription = Subscription(
                user_id=user.id,
                plan_id=plan.id,
                plan_name=plan.name,
                properties_allowed=plan.max_properties,
                amount_paid=amount,
                mpesa_receipt=tx_ref or (data.get("id") or ""),
                is_active=True,
                created_at=datetime.utcnow(),
                expires_at=expires_at,
            )

            db.session.add(subscription)
            db.session.commit()

            logger.info("SUBSCRIPTION ACTIVATED → user=%s plan=%s", user.id, plan.id)
            return jsonify({"status": "success", "message": "subscription activated"}), 200

        except Exception:
            logger.exception("Error handling charge.completed webhook")
            return jsonify({"status": "error", "message": "processing error"}), 200

    # Ignore other events
    return jsonify({"status": "ignored"}), 200
