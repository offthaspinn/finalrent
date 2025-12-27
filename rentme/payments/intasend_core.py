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
    base_url = current_app.config.get(
        "INTASEND_BASE_URL",
        "https://sandbox.intasend.com/api/v1"
    )

    public_key = current_app.config.get("INTASEND_PUBLIC_KEY")
    secret_key = current_app.config.get("INTASEND_SECRET_KEY")

    if not public_key or not secret_key:
        raise RuntimeError("IntaSend keys not set")

    payload = {
        "public_key": public_key,
        "amount": amount,
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
        headers={
            "X-IntaSend-Secret-Key": secret_key,
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    return response.json()
