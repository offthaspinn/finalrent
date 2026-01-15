import requests
from flask import current_app


def create_intasend_payment(
    *,
    amount,
    phone,
    email,
    description,
    redirect_url,
    api_ref=None,
    reference=None,
):
    # Normalize reference
    ref = api_ref or reference
    if not ref:
        raise ValueError("Payment reference (api_ref) is required")

    payload = {
        "public_key": current_app.config["INTASEND_PUBLIC_KEY"],
        "amount": float(amount),
        "currency": "KES",
        "email": email,
        "phone_number": phone,
        "redirect_url": redirect_url,
        "description": description,
        "reference": ref,
    }

    response = requests.post(
        f"{current_app.config['INTASEND_BASE_URL']}/checkout/",
        json=payload,
        timeout=30,
    )

    response.raise_for_status()
    return response.json()