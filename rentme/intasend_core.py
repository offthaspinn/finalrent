from flask import current_app
import requests
import logging

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

    base_url = current_app.config["INTASEND_BASE_URL"]
    public_key = current_app.config["INTASEND_PUBLIC_KEY"]

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

    response = requests.post(
        f"{base_url}/checkout/",
        json=payload,
        headers={
            "Authorization": f"Bearer {public_key}",
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
