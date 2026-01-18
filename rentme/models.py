# models.py
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import pytz
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Column, DateTime
from rentme.extensions import db 
from rentme.utils import generate_property_ref, generate_unit_reference
from sqlalchemy import event


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
    last_logout = db.Column(db.DateTime, default=datetime.utcnow)

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
        back_populates="landlord",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    subscriptions = db.relationship(
        "Subscription",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    landlord_settings = db.relationship(
        "LandlordSettings",
        uselist=False,
        backref="user",
        cascade="all, delete-orphan",
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
    def active_subscription(self):
        from rentme.models import Subscription

        now = datetime.utcnow()

        sub = (
            Subscription.query
            .filter_by(user_id=self.id, is_active=True)
            .order_by(Subscription.created_at.desc())
            .first()
        )

        if not sub:
            return None

        if sub.expires_at and sub.expires_at >= now:
            sub.is_grace = False
            return sub

        if sub.grace_expires_at and sub.grace_expires_at >= now:
            sub.is_grace = True
            db.session.commit()
            return sub

        sub.is_active = False
        sub.is_grace = False
        db.session.commit()
        return None

    def has_active_subscription(self) -> bool:
        return self.active_subscription() is not None

    def can_create_property(self) -> bool:
        sub = self.active_subscription()
        if not sub:
            return False
        return self.properties.count() < sub.properties_allowed

    def __repr__(self):
        return f"<User {self.email} | admin={self.is_admin}>"

class LandlordSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True)

    # Display only (IntaSend-owned)
    master_paybill = db.Column(db.String(50), nullable=True)
    master_account_format = db.Column(db.String(50), nullable=True)

    # Payout (used later)
    bank_name = db.Column(db.String(100), nullable=True)
    bank_account_name = db.Column(db.String(100), nullable=True)
    bank_account_number = db.Column(db.String(50), nullable=True)
    bank_branch = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class RentLedger(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    landlord_id = db.Column(db.Integer, nullable=False)
    property_id = db.Column(db.Integer, nullable=False)
    unit_id = db.Column(db.Integer, nullable=False)
    tenant_id = db.Column(db.Integer, nullable=True)

    amount = db.Column(db.Numeric(10, 2))
    currency = db.Column(db.String(10), default="KES")

    intasend_invoice_id = db.Column(db.String(50))
    intasend_ref = db.Column(db.String(50))

    status = db.Column(db.String(20))  # COMPLETE, FAILED
    paid_at = db.Column(db.DateTime)


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


class Invoice(db.Model):
    __tablename__ = "invoice"

    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Used inside IntaSend reference
    reference_code = db.Column(
        db.String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    amount_due = db.Column(db.Float, nullable=False)
    amount_paid = db.Column(db.Float, default=0.0)

    status = db.Column(
        db.String(20),
        default="UNPAID"   # UNPAID | PARTIAL | PAID
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # relationship
    tenant = db.relationship("Tenant", backref="invoices")

    def __repr__(self):
        return f"<Invoice {self.reference_code} status={self.status}>"


# ==============================================================
# PAYMENT MODEL
# Used for SendMoney, Paybill, Till, and Daraja STK Push
# ==============================================================
class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    provider = db.Column(
        db.String(30),
        nullable=False,
        default="INTASEND"
    )

    transaction_id = db.Column(db.String(100), unique=True, nullable=False)
    reference = db.Column(db.String(120), index=True)

    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="KES")

    status = db.Column(
        db.String(20),
        default="CONFIRMED"   # CONFIRMED | PARTIAL | FAILED
    )

    paid_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    raw_payload = db.Column(db.JSON)

    tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    def apply_payment(self):
        if self.tenant:
            self.tenant.amount_due = max(0.0, self.tenant.amount_due - self.amount)
            self.tenant.last_rent_update = date.today()


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
    __tablename__ = "property"

    id = db.Column(db.Integer, primary_key=True)

    landlord_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    name = db.Column(db.String(150), nullable=False)

    reference = db.Column(db.String(10), unique=True, nullable=False)

    # ✅ REQUIRED relationship (this was missing)
    landlord = db.relationship(
        "User",
        back_populates="properties"
    )

    units = db.relationship(
        "Unit",
        back_populates="property",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Property {self.name} ({self.reference})>"


from rentme.extensions import db


class Unit(db.Model):
    __tablename__ = "unit"

    id = db.Column(db.Integer, primary_key=True)

    property_id = db.Column(
        db.Integer,
        db.ForeignKey("property.id"),
        nullable=False
    )

    house_no = db.Column(db.String(20), nullable=False)

    payment_ref = db.Column(db.String(50), unique=True, nullable=True)

    property = db.relationship(
        "Property",
        back_populates="units"
    )

    def __repr__(self):
        return f"<Unit {self.house_no} | {self.payment_ref}>"


class Subscription(db.Model):
    __tablename__ = "subscription"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False
    )

    plan_id = db.Column(
        db.Integer,
        db.ForeignKey("plan.id", ondelete="RESTRICT"),
        nullable=True
    )

    intent_id = db.Column(
        db.Integer,
        db.ForeignKey("subscription_intents.id"),
        unique=True,
        nullable=True  # trials / admin subs
    )

    # Snapshot values
    plan_name = db.Column(db.String(50), nullable=False)
    properties_allowed = db.Column(db.Integer, nullable=False)

    amount_paid = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    payment_invoice_id = db.Column(db.String(100), unique=True)

    is_active = db.Column(db.Boolean, default=True)

    # States
    is_trial = db.Column(db.Boolean, default=False)
    is_grace = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    grace_expires_at = db.Column(db.DateTime)

    # -------------------------
    # Relationships (✅ FINAL)
    # -------------------------
    user = db.relationship(
        "User",
        back_populates="subscriptions"
    )

    plan = db.relationship(
        "Plan",
        back_populates="subscriptions"
    )

    intent = db.relationship("SubscriptionIntent")

    def __repr__(self):
        return (
            f"<Subscription user={self.user_id} "
            f"plan={self.plan_name} "
            f"active={self.is_active} "
            f"trial={self.is_trial}>"
        )

class Plan(db.Model):
    __tablename__ = "plan"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Integer, nullable=False)  # KES
    max_properties = db.Column(db.Integer, nullable=False)
    duration_days = db.Column(db.Integer, default=30)

    # ✅ FIXED — NO backref
    subscriptions = db.relationship(
        "Subscription",
        back_populates="plan",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    def __repr__(self):
        return f"<Plan {self.name}>"


class SubscriptionIntent(db.Model):
    __tablename__ = "subscription_intents"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False
    )

    plan_id = db.Column(
        db.Integer,
        db.ForeignKey("plan.id", ondelete="RESTRICT"),
        nullable=False
    )

    # IntaSend identifiers
    reference = db.Column(db.String(100), unique=True, nullable=False)
    payment_invoice_id = db.Column(db.String(100), unique=True)
    transaction_id = db.Column(db.String(100))

    payer_account = db.Column(db.String(120))
    currency = db.Column(db.String(10), default="KES")

    amount = db.Column(db.Numeric(10, 2), nullable=False)
    charge = db.Column(db.Numeric(10, 2), default=0)

    status = db.Column(
        db.String(20),
        nullable=False,
        default="PENDING"  # PENDING | COMPLETE | FAILED
    )

    clearing_status = db.Column(db.String(20))  # AVAILABLE

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, onupdate=db.func.now())

    user = db.relationship("User")
    plan = db.relationship("Plan")


    

@event.listens_for(Property, "before_insert")
def set_property_reference(mapper, connection, target):
    if not target.reference:
        target.reference = generate_property_ref()

@event.listens_for(Unit, "before_insert")
def set_unit_payment_ref(mapper, connection, target):
    if target.payment_ref:
        return

    # 🔒 Fetch property reference safely
    property_ref = connection.execute(
        db.select(Property.reference)
        .where(Property.id == target.property_id)
    ).scalar_one()

    target.payment_ref = generate_unit_reference(
        property_ref,
        target.house_no
    )
