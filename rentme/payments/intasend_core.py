import requests
from flask import current_app


def create_intasend_payment(
    *,
    amount,
    email,
    phone,
    invoice_id,
    redirect_url,
    description="Subscription payment",
):
    base_url = current_app.config["INTASEND_BASE_URL"]
    secret_key = current_app.config["INTASEND_SECRET_KEY"]

    payload = {
        "amount": float(amount),
        "currency": "KES",
        "email": email,
        "phone_number": phone,
        "invoice_id": invoice_id,  # ✅ documented
        "redirect_url": redirect_url,
        "description": description,
    }

    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        f"{base_url}/payment/mpesa/",
        json=payload,
        headers=headers,
        timeout=30,
    )

    try:
        data = response.json()
    except Exception:
        current_app.logger.error(
            f"IntaSend non-JSON response: {response.text}"
        )
        return None

    current_app.logger.info(
        f"INTASEND RESPONSE [{response.status_code}]: {data}"
    )

    if response.status_code not in (200, 201):
        return None

    return data