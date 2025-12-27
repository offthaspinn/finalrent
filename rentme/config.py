import os
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect

# Load .env file
load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    FLASK_ENV = "production"

    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAILAPI_KEY = os.environ.get("MAILAPI_KEY")
    EMAIL_FROM = os.environ.get("EMAIL_FROM")
    BASE_URL = os.environ.get("BASE_URL")

    MPESA_ENV = os.environ.get("MPESA_ENV", "sandbox")
    CALLBACK_BASE = os.environ.get("CALLBACK_BASE")

    FLW_SECRET_KEY = os.getenv("FLW_SECRET_KEY")
    FLW_PUBLIC_KEY = os.getenv("FLW_PUBLIC_KEY")
    FLW_WEBHOOK_SECRET = os.getenv("FLW_WEBHOOK_SECRET")
    FLW_BASE_URL = os.getenv("FLW_BASE_URL", "https://api.flutterwave.com/v3")


    INTASEND_PUBLIC_KEY = os.getenv("INTASEND_PUBLIC_KEY")
    INTASEND_SECRET_KEY = os.getenv("INTASEND_SECRET_KEY")
    INTASEND_WEBHOOK_SECRET = os.getenv("INTASEND_WEBHOOK_SECRET")
    INTASEND_BASE_URL = os.getenv(
       "INTASEND_BASE_URL",
      "https://sandbox.intasend.com/api/v1"
)


