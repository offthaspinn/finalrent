# mpesa_handler.py — FINAL (Live-only; multi-tenant aware)
# Save as mpesa_handler.py in project root
# This file expects environment variables to be set for Daraja & Twilio
# and an existing Flask app that registers the `mpesa_bp` blueprint.

import os
import sys
import json
import time
import logging
import sqlite3
import traceback
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Optional
from rentme.models import User, Tenant, LandlordSettings
from rentme.mpesa_core import initiate_stk_push
from rentme.models import Payment
from rentme.extensions import db

import requests
from flask import Blueprint, request, jsonify, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Optional imports from your project (ORM path)
try:
    from rentme.extensions import db, socketio
    from rentme.models import Tenant, Payment, User, LandlordSettings

    _USE_ORM = True
except Exception:
    # Fallback raw DB helpers will be used
    db = None
    socketio = None
    Tenant = None
    Payment = None
    User = None
    LandlordSettings = None
    _USE_ORM = False

# Twilio optional
try:
    from twilio.rest import Client as TwilioClient

    TWILIO_AVAILABLE = True
except Exception:
    TWILIO_AVAILABLE = False

# Postgres optional
try:
    import psycopg2
    import psycopg2.extras
    from psycopg2 import IntegrityError as PGIntegrityError

    PSYCOPG2_AVAILABLE = True
except Exception:
    psycopg2 = None
    PGIntegrityError = None
    PSYCOPG2_AVAILABLE = False


# Blueprint
mpesa_bp = Blueprint("mpesa_bp", __name__)

SAFARICOM_IPS = {
    "196.201.214.200",
    "196.201.214.206",
    "196.201.213.114",
    "196.201.213.44",
}

def _is_safaricom_ip(req):
    ip = req.headers.get("X-Forwarded-For", "").split(",")[0] or req.remote_addr
    return ip in SAFARICOM_IPS


# Logging
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LOG_FILE = os.path.join(BASE_DIR, "mpesa.log")
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

# DB / paths
DB_URL = os.getenv("DATABASE_URL")
DB_SQLITE_PATH = os.path.join(BASE_DIR, "rentana_full.db")
RECEIPT_DIR = os.path.join(BASE_DIR, "static", "receipts")
os.makedirs(RECEIPT_DIR, exist_ok=True)

_USE_PG = bool(
    DB_URL
    and DB_URL.startswith(("postgres://", "postgresql://"))
    and PSYCOPG2_AVAILABLE
)

# Daraja config (user should supply DARAJA_CONSUMER_KEY/SECRET and optional DARAJA_ENV)
DARAJA_CONSUMER_KEY = os.getenv("DARAJA_CONSUMER_KEY")
DARAJA_CONSUMER_SECRET = os.getenv("DARAJA_CONSUMER_SECRET")
DARAJA_ENV = os.getenv("DARAJA_ENV", "production").lower()
DARAJA_BASE = (
    "https://api.safaricom.co.ke"
    if DARAJA_ENV == "production"
    else "https://sandbox.safaricom.co.ke"
)
_OAUTH_TOKEN_CACHE = {"token": None, "expiry": 0}

# Twilio
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM")

# Default paybill/shortcode fallback
DEFAULT_PAYBILL = os.getenv("DEFAULT_PAYBILL", os.getenv("SANDBOX_SHORTCODE", "600000"))

# MPESAAAAA ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;; LIVE
MPESA_LIVE = os.getenv("MPESA_LIVE", "0") == "1"


# csrf_---------------------------------------
def csrf_exempt(view):
    """Simple decorator to mark a route as CSRF-exempt."""
    view.csrf_exempt = True
    return view

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[]
)



# -------------------------
# DB connections & helpers
# -------------------------


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


def _norm_phone_db(p: Optional[str]) -> str:
    if not p:
        return ""
    digits = "".join(ch for ch in str(p) if ch.isdigit())
    if len(digits) == 10 and digits.startswith("0"):
        digits = "254" + digits[1:]
    if len(digits) == 9 and digits.startswith("7"):
        digits = "254" + digits
    return digits


def _normalize_msisdn(msisdn):
    if not msisdn:
        return None
    s = str(msisdn).strip()
    if s.startswith("+"):
        s = s[1:]
    s = s.replace(" ", "").replace("-", "")
    if s.startswith("254") and len(s) >= 12:
        return s
    if s.startswith("0") and len(s) == 10:
        return "254" + s[1:]
    if s.startswith("7") and len(s) == 9:
        return "254" + s
    return s

def stk_push(phone, amount, account_reference, transaction_desc):
    """
    Initiates an STK Push for subscriptions
    """

    response = initiate_stk_push(
        phone=phone,
        amount=amount,
        account_reference=account_reference,
        transaction_desc=transaction_desc,
    )

    # Save pending payment (awaiting callback)
    payment = Payment(
        transaction_id=response.get("CheckoutRequestID"),
        amount=amount,
        paid_at=datetime.utcnow(),
        note="Subscription payment",
        checkout_request_id=response.get("CheckoutRequestID"),
    )

    db.session.add(payment)
    db.session.commit()

    return response


def _tx_exists(conn, tx_id: str) -> bool:
    if not tx_id:
        return False
    cur = conn.cursor()
    try:
        if _USE_PG:
            cur.execute(
                "SELECT 1 FROM payment WHERE transaction_id = %s LIMIT 1", (tx_id,)
            )
            r = cur.fetchone()
            return bool(r)
        else:
            cur.execute(
                "SELECT 1 FROM payment WHERE transaction_id=? LIMIT 1", (tx_id,)
            )
            return cur.fetchone() is not None
    finally:
        try:
            cur.close()
        except Exception:
            pass


def find_owner_by_shortcode_orm(account_numeric: str):
    """Return the User object for a given paybill/till/send_money/phone number using ORM."""
    if not _USE_ORM or User is None or LandlordSettings is None:
        return None

    # First try LandlordSettings table
    ls = LandlordSettings.query.filter(
        (LandlordSettings.paybill_number == account_numeric)
        | (LandlordSettings.till_number == account_numeric)
        | (LandlordSettings.send_money_number == account_numeric)
    ).first()

    if ls:
        return User.query.filter_by(id=ls.user_id).first()

    # Fallback: match User table fields directly
    u = User.query.filter(
        (User.paybill_number == account_numeric)
        | (User.till_number == account_numeric)
        | (User.phone_number == account_numeric)
    ).first()

    return u


def _total_paid(conn, tenant_id):
    cur = conn.cursor()
    if _USE_PG:
        cur.execute(
            "SELECT COALESCE(SUM(amount),0) as total FROM payment WHERE tenant_id=%s",
            (tenant_id,),
        )
        r = cur.fetchone()
        return float(r["total"] or 0.0) if r else 0.0
    else:
        cur.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payment WHERE tenant_id=?",
            (tenant_id,),
        )
        r = cur.fetchone()
        return float(r[0] or 0.0) if r else 0.0


def _find_tenant_by_house_and_account(
    conn, house_no: Optional[str], account: str, msisdn: Optional[str] = None
):
    """
    Find tenant given:
      - house_no and account (account is the business short code / paybill / till / sendno)
      - if house_no is None, attempt to match by account (phone) or msisdn
    Returns dict with tenant fields or None.
    """
    account = (account or "").strip()
    cur = conn.cursor()

    # 1) If house_no provided -> we find owners with this account then tenant by house_no among them
    if house_no:
        house_no_l = house_no.strip().lower()
        if _USE_PG:
            # find owners who own the provided business code
            cur.execute(
                'SELECT id FROM "user" WHERE paybill_number=%s OR till_number=%s OR send_money_number=%s OR phone_number=%s',
                (account, account, account, account),
            )
            users = [r["id"] for r in cur.fetchall()]
            if not users:
                return None
            placeholders = ",".join(["%s"] * len(users))
            query = f"SELECT id, name, phone, house_no, monthly_rent, owner_id FROM tenant WHERE lower(house_no)=lower(%s) AND owner_id IN ({placeholders}) LIMIT 1"
            params = [house_no_l] + users
            cur.execute(query, params)
            r = cur.fetchone()
            if not r:
                return None
            return {
                "id": r["id"],
                "name": r["name"],
                "phone": r["phone"],
                "house_no": r["house_no"],
                "monthly_rent": float(r["monthly_rent"] or 0),
                "owner_id": r["owner_id"],
            }
        else:
            cur.execute(
                """SELECT id FROM "user" WHERE paybill_number=? OR till_number=? OR send_money_number=? OR phone_number=?""",
                (account, account, account, account),
            )
            users = [r[0] for r in cur.fetchall()]
            if not users:
                return None
            placeholders = ",".join("?" for _ in users)
            sql = f"""SELECT id, name, phone, house_no, monthly_rent, owner_id
                      FROM tenant WHERE lower(house_no)=? AND owner_id IN ({placeholders}) LIMIT 1"""
            params = [house_no.lower()] + users
            cur.execute(sql, params)
            r = cur.fetchone()
            if not r:
                return None
            tid, name, ph, hno, rent, owner_id = r
            return {
                "id": tid,
                "name": name,
                "phone": ph,
                "house_no": hno,
                "monthly_rent": rent or 0.0,
                "owner_id": owner_id,
            }

    # Subscription------------------------------------------------------------

    # 2) No house_no -> attempt to find tenant by phone matching the account or msisdn
    # first try account as phone
    if account:
        acct_norm = "".join(ch for ch in account if ch.isdigit())
        if acct_norm:
            acct_like = f"%{acct_norm[-6:]}%"
            if _USE_PG:
                cur.execute(
                    "SELECT id, name, phone, house_no, monthly_rent, owner_id FROM tenant WHERE phone LIKE %s LIMIT 1",
                    (acct_like,),
                )
                r = cur.fetchone()
                if r:
                    return {
                        "id": r["id"],
                        "name": r["name"],
                        "phone": r["phone"],
                        "house_no": r["house_no"],
                        "monthly_rent": float(r["monthly_rent"] or 0),
                        "owner_id": r["owner_id"],
                    }
            else:
                cur.execute(
                    "SELECT id, name, phone, house_no, monthly_rent, owner_id FROM tenant WHERE phone LIKE ? LIMIT 1",
                    (acct_like,),
                )
                r = cur.fetchone()
                if r:
                    tid, name, ph, hno, rent, owner_id = r
                    return {
                        "id": tid,
                        "name": name,
                        "phone": ph,
                        "house_no": hno,
                        "monthly_rent": rent or 0.0,
                        "owner_id": owner_id,
                    }

    # 3) Try msisdn if provided
    if msisdn:
        m_norm = _normalize_msisdn(msisdn)
        if m_norm:
            mlike = f"%{m_norm[-6:]}%"
            if _USE_PG:
                cur.execute(
                    "SELECT id, name, phone, house_no, monthly_rent, owner_id FROM tenant WHERE phone LIKE %s LIMIT 1",
                    (mlike,),
                )
                r = cur.fetchone()
                if r:
                    return {
                        "id": r["id"],
                        "name": r["name"],
                        "phone": r["phone"],
                        "house_no": r["house_no"],
                        "monthly_rent": float(r["monthly_rent"] or 0),
                        "owner_id": r["owner_id"],
                    }
            else:
                cur.execute(
                    "SELECT id, name, phone, house_no, monthly_rent, owner_id FROM tenant WHERE phone LIKE ? LIMIT 1",
                    (mlike,),
                )
                r = cur.fetchone()
                if r:
                    tid, name, ph, hno, rent, owner_id = r
                    return {
                        "id": tid,
                        "name": name,
                        "phone": ph,
                        "house_no": hno,
                        "monthly_rent": rent or 0.0,
                        "owner_id": owner_id,
                    }

    return None


def _insert_payment(conn, tenant_id, amount, tx_id, note=None):
    now = datetime.utcnow().isoformat(timespec="seconds")
    cur = conn.cursor()
    try:
        if _USE_PG:
            cur.execute(
                "INSERT INTO payment (tenant_id, amount, transaction_id, note, paid_at, created_at) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (tenant_id, float(amount), tx_id, note, now, now),
            )
            new_id = cur.fetchone()["id"]
            conn.commit()
            return new_id
        else:
            cur.execute(
                """INSERT INTO payment (tenant_id, amount, transaction_id, note, paid_at, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (tenant_id, float(amount), tx_id, note, now, now),
            )
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        conn.rollback()
        text = str(e).lower()
        if (
            "unique" in text
            or "duplicate" in text
            or isinstance(e, sqlite3.IntegrityError)
            or (PGIntegrityError and isinstance(e, PGIntegrityError))
        ):
            logger.warning("Integrity error / duplicate tx ignored: %s", tx_id)
            return None
        else:
            logger.exception("Unexpected error inserting payment: %s", e)
            raise


# -------------------------
# Receipts (simple file)
# -------------------------


def _create_pdf_receipt(tenant, amount, tx_id, remaining):
    filename = f"receipt_{tenant['id']}_{tx_id}.pdf"
    out = os.path.join(RECEIPT_DIR, filename)
    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write(
                f"Tenant {tenant.get('name') or tenant['id']} | {tenant.get('house_no','-')}\n"
            )
            f.write(f"Amount {amount}\nTx {tx_id}\nBalance {remaining}\n")
        return out
    except Exception:
        logger.exception("Error creating receipt")
        return None


# -------------------------
# Twilio SMS helper
# -------------------------


def _send_sms(phone, message):
    if not (TWILIO_AVAILABLE and TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM):
        logger.info("SMS not sent (Twilio not configured). Preview: %s", message)
        return
    try:
        client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(body=message, from_=TWILIO_FROM, to=phone)
        logger.info("SMS sent to %s", phone)
    except Exception:
        logger.exception("Twilio error when sending SMS")


# -------------------------
# Daraja oauth & verify
# -------------------------


def _get_oauth_token() -> Optional[str]:
    if not (DARAJA_CONSUMER_KEY and DARAJA_CONSUMER_SECRET):
        logger.warning("Daraja credentials not configured.")
        return None
    now_ts = int(time.time())
    if _OAUTH_TOKEN_CACHE["token"] and _OAUTH_TOKEN_CACHE["expiry"] - now_ts > 30:
        return _OAUTH_TOKEN_CACHE["token"]
    url = f"{DARAJA_BASE}/oauth/v1/generate?grant_type=client_credentials"
    try:
        resp = requests.get(
            url, auth=(DARAJA_CONSUMER_KEY, DARAJA_CONSUMER_SECRET), timeout=10
        )
        j = resp.json()
        token = j.get("access_token")
        expires_in = int(j.get("expires_in", 3600))
        _OAUTH_TOKEN_CACHE["token"] = token
        _OAUTH_TOKEN_CACHE["expiry"] = now_ts + expires_in
        logger.info("Got Daraja oauth token (masked)")
        return token
    except Exception:
        logger.exception("Daraja token fetch failed")
        return None


def verify_transaction_with_daraja(
    transaction_id: str, amount: float, msisdn: str, shortcode: str
) -> bool:
    """Attempt to confirm the transaction via Daraja TransactionStatusQuery.
    Note: This endpoint is subject to your Daraja account permissions.
    """
    token = _get_oauth_token()
    if not token:
        logger.debug("Daraja token unavailable; verification skipped")
        return False
    url = f"{DARAJA_BASE}/mpesa/transactionstatus/v1/query"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "CommandID": "TransactionStatusQuery",
        "PartyA": shortcode,
        "IdentifierType": "4",
        "Remarks": "verify",
        "Initiator": os.getenv("DARAJA_INITIATOR", "testapi"),
        "SecurityCredential": os.getenv("DARAJA_SECURITY_CREDENTIAL", ""),
        "TransactionID": transaction_id,
        "Occasion": "verify",
    }
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=12)
        if resp.status_code not in (200, 201):
            logger.error(
                "Daraja verify failed HTTP %s: %s", resp.status_code, resp.text
            )
            return False
        resp_text = str(resp.text).lower()
        return any(k in resp_text for k in ["completed", "success", "accepted"])
    except Exception:
        logger.exception("Daraja verify exception")
        return False


# -------------------------
# Core processing for fallback (non-ORM) and ORM-aware
# -------------------------

# -------------------------
# Core processing (ORM-first, fallback-safe)
# -------------------------


def process_payment_orm(
    account: str,
    amount: float,
    tx_id: str,
    note: str = None,
    msisdn: str = None,
):
    """
    Process an M-Pesa payment via ORM (LIVE, idempotent, multi-tenant aware)
    """

    from datetime import datetime
    from rentme.extensions import db

    # --------------------------------------------------
    # 1. IDEMPOTENCY (DO NOT DUPLICATE PAYMENTS)
    # --------------------------------------------------
    existing = Payment.query.filter_by(transaction_id=tx_id).first()
    if existing:
        logger.warning("Duplicate transaction ignored → %s", tx_id)
        return {
            "ok": True,
            "duplicate": True,
            "payment_id": existing.id,
        }

    account_ref = (account or "").strip()
    house_no = None

    # --------------------------------------------------
    # 2. PARSE ACCOUNT REFERENCE
    # Format: PAYBILL#H034
    # --------------------------------------------------
    if "#" in account_ref:
        business_code, house_no = account_ref.split("#", 1)
        business_code = business_code.strip()
        house_no = house_no.strip()
    else:
        business_code = account_ref or DEFAULT_PAYBILL

    # --------------------------------------------------
    # 3. RESOLVE OWNER (LANDLORD)
    # --------------------------------------------------
    owner = None

    if LandlordSettings:
        ls = LandlordSettings.query.filter(
            (LandlordSettings.paybill_number == business_code)
            | (LandlordSettings.till_number == business_code)
            | (LandlordSettings.send_money_number == business_code)
        ).first()
        if ls:
            owner = User.query.get(ls.user_id)

    if not owner:
        owner = User.query.filter(
            (User.paybill_number == business_code)
            | (User.till_number == business_code)
            | (User.phone_number == business_code)
        ).first()

    # --------------------------------------------------
    # 4. RESOLVE TENANT
    # --------------------------------------------------
    tenant = None

    if owner and house_no:
        tenant = Tenant.query.filter_by(
            owner_id=owner.id,
            house_no=house_no,
            is_active=True,
        ).first()

    if not tenant and owner and msisdn:
        last6 = _normalize_msisdn(msisdn)[-6:]
        tenant = Tenant.query.filter(
            Tenant.owner_id == owner.id,
            Tenant.phone.like(f"%{last6}%"),
        ).first()

    if not tenant and msisdn:
        last6 = _normalize_msisdn(msisdn)[-6:]
        tenant = Tenant.query.filter(
            Tenant.phone.like(f"%{last6}%")
        ).first()

    if not tenant:
        logger.warning("Tenant not found → tx=%s account=%s", tx_id, account_ref)
        return {"ok": False, "reason": "tenant_not_found"}

    # --------------------------------------------------
    # 5. RECORD PAYMENT
    # --------------------------------------------------
    payment = Payment(
        transaction_id=tx_id,
        tenant_id=tenant.id,
        amount=float(amount),
        reference=account_ref,
        paid_at=datetime.utcnow(),
        note=note or "M-Pesa confirmation",
        verified=True,  # webhook is trusted
    )

    try:
        db.session.add(payment)

        # Apply payment to tenant balance
        tenant.balance = (tenant.balance or 0) - float(amount)
        tenant.last_payment_at = datetime.utcnow()

        db.session.commit()

    except Exception:
        db.session.rollback()
        logger.exception("Payment insert failed → %s", tx_id)
        return {"ok": False, "reason": "insert_failed"}

    # --------------------------------------------------
    # 6. NOTIFICATIONS
    # --------------------------------------------------
    try:
        _send_sms(
            tenant.phone,
            f"Dear {tenant.name}, payment of Ksh {int(amount):,} received. Thank you.",
        )
    except Exception:
        logger.exception("SMS failed")

    if socketio:
        socketio.emit(
            "payment_update",
            {
                "tenant_id": tenant.id,
                "amount": amount,
                "tx_id": tx_id,
            },
            broadcast=True,
        )

    # --------------------------------------------------
    # 7. RECEIPT
    # --------------------------------------------------
    receipt = _create_pdf_receipt(
        tenant=tenant,
        amount=amount,
        tx_id=tx_id,
        remaining=tenant.balance,
    )

    return {
        "ok": True,
        "payment_id": payment.id,
        "tenant_id": tenant.id,
        "amount": amount,
        "tx_id": tx_id,
        "receipt": receipt,
    }

# -------------------------
# -------------------------
# HTTP callback endpoints
# -------------------------
# HTTP callback endpoints
# -------------------------

@mpesa_bp.route("/payment_callback/validate", methods=["POST"])
@csrf_exempt  # ✅ Required for Daraja callbacks
def mpesa_validate():
    """Daraja calls this to validate before completing the payment."""
    data = request.get_json(silent=True) or {}
    logger.info("VALIDATION payload: %s", data)

    bill_ref = (
        data.get("BillRefNumber")
        or data.get("AccountReference")
        or data.get("BillRef")
        or ""
    ).strip()

    owner_id = data.get("OwnerID") or data.get("owner_id") or data.get("UserID")

    # Resolve owner via shortcode if missing
    if not owner_id:
        shortcode = (
            data.get("ShortCode")
            or data.get("BusinessShortCode")
            or data.get("Shortcode")
            or ""
        ).strip()

        if shortcode and _USE_ORM and LandlordSettings:
            try:
                ls = LandlordSettings.query.filter(
                    (LandlordSettings.paybill_number == shortcode)
                    | (LandlordSettings.till_number == shortcode)
                    | (LandlordSettings.send_money_number == shortcode)
                ).first()
                if ls:
                    owner_id = ls.user_id
            except Exception:
                logger.exception("ORM shortcode lookup failed")

    if not owner_id:
        logger.warning("Validation failed: missing OwnerID")
        return jsonify({"ResultCode": 1, "ResultDesc": "Missing OwnerID"}), 200

    # Fetch owner
    owner = None
    if _USE_ORM and User:
        owner = User.query.get(owner_id)
        if not owner:
            logger.warning("Validation failed: invalid owner %s", owner_id)
            return jsonify({"ResultCode": 1, "ResultDesc": "Invalid Owner"}), 200

    # Find tenant
    tenant = None
    if _USE_ORM and Tenant and bill_ref:
        tenant = Tenant.query.filter_by(owner_id=owner.id, house_no=bill_ref).first()

        if not tenant and bill_ref.isdigit():
            tenant = Tenant.query.filter(
                Tenant.owner_id == owner.id, Tenant.phone.like(f"%{bill_ref}%")
            ).first()

    if tenant:
        logger.info("Validation passed: owner=%s tenant=%s", owner_id, tenant.name)
        return jsonify({"ResultCode": 0, "ResultDesc": "Validation Passed"}), 200

    logger.warning("Validation failed: bill_ref=%s owner=%s", bill_ref, owner_id)
    return jsonify({"ResultCode": 1, "ResultDesc": "Invalid tenant reference"}), 200


# --------------------------------------------------------------------
# CONFIRMATION ENDPOINT  (🔥 FIXED VERSION)
# --------------------------------------------------------------------

@limiter.limit("10/minute")
@mpesa_bp.route("/payment_callback/confirmation", methods=["POST"])
@csrf_exempt
def mpesa_confirmation():
    """
    Daraja payment confirmation endpoint.
    Records payment AND activates subscription.
    """
    from datetime import datetime, timedelta
    from flask import request, jsonify
    from rentme.models import (
        User,
        Subscription,
        Plan,
        SubscriptionIntent   # 👈 ADD THIS MODEL
    )
    from rentme.extensions import db

    payload = request.get_json(silent=True) or {}
    logger.info("M-PESA CONFIRMATION PAYLOAD: %s", payload)

    body = payload.get("Body", payload)
    stk = body.get("stkCallback")

    try:
        # ------------------------------------------------
        # 1. PARSE PAYMENT DATA
        # ------------------------------------------------
        if stk:
            items = stk.get("CallbackMetadata", {}).get("Item", [])
            data = {i["Name"]: i.get("Value") for i in items if isinstance(i, dict)}

            tx_id = data.get("MpesaReceiptNumber") or stk.get("CheckoutRequestID")
            amount = float(data.get("Amount", 0))
            phone = data.get("PhoneNumber")
            account_ref = stk.get("AccountReference")
        else:
            tx_id = (
                body.get("MpesaReceiptNumber")
                or body.get("TransID")
                or body.get("TransactionID")
            )
            amount = float(body.get("Amount", 0))
            phone = body.get("MSISDN") or body.get("Msisdn")
            account_ref = body.get("BillRefNumber")

        if not tx_id or amount <= 0:
            logger.warning("Invalid confirmation payload")
            return jsonify({"ResultCode": 1, "ResultDesc": "Invalid data"}), 200

        msisdn = _normalize_msisdn(phone)

        # ------------------------------------------------
        # 2. VERIFY WITH DARAJA (NON-BLOCKING)
        # ------------------------------------------------
        try:
            verify_transaction_with_daraja(
                tx_id=str(tx_id),
                amount=amount,
                msisdn=msisdn or "",
                account_ref=account_ref or ""
            )
        except Exception:
            logger.exception("Daraja verification failed (ignored)")

        # ------------------------------------------------
        # 3. RECORD PAYMENT
        # ------------------------------------------------
        try:
            result = process_payment_orm(
                account_ref=account_ref,
                amount=amount,
                transaction_id=str(tx_id),
                note="Daraja confirmation",
                msisdn=msisdn
            )
        except Exception:
            logger.exception("process_payment_orm failed")
            result = {"ok": False}

        # ------------------------------------------------
        # 4. ACTIVATE SUBSCRIPTION  🔥 FIXED LOGIC
        # ------------------------------------------------
        if result.get("ok"):
            user = User.query.filter_by(login_phone=msisdn).first()

            if not user:
                logger.warning("No user found for phone %s", msisdn)
                return jsonify({"ResultCode": 0, "ResultDesc": "Payment recorded"}), 200

            # ------------------------------------------------
            # 4A. FIND PENDING SUBSCRIPTION INTENT (BEST WAY)
            # ------------------------------------------------
            intent = SubscriptionIntent.query.filter_by(
                user_id=user.id,
                status="pending"
            ).order_by(SubscriptionIntent.created_at.desc()).first()

            plan = None

            if intent:
                plan = Plan.query.get(intent.plan_id)
            else:
                # ------------------------------------------------
                # 4B. SAFE FALLBACK (NO PLAN- REQUIRED)
                # ------------------------------------------------
                logger.warning("No subscription intent found. Using fallback plan.")
                plan = Plan.query.order_by(Plan.id.desc()).first()

            if not plan:
                logger.error("No plan found for activation")
                return jsonify({"ResultCode": 0, "ResultDesc": "Payment recorded"}), 200

            # ------------------------------------------------
            # 4C. DEACTIVATE OLD SUBSCRIPTIONS
            # ------------------------------------------------
            Subscription.query.filter_by(
                user_id=user.id,
                is_active=True
            ).update({"is_active": False})

            # ------------------------------------------------
            # 4D. CREATE NEW SUBSCRIPTION
            # ------------------------------------------------
            expires_at = datetime.utcnow() + timedelta(days=plan.duration_days)

            subscription = Subscription(
                user_id=user.id,
                plan_id=plan.id,
                plan_name=plan.name,
                properties_allowed=plan.max_properties,
                amount_paid=amount,
                mpesa_receipt=tx_id,
                is_active=True,
                created_at=datetime.utcnow(),
                expires_at=expires_at
            )

            db.session.add(subscription)

            if intent:
                intent.status = "completed"

            db.session.commit()

            logger.info(
                "SUBSCRIPTION ACTIVATED → user=%s plan=%s",
                user.id, plan.id
            )

            return jsonify({
                "ResultCode": 0,
                "ResultDesc": "Confirmation received successfully"
            }), 200

        # ------------------------------------------------
        # 5. SANDBOX FALLBACK
        # ------------------------------------------------
        if not MPESA_LIVE:
            logger.warning(
                "[SIMULATION] Payment accepted → %s %s",
                tx_id, amount
            )
            return jsonify({
                "ResultCode": 0,
                "ResultDesc": "Confirmation received (simulated)"
            }), 200

        # ------------------------------------------------
        # 6. LIVE FAILURE
        # ------------------------------------------------
        logger.error("LIVE payment failed → %s", tx_id)
        return jsonify({
            "ResultCode": 1,
            "ResultDesc": "Payment processing failed"
        }), 200

    except Exception:
        logger.exception("Fatal confirmation error")
        return jsonify({
            "ResultCode": 1,
            "ResultDesc": "Processing error"
        }), 200
