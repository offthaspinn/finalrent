# models.py
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import pytz
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Column, DateTime
from rentme.extensions import db 


class JobLock(db.Model):
    __tablename__ = "job_locks"

    id = db.Column(db.Integer, primary_key=True)
    job_name = db.Column(db.String(100), unique=True, nullable=False)
    last_run = db.Column(db.Date, nullable=True)
    locked_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<JobLock {self.job_name}>"

class MpesaCredential(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    shortcode = db.Column(db.String(50))
    shortcode_type = db.Column(db.String(20))   # paybill, till, sendmoney
    callback_url = db.Column(db.String(500))

    mpesa_env = db.Column(db.String(20), default="sandbox")

    encrypted_consumer_key = db.Column(db.LargeBinary)
    encrypted_consumer_secret = db.Column(db.LargeBinary)
    encrypted_passkey = db.Column(db.LargeBinary)

    def set_secret(self, key_name, raw_value):
        setattr(self, f"encrypted_{key_name}", encrypt_value(raw_value))

    def get_secret(self, key_name):
        return decrypt_value(getattr(self, f"encrypted_{key_name}"))


# ==============================================================
# USER MODEL (Each user has own tenants + own MPESA credentials)
# ==============================================================

class User(db.Model, UserMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)

    # -------------------------
    # Identity
    # -------------------------
    full_name = db.Column(db.String(180), nullable=True)
    email = db.Column(db.String(256), unique=True, nullable=False, index=True)
    login_phone = db.Column(db.String(20), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)

    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_logout = Column(DateTime, default=datetime.utcnow)

    # -------------------------
    # PAYMENT METHOD CHOSEN BY USER
    # -------------------------
    # "SendMoney" | "Paybill" | "Till"
    payment_method = db.Column(db.String(50), nullable=True)

    # SEND MONEY OPTION
    phone_number = db.Column(db.String(20), nullable=True)

    # PAYBILL OPTION
    paybill_number = db.Column(db.String(30), nullable=True)

    # TILL OPTION
    till_number = db.Column(db.String(30), nullable=True)

    # -------------------------
    # DARAJA MPESA CREDENTIALS
    # -------------------------
    mpesa_consumer_key = db.Column(db.String(200), nullable=True)
    mpesa_consumer_secret = db.Column(db.String(200), nullable=True)
    mpesa_passkey = db.Column(db.String(200), nullable=True)
    mpesa_shortcode = db.Column(db.String(20), nullable=True)
    mpesa_env = db.Column(db.String(20), default="sandbox")  # sandbox | production
    mpesa_callback_url = db.Column(db.String(500), nullable=True)

    # -------------------------
    # Password reset
    # -------------------------
    reset_code = db.Column(db.String(10), nullable=True)
    reset_code_expires_at = db.Column(db.DateTime, nullable=True)

    # -------------------------
    # Relationships
    # -------------------------
    properties = db.relationship(
        "Property",
        backref="owner",
        cascade="all, delete-orphan",
        lazy=True
    )

    subscriptions = db.relationship(
        "Subscription",
        backref="user",
        cascade="all, delete-orphan",
        lazy=True
    )

    payments = db.relationship(
        "Payment",
        backref="payer",
        cascade="all, delete-orphan",
        lazy=True
    )

    audit_logs = db.relationship(
        "AuditLog",
        backref="user",
        cascade="all, delete-orphan",
        lazy=True
    )

    # -------------------------
    # Auth helpers
    # -------------------------
    def set_password(self, pwd: str):
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd: str) -> bool:
        return check_password_hash(self.password_hash, pwd)

    # =========================
    # SUBSCRIPTION HELPERS
    # =========================
    def has_active_subscription(self) -> bool:
        """
        Check if user has a valid, non-expired subscription.
        Automatically deactivates expired subscriptions.
        """
        from rentme.models import Subscription

        sub = (
            Subscription.query
            .filter_by(user_id=self.id, is_active=True)
            .order_by(Subscription.created_at.desc())
            .first()
        )

        if not sub:
            return False

        if sub.expires_at and sub.expires_at < datetime.utcnow():
            sub.is_active = False
            db.session.commit()
            return False

        return True

    def active_subscription(self):
        """
        Return active subscription or None
        """
        from rentme.models import Subscription

        return (
            Subscription.query
            .filter_by(user_id=self.id, is_active=True)
            .order_by(Subscription.created_at.desc())
            .first()
        )

    def can_create_property(self) -> bool:
        """
        Enforce property limit based on subscription plan
        """
        sub = self.active_subscription()
        if not sub or not sub.plan:
            return False

        return len(self.properties) < sub.plan.max_properties

    def __repr__(self):
        return f"<User {self.email} | admin={self.is_admin}>"


class SubscriptionIntent(db.Model):
    __tablename__ = "subscription_intents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    plan_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending / completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class LandlordSettings(db.Model):
    __tablename__ = "landlord_settings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    payment_method = db.Column(db.String(50), nullable=True)

    # Business receiving numbers
    paybill_number = db.Column(db.String(32), nullable=True)
    till_number = db.Column(db.String(32), nullable=True)
    send_money_number = db.Column(db.String(32), nullable=True)
    phone_number = db.Column(db.String(50), nullable=True)  # optional display phone

    # -----------------------------
    # MPESA (Safaricom) Credentials
    # -----------------------------
    mpesa_consumer_key = db.Column(db.String(255), nullable=True)
    mpesa_consumer_secret = db.Column(db.String(255), nullable=True)
    mpesa_shortcode = db.Column(db.String(32), nullable=True)   # BusinessShortCode / Paybill/Till
    mpesa_passkey = db.Column(db.String(255), nullable=True)
    mpesa_mode = db.Column(db.String(20), default="production", nullable=False)  # 'production' or 'sandbox'
    callback_url = db.Column(db.String(512), nullable=True)  # optional per-landlord callback override

    # -----------------------------
    # KCB Paybill Credentials
    # -----------------------------
    kcb_api_key = db.Column(db.String(255), nullable=True)
    kcb_paybill = db.Column(db.String(32), nullable=True)
    kcb_env = db.Column(db.String(20), default="sandbox", nullable=False)  # 'sandbox' or 'production'
    kcb_callback_url = db.Column(db.String(512), nullable=True)  # optional per-landlord callback

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    user = db.relationship("User", backref=db.backref("landlord_settings", uselist=False))

    def __repr__(self):
        return f"<LandlordSettings user_id={self.user_id} mpesa_mode={self.mpesa_mode} kcb_env={self.kcb_env}>"


# ==============================================================
# TENANT MODEL (Each tenant belongs to a specific user)
# ==============================================================

from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from rentme.extensions import db


class Tenant(db.Model):
    __tablename__ = "tenant"

    id = db.Column(db.Integer, primary_key=True)

    # 🔑 Tenant belongs to a PROPERTY (NOT a user)
    property_id = db.Column(
        db.Integer,
        db.ForeignKey("property.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = db.Column(db.String(180), nullable=False)
    phone = db.Column(db.String(80), nullable=False)
    national_id = db.Column(db.String(80))

    # Used as Paybill / Account Number
    house_no = db.Column(db.String(80), nullable=False)

    monthly_rent = db.Column(db.Float, nullable=False, default=0.0)
    move_in_date = db.Column(db.Date, nullable=False, default=date.today)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    last_rent_update = db.Column(db.Date, nullable=False, default=date.today)
    amount_due = db.Column(db.Float, nullable=False, default=0.0)

    # -----------------------
    # Relationships
    # -----------------------
    payments = db.relationship(
        "Payment",
        backref="tenant",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    # -----------------------
    # Rent Calculations
    # -----------------------
    def total_paid(self) -> float:
        return sum((p.amount or 0.0) for p in self.payments)

    def months_since_move_in(self, upto: date | None = None) -> int:
        upto = upto or date.today()

        if upto < self.move_in_date:
            return 0

        rd = relativedelta(upto, self.move_in_date)
        return rd.years * 12 + rd.months + (1 if rd.days >= 0 else 0)

    def total_due_since(self, upto: date | None = None) -> float:
        return self.months_since_move_in(upto) * float(self.monthly_rent)

    def balance_calc(self, upto: date | None = None) -> float:
        return round(self.total_paid() - self.total_due_since(upto), 2)

    @property
    def balance(self) -> float:
        return self.balance_calc()

    def formatted_balance(self) -> str:
        bal = self.balance
        sign = "+" if bal >= 0 else "-"
        return f"{sign}{abs(bal):,.2f}"

    def update_monthly_due(self):
        today = date.today()

        # Prevent double charging in the same month
        if (
            self.last_rent_update.year == today.year
            and self.last_rent_update.month == today.month
        ):
            return

        months_behind = (
            (today.year - self.last_rent_update.year) * 12
            + (today.month - self.last_rent_update.month)
        )

        if months_behind > 0:
            self.amount_due += self.monthly_rent * months_behind
            self.last_rent_update = today
            db.session.commit()


# ==============================================================
# PAYMENT MODEL
# Used for SendMoney, Paybill, Till, and Daraja STK Push
# ==============================================================
class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    transaction_id = db.Column(db.String(100), unique=True, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    paid_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    note = db.Column(db.String(255))

    # Foreign Keys
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    # CheckoutRequestID for Daraja callbacks routing
    checkout_request_id = db.Column(db.String(100), index=True, nullable=True)

    def apply_payment(self):
        """Reduce tenant’s amount_due when payment is made"""
        if self.tenant:
            self.tenant.amount_due = max(0.0, self.tenant.amount_due - self.amount)
            self.tenant.last_rent_update = date.today()
            db.session.commit()



# ==============================================================
# AUDIT LOG MODEL
# ==============================================================
class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    action = db.Column(db.String(200), nullable=False)
    meta = db.Column(db.String(1000))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)



# ==============================================================
# AUTO RENT UPDATER (Kenya Time)
# ==============================================================
def auto_update_all_unpaid_rents():
    kenya_tz = pytz.timezone("Africa/Nairobi")
    now = datetime.now(kenya_tz)
    today = now.date()

    tenants = Tenant.query.all()
    updated = 0

    for t in tenants:
        months_behind = (today.year - t.last_rent_update.year) * 12 + (today.month - t.last_rent_update.month)
        if months_behind > 0:
            t.amount_due += t.monthly_rent * months_behind
            t.last_rent_update = today
            updated += 1

    if updated > 0:
        db.session.commit()
        db.session.add(AuditLog(
            user_id=None,
            action="Auto rent update",
            meta=f"{updated} tenants updated on {today.isoformat()} (EAT)"
        ))
        db.session.commit()

    return updated

#Properties
class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tenants = db.relationship(
        "Tenant",
        backref="property",
        cascade="all, delete-orphan"
    )


class Subscription(db.Model):
    __tablename__ = "subscription"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    plan_id = db.Column(db.Integer, db.ForeignKey("plan.id"), nullable=True)  # ✅ FK explicitly
    plan_name = db.Column(db.String(50), nullable=False)

    properties_allowed = db.Column(db.Integer, nullable=False)
    amount_paid = db.Column(db.Float, nullable=False)

    is_active = db.Column(db.Boolean, default=True)
    mpesa_receipt = db.Column(db.String(50))
    created_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)

    # Relationship
    plan = db.relationship("Plan", backref="subscriptions")


class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(50))
    price = db.Column(db.Integer)  # in KES
    max_properties = db.Column(db.Integer)

    duration_days = db.Column(db.Integer, default=30)

