import logging
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import current_app
from typing import Optional

log = logging.getLogger(__name__)

def generate_reset_token(email: str) -> str:
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return s.dumps(email, salt="password-reset-salt")


def verify_reset_token(token: str, max_age: int = 3600) -> Optional[str]:
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        return s.loads(token, salt="password-reset-salt", max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
