# intasend_core.py
import os
import requests
import logging

INTASEND_BASE_URL = "https://api.intasend.com/api/v1"
INTASEND_PUBLIC_KEY = os.getenv("INTASEND_PUBLIC_KEY")  # ✅ USE PUBLIC KEY

logger = logging.getLogger("intasend")

def create_intasend_invoice(
    *,
    amount: float,
    reference: str,
    phone: str | None = None,
    email: str | None = None,
    description: str = "Rent Payment",
):
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")

    payload = {
        "amount": float(amount),
        "currency": "KES",
        "reference": reference,
        "description": description,
    }

    if phone:
        payload["phone_number"] = phone

    if email:
        payload["email"] = email

    logger.info("📨 Creating IntaSend invoice: %s", payload)

    response = requests.post(
        f"{INTASEND_BASE_URL}/checkout/",
        json=payload,
        headers={
            "Authorization": f"Bearer {INTASEND_PUBLIC_KEY}",  # ✅ FIX
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
