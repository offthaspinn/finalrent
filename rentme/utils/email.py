import logging
import requests
from typing import Optional
from flask import current_app

log = logging.getLogger(__name__)

def send_reset_email(
    to_email: str, token: str, subject: Optional[str] = None, body: Optional[str] = None
) -> bool:
    api_key = current_app.config.get("MAILAPI_KEY")
    email_from = current_app.config.get("EMAIL_FROM")
    base_url = current_app.config.get("BASE_URL", "").rstrip("/")

    if not api_key or not email_from or not base_url:
        log.error("Mail API configuration missing")
        return False

    reset_link = f"{base_url}/reset_password/{token}"

    if not subject:
        subject = "Password Reset"

    if not body:
        body = f"""Hello,

You requested a password reset.

Reset your password using the link below:
{reset_link}

This link expires in 1 hour.

— Rentana Team
"""

    try:
        res = requests.post(
            "https://api.mailapi.dev/send",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"from": email_from, "to": to_email, "subject": subject, "text": body},
            timeout=10,
        )

        return res.status_code in (200, 202)

    except Exception as e:
        log.exception("MailAPI exception: %s", e)
        return False
