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
    """
    Create an IntaSend hosted checkout invoice.

    IMPORTANT:
    - Uses PUBLIC KEY (required for /checkout/)
    - Works in both sandbox & live
    """

    if amount <= 0:
        raise ValueError("Amount must be greater than zero")

    # Safety defaults (IntaSend requires names)
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

    base_url = current_app.config["INTASEND_BASE_URL"]
    public_key = current_app.config["INTASEND_PUBLIC_KEY"]

    logger.info("📨 Creating IntaSend invoice: %s", payload)
    logger.info("🔐 Using IntaSend PUBLIC key prefix: %s", public_key[:12])

    response = requests.post(
        f"{base_url}/checkout/",
        json=payload,
        headers={
            # ✅ REQUIRED for checkout
            "X-IntaSend-Public-Key": public_key,
            "Content-Type": "application/json",
        },
        timeout=20,
    )

    if not response.ok:
        logger.error("❌ IntaSend error response [%s]: %s", response.status_code, response.text)

    response.raise_for_status()
    data = response.json()

    return {
        "invoice_id": data.get("id"),
        "payment_url": data.get("url"),
        "reference": reference,
        "amount": amount,
    }
