import requests
from flask import current_app

def create_intasend_payment(
    *,
    amount,
    phone,
    email,
    reference,
    redirect_url,
    description,
):
    payload = {
        "public_key": current_app.config["INTASEND_PUBLIC_KEY"],
        "amount": float(amount),
        "currency": "KES",
        "email": email,
        "phone_number": phone,
        "redirect_url": redirect_url,
        "description": description,
        "reference": reference,
    }

    response = requests.post(
        f"{current_app.config['INTASEND_BASE_URL']}/checkout/",
        json=payload,
        timeout=30,
    )

    response.raise_for_status()
    return response.json()
