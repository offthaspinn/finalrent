# kcb_core.py
# Core KCB Paybill logic (sandbox/live)

import os
import requests
import json
from datetime import datetime

KCB_BASE_URL = os.getenv("KCB_BASE_URL", "https://sandbox.kcbgroup.com/mpesa")
KCB_API_KEY = os.getenv("KCB_API_KEY")
KCB_PAYBILL = os.getenv("KCB_PAYBILL", "600000")
KCB_CALLBACK_URL = os.getenv("KCB_CALLBACK_URL", "https://yourdomain.com/kcb_callback")

def _get_headers():
    """Return default headers for KCB API requests."""
    return {
        "Authorization": f"Bearer {KCB_API_KEY}",
        "Content-Type": "application/json",
    }

def initiate_stk_push(phone, amount, account_reference, transaction_desc):
    """
    Initiates a KCB Paybill STK Push / mobile payment.
    """
    payload = {
        "paybillNumber": KCB_PAYBILL,
        "amount": int(amount),
        "phoneNumber": phone,
        "accountReference": account_reference,
        "transactionDesc": transaction_desc,
        "callbackUrl": KCB_CALLBACK_URL,
        "timestamp": datetime.utcnow().isoformat(),
    }

    url = f"{KCB_BASE_URL}/stkpush"
    try:
        resp = requests.post(url, headers=_get_headers(), json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print("KCB STK Push error:", e)
        return {"error": str(e)}

def simulate_payment(phone, amount, account_reference="Rentana", description="Test Payment"):
    """Simulate a payment in sandbox mode."""
    print(f"📲 Simulating KCB payment: {phone} -> {amount} ({account_reference})")
    return {
        "MerchantRequestID": "KCB123456",
        "CheckoutRequestID": "KCB67890",
        "ResponseCode": "0",
        "ResponseDescription": "Success. Request accepted for processing",
        "CustomerMessage": "Success. Payment simulated.",
    }
