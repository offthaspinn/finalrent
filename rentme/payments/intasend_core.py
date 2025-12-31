import requests
from flask import current_app


def create_intasend_payment(
    *,
    amount,
    email,
    phone,
    tx_ref,
    redirect_url,
    description="Subscription payment",
):
    base_url = current_app.config["INTASEND_BASE_URL"]
    public_key = current_app.config["INTASEND_PUBLIC_KEY"]

    if not public_key:
        raise RuntimeError("IntaSend public key not set")

    payload = {
        "public_key": public_key,
        "amount": float(amount),
        "currency": "KES",
        "email": email,
        "phone_number": phone,
        "api_ref": tx_ref,
        "redirect_url": redirect_url,
        "description": description,
    }

    response = requests.post(
        f"{base_url}/checkout/",
        json=payload,
        timeout=30,
    )

    data = response.json()
    current_app.logger.info(f"INTASEND RESPONSE: {data}")
    return data
