# mpesa_core.py
# Core M-Pesa logic placeholder (for testing sandbox)

import json


def process_direct_payment(
    amount, phone_number, account_reference="Rentana", description="Test Payment"
):
    """
    Simulates processing a direct M-Pesa payment for sandbox testing.
    """
    print(f"📲 Simulating payment: {phone_number} -> {amount} ({account_reference})")
    mock_response = {
        "MerchantRequestID": "12345-abcde",
        "CheckoutRequestID": "67890-fghij",
        "ResponseCode": "0",
        "ResponseDescription": "Success. Request accepted for processing",
        "CustomerMessage": "Success. Payment simulated.",
    }
    return mock_response


def initiate_stk_push(phone, amount, account_reference, transaction_desc):
    business_shortcode = "0114713717"  # POCHI / PAYBILL
    passkey = MPESA_PASSKEY

    timestamp = generate_timestamp()
    password = generate_password(
        business_shortcode,
        passkey,
        timestamp
    )

    payload = {
        "BusinessShortCode": business_shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": business_shortcode,
        "PhoneNumber": phone,
        "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": account_reference,
        "TransactionDesc": transaction_desc,
    }

    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        MPESA_STK_URL,
        json=payload,
        headers=headers,
        timeout=30,
    )

    return response.json()
