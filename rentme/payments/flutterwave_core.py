import requests
from flask import current_app


def create_flutterwave_payment(
    *,
    amount,
    email,
    phone,
    tx_ref,
    redirect_url,
    description="Subscription payment",
):
    """
    Initiates a Flutterwave payment
    """

    base_url = current_app.config.get(
        "FLW_BASE_URL",
        "https://api.flutterwave.com/v3"
    )

    secret_key = current_app.config.get("FLW_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("FLW_SECRET_KEY is not set")

    payload = {
        "tx_ref": tx_ref,
        "amount": amount,
        "currency": "KES",
        "redirect_url": redirect_url,
        "customer": {
            "email": email,
            "phonenumber": phone,
        },
        "customizations": {
            "title": "Rentana Subscription",
            "description": description,
        },
    }

    response = requests.post(
        f"{base_url}/payments",
        json=payload,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    return response.json()
