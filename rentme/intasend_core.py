# intasend_core.py
# Core IntaSend payment initiation logic

import os
import requests
import logging

INTASEND_BASE_URL = "https://api.intasend.com/api/v1"
INTASEND_SECRET_KEY = os.getenv("INTASEND_SECRET_KEY")

logger = logging.getLogger("intasend")

# --------------------------------------------------
# Create payment invoice
# --------------------------------------------------

def create_intasend_invoice(
    *,
    amount: float,
    reference: str,
    phone_number: str | None = None,
    email: str | None = None,
    description: str = "Rent Payment",
):
    """
    Creates an IntaSend invoice and returns a payment URL.
    This is the ONLY way tenants initiate payment.
    """

    if amount <= 0:
        raise ValueError("Amount must be greater than zero")

    payload = {
        "amount": float(amount),
        "currency": "KES",
        "reference": reference,
        "description": description,
    }

    if phone_number:
        payload["phone_number"] = phone_number

    if email:
        payload["email"] = email

    logger.info("📨 Creating IntaSend invoice: %s", payload)

    response = requests.post(
        f"{INTASEND_BASE_URL}/checkout/",
        json=payload,
        headers={
            "Authorization": f"Bearer {INTASEND_SECRET_KEY}",
            "Content-Type": "application/json",
        },
        timeout=20,
    )

    response.raise_for_status()
    data = response.json()

    return {
        "invoice_id": data.get("invoice_id"),
        "payment_url": data.get("url"),
        "reference": reference,
        "amount": amount,
    }
