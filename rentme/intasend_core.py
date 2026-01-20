# rentme/intasend_core.py
import logging
import requests
from flask import current_app

logger = logging.getLogger("intasend")

def create_intasend_invoice(
    *,
    amount: float,
    reference: str,
    email: str,
    first_name: str,
    last_name: str,
    description: str = "Rent Payment",
):
    
    first_name = (first_name or "Customer").strip()
    last_name = (last_name or "User").strip()

    payload = {
        "amount": float(amount),
        "currency": "KES",
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "api_ref": reference,
        "redirect_url": f"{current_app.config['BASE_URL']}/subscriptions/complete",
        "description": description,
    }

    logger.info("📨 Creating IntaSend invoice: %s", payload)
    logger.info(
        "🔐 Using IntaSend PUBLIC key prefix: %s",
        current_app.config["INTASEND_PUBLIC_KEY"][:12],
    )

    response = requests.post(
        f"{current_app.config['INTASEND_BASE_URL']}/checkout/",
        json=payload,
        headers={
            "X-IntaSend-Public-Key": current_app.config["INTASEND_PUBLIC_KEY"],
            "Content-Type": "application/json",
        },
        timeout=20,
    )

    if not response.ok:
        logger.error("❌ IntaSend error response: %s", response.text)

    response.raise_for_status()
    data = response.json()

    return {
        "invoice_id": data["id"],
        "payment_url": data["url"],
        "reference": reference,
        "amount": amount,
    }
