from flask_wtf.csrf import CSRFProtect
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ---------------------------
    # Core
    # ---------------------------
    SECRET_KEY = os.getenv("SECRET_KEY")
    FLASK_ENV = os.getenv("FLASK_ENV", "production")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ---------------------------
    # Security
    # ---------------------------
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    # ---------------------------
    # Email
    # ---------------------------
    MAILAPI_KEY = os.getenv("MAIL_API_KEY")
    EMAIL_FROM = os.getenv("EMAIL_FROM")
    BASE_URL = os.getenv("BASE_URL")

    # ---------------------------
    # MPesa
    # ---------------------------
    MPESA_ENV = os.getenv("MPESA_ENV", "sandbox")
    CALLBACK_BASE = os.getenv("MPESA_CALLBACK")

    # ---------------------------
    # Flutterwave
    # ---------------------------
    FLW_SECRET_KEY = os.getenv("FLW_SECRET_KEY")
    FLW_PUBLIC_KEY = os.getenv("FLW_PUBLIC_KEY")
    FLW_WEBHOOK_SECRET = os.getenv("FLW_WEBHOOK_SECRET")
    FLW_BASE_URL = os.getenv("FLW_BASE_URL", "https://api.flutterwave.com/v3")

    # ---------------------------
    # IntaSend ✅ SINGLE SOURCE
    # ---------------------------
    INTASEND_ENV = os.getenv("INTASEND_ENV", "live")

    INTASEND_PUBLIC_KEY = os.getenv("INTASEND_PUBLIC_KEY")
    INTASEND_SECRET_KEY = os.getenv("INTASEND_SECRET_KEY")

    INTASEND_BASE_URL = (
        "https://sandbox.intasend.com/api/v1"
        if INTASEND_ENV == "sandbox"
        else "https://api.intasend.com/api/v1"
    )

