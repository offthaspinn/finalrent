import requests
from flask import current_app


def create_intasend_payment(
    *,
    amount,
    email,
    phone,
    api_ref,
    redirect_url,
    description="Subscription payment",
):
    base_url = current_app.config.get("INTASEND_BASE_URL")
    public_key = current_app.config.get("INTASEND_PUBLIC_KEY")

    if not base_url or not public_key:
        raise RuntimeError("IntaSend public key missing")

    payload = {
        "public_key": public_key,
        "amount": float(amount),
        "currency": "KES",
        "email": email,
        "phone_number": phone,
        "api_ref": api_ref,        # stored in DB
        "redirect_url": redirect_url,
        "description": description,
    }

    response = requests.post(
        f"{base_url}/checkout/",
        json=payload,
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
        f"INTASEND CHECKOUT [{response.status_code}]: {data}"
    )

    return data