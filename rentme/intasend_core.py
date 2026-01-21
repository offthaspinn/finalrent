# rentme/intasend_core.py
import logging
import requests
from flask import current_app

logger = logging.getLogger("intasend")


def initiate_intasend_mpesa(
    *,
    amount: float,
    reference: str,
    phone_number: str,
    email: str,
    first_name: str,
    last_name: str,
    description: str = "Subscription Payment",
):
    """
    Initiate an IntaSend MPESA STK Push.

    IMPORTANT:
    - Uses SECRET KEY
    - No redirects
    - Webhook-driven completion
    """

    if amount <= 0:
        raise ValueError("Amount must be greater than zero")

    first_name = (first_name or "Customer").strip()
    last_name = (last_name or "User").strip()

    payload = {
        "amount": float(amount),
        "currency": "KES",
        "phone_number": phone_number,  # MUST be 2547XXXXXXXX
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "api_ref": reference,
        "comment": description,
        "callback_url": f"{current_app.config['BASE_URL']}/intasend/webhook",
    }

    base_url = current_app.config["INTASEND_BASE_URL"]
    secret_key = current_app.config["INTASEND_SECRET_KEY"]

    logger.info("📲 Initiating IntaSend MPESA STK: %s", payload)
    logger.info("🔐 Using IntaSend SECRET key prefix: %s", secret_key[:12])

    response = requests.post(
        f"{base_url}/payment/mpesa/",
        json=payload,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        },
        timeout=20,
    )

    if not response.ok:
        logger.error(
            "❌ IntaSend MPESA error [%s]: %s",
            response.status_code,
            response.text,
        )

    response.raise_for_status()
    return response.json()
