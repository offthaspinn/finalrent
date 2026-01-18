import logging
from flask import current_app

log = logging.getLogger(__name__)

def send_sms_via_africastalking(phone_number: str, message: str) -> bool:
    username = current_app.config.get("AFRICASTALKING_USERNAME")
    api_key = current_app.config.get("AFRICASTALKING_API_KEY")

    if not username or not api_key:
        log.warning("Africa's Talking not configured")
        return False

    try:
        import africastalking as at_sdk
        at = at_sdk.initialize(username=username, api_key=api_key)
        at.SMS.send(message=message, to=[phone_number])
        return True
    except Exception as e:
        log.exception("AT SMS failed: %s", e)
        return False


def send_sms_via_twilio(phone_number: str, message: str) -> bool:
    sid = current_app.config.get("TWILIO_SID")
    token = current_app.config.get("TWILIO_TOKEN")
    sender = current_app.config.get("TWILIO_FROM")

    if not sid or not token or not sender:
        return False

    try:
        from twilio.rest import Client
        Client(sid, token).messages.create(
            body=message, from_=sender, to=phone_number
        )
        return True
    except Exception:
        log.exception("Twilio SMS failed")
        return False
