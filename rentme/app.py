import os
from flask import session

import io
import json
import csv
from rentme.forms import LoginForm
from datetime import datetime, date, timedelta
from functools import wraps
import uuid
import pytz
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
import random
from rentme.forms import CreatePropertyForm

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_from_directory,
    jsonify,
    abort,
    Response,
)
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
    UserMixin,
)
from flask import Flask, Blueprint, render_template, request, redirect, url_for, flash

from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
import redis
# at the top of rentme/app.py (with your other imports)
from flask import current_app, request, session, url_for, redirect

# Local imports
from rentme.extensions import db, mail, limiter
from rentme.config import Config
from rentme.models import User, Tenant, Payment, AuditLog, Plan, Property, Subscription
from rentme.mpesa_handler import mpesa_bp
from rentme.landlord_settings import landlord_settings_bp
from register_daraja_live import register_urls
from rentme.forms import RegisterForm
from rentme.forms import ForgotPasswordForm
from rentme.utils import send_sms_via_africastalking, send_reset_email, normalize_msisdn
from rentme.forms import TenantForm
from wtforms.validators import ValidationError
from flask_wtf.csrf import validate_csrf
from wtforms.validators import ValidationError
from flask_wtf import CSRFProtect
from sqlalchemy import or_
from sqlalchemy import func
from rentme.forms import ResetPasswordForm
from rentme.routes.subscriptions import subscriptions_bp
from flask_migrate import Migrate
from rentme.payments.intasend_bp import intasend_bp
from rentme.forms import CreatePropertyForm
from pytz import timezone
from rentme.subscriptions.utils import subscription_required




# -----------------------
# Load environment variables
# -----------------------
load_dotenv()

# -----------------------
# Paths
# -----------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
APK_FOLDER = os.path.join(BASE_DIR, "static", "apk")

migrate = Migrate()

# -----------------------
# Create Flask app
# -----------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
from rentme.routes import *

if __name__ == "__main__":
    app.run(debug=True)

app.config.from_object(Config)

# Redis connection (optional, for production rate limiting)
REDIS_URL = os.getenv("REDIS_URL")

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri=REDIS_URL if REDIS_URL else "memory://",
)

# -----------------------
# Environment overrides
# -----------------------
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY not set")

app.config["SECRET_KEY"] = SECRET_KEY

db_url = os.getenv("SQLALCHEMY_DATABASE_URI")
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

# -----------------------
# Init extensions
# -----------------------
db.init_app(app)
csrf = CSRFProtect(app)
mail.init_app(app)
limiter.init_app(app)
migrate.init_app(app, db)
csrf.init_app(app)
csrf.exempt(mpesa_bp)
csrf.exempt(intasend_bp)


# -----------------------
# Login manager
# -----------------------


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    if not user:
        return None

    # Optional: reject sessions created before last_logout
    session_created_at = session.get("created_at")
    if session_created_at:
        try:
            session_created_dt = datetime.fromisoformat(session_created_at)
            if user.last_logout and session_created_dt < user.last_logout:
                return None
        except Exception as e:
            print("❌ Error checking last_logout:", e)

    return user


# -----------------------
# Timezone helpers
# -----------------------
NAIROBI_TZ = pytz.timezone("Africa/Nairobi")


def to_nairobi(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(NAIROBI_TZ)


app.jinja_env.filters["to_nairobi"] = to_nairobi

# -----------------------
# Blueprints
# -----------------------
app.register_blueprint(mpesa_bp, url_prefix="/mpesa")
print("✅ M-Pesa Blueprint active at /mpesa")
app.register_blueprint(landlord_settings_bp, url_prefix="/settings")

app.register_blueprint(subscriptions_bp)


app.register_blueprint(intasend_bp)


# -----------------------
# Debug logger
# -----------------------
# -----------------------
# Development-only request logging
# -----------------------
if app.config.get("ENV") == "development":

    @app.before_request
    def log_request_info():
        print("\n====== 📥 NEW REQUEST ======")
        print(f"➡️ Path:   {request.path}")
        print(f"➡️ Method: {request.method}")

        try:
            data = request.get_json(force=True, silent=True)
            if data:
                print(f"➡️ Body:\n{json.dumps(data, indent=2)}")
            else:
                print("➡️ Body: None")
        except Exception as e:
            print(f"⚠️ JSON parse error: {e}")


# -----------------------
# DB + Scheduler
# -----------------------

# -----------------------
# Audit helper
# -----------------------


# -----------------------
# Audit helper (NON-BLOCKING)
# -----------------------
def audit(user, action, meta=""):
    try:
        entry = AuditLog(
            user_id=(user.id if user else None),
            action=action,
            meta=str(meta),
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.warning("Audit log failed: %s", e)


# -----------------------
# Decorators
# -----------------------
def ensure_apk_exists(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not os.path.isdir(APK_FOLDER):
            flash("APK folder missing.", "danger")
            return redirect(url_for("dashboard"))
        apk_files = [f for f in os.listdir(APK_FOLDER) if f.lower().endswith(".apk")]
        if not apk_files:
            flash("No APK file found.", "warning")
            return redirect(url_for("dashboard"))
        kwargs["_apk_filename"] = apk_files[0]
        return func(*args, **kwargs)

    return wrapper


def owner_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        tenant_id = (
            kwargs.get("tenant_id")
            or request.view_args.get("tenant_id")
            or request.form.get("tenant_id")
            or request.args.get("tenant_id")
        )
        if not tenant_id:
            abort(400, description="Tenant ID missing.")
        tenant = Tenant.query.get(int(tenant_id))
        if not tenant:
            abort(404, description="Tenant not found.")
        if not current_user.is_authenticated:
            return redirect(url_for("login", next=request.path))
        if tenant.property_id != current_user.id and not current_user.is_admin:
            flash("No permission.", "danger")
            return redirect(url_for("tenant_list"))
        kwargs["_tenant_obj"] = tenant
        return func(*args, **kwargs)

    return wrapper


# -----------------------
# Routes
# -----------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    form = RegisterForm()

    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        raw_phone = form.login_phone.data.strip() if form.login_phone.data else ""
        phone = normalize_msisdn(raw_phone) if raw_phone else None

        # 🔍 Check existing email
        email_exists = User.query.filter_by(email=email).first()
        if email_exists:
            flash("Email already registered. Please login.", "warning")
            return redirect(url_for("login"))

        # 🔍 Check existing phone (only if provided & valid)
        if phone:
            phone_exists = User.query.filter_by(login_phone=phone).first()
            if phone_exists:
                flash("Phone number already registered. Please login.", "warning")
                return redirect(url_for("login"))

        # 🚨 Invalid phone provided
        if raw_phone and not phone:
            flash("Invalid phone number format.", "danger")
            return redirect(url_for("register"))

        # ✅ Create user
        user = User(
            full_name=form.full_name.data.strip(),
            email=email,
            login_phone=phone,
            password_hash=generate_password_hash(form.password.data),
        )

        try:
            db.session.add(user)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash("Registration failed. Please try again.", "danger")
            return redirect(url_for("register"))

        audit(
            user,
            "user_registered",
            f"email:{user.email}, phone:{user.login_phone or '-'}",
        )

        flash("Registration successful! You can now login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", form=form)


# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    form = LoginForm()

    if form.validate_on_submit():
        identifier = form.identifier.data.strip()
        password = form.password.data

        user = User.query.filter_by(email=identifier.lower()).first()
        if not user:
            user = User.query.filter_by(login_phone=identifier).first()

        if not user or not user.check_password(password):
            flash("Invalid credentials.", "danger")
            return render_template("login.html", form=form)

        login_user(user)
        audit(user, "user_logged_in", f"id:{user.id}")

        # 🚫 NO LOGOUT HERE
        if not user.has_active_subscription():
            flash(
                "Your subscription has expired. Please choose a plan to continue.",
                "warning",
            )
            return redirect(url_for("subscriptions.list_plans"))

        flash("Welcome back!", "success")
        return redirect(request.args.get("next") or url_for("dashboard"))

    return render_template("login.html", form=form)


# ======================================================
# ======================================================
# 🔐 GLOBAL ACCESS ENFORCEMENT
# ======================================================
@app.before_request
def enforce_property_and_subscription():
    endpoint = request.endpoint or ""

    # -----------------------------
    # 1️⃣ Public routes (ALWAYS allowed)
    # -----------------------------
    PUBLIC_ENDPOINTS = {
        "login",
        "logout",
        "register",
        "forgot_password",
        "reset_password",
        "verify_email",
        "home",
    }

    if (
        endpoint.startswith("static")
        or endpoint.startswith("subscriptions.")
        or endpoint.startswith("intasend.")
        or endpoint in PUBLIC_ENDPOINTS
    ):
        return

    # -----------------------------
    # 2️⃣ Require authentication
    # -----------------------------
    if not current_user.is_authenticated:
        return redirect(url_for("login"))

    # -----------------------------
    # 3️⃣ Require active subscription
    # -----------------------------
    if not current_user.has_active_subscription():
        return redirect(url_for("subscriptions.list_plans"))

    # -----------------------------
    # 4️⃣ Property selection rules
    # -----------------------------
    PROPERTY_ALLOWED = {
        "select_property",
        "activate_property",
        "create_property",
        "profile",
    }

    if "active_property_id" not in session:
        if endpoint not in PROPERTY_ALLOWED:
            return redirect(url_for("select_property"))

    # -----------------------------
    # 5️⃣ Access granted
    # -----------------------------
    return
# ======================================================
# 🏠 PROPERTIES
# ======================================================
@app.route("/properties")
@login_required
@subscription_required
def select_property():
    properties = (
        Property.query
        .filter_by(owner_id=current_user.id)
        .order_by(Property.id.asc())
        .all()
    )

    form = CreatePropertyForm()

    return render_template(
        "properties.html",
        properties=properties,
        can_create=current_user.can_create_property(),
        form=form,
    )


@app.route("/properties/<int:property_id>/activate")
@login_required
def activate_property(property_id):
    prop = Property.query.filter_by(
        id=property_id,
        owner_id=current_user.id
    ).first_or_404()

    session["active_property_id"] = prop.id

    flash(f"Switched to {prop.name}", "success")
    return redirect(url_for("dashboard"))


# ======================================================
# 🏠 CREATE PROPERTY
# ======================================================
@app.route("/properties/create", methods=["GET", "POST"])
@login_required
@subscription_required
def create_property():
    form = CreatePropertyForm()

    current_app.logger.debug(
        "create_property called; endpoint=%s; method=%s; session=%s; has_active=%s; can_create=%s; form_errors=%s",
        request.endpoint,
        request.method,
        dict(session),
        current_user.has_active_subscription(),
        current_user.can_create_property(),
        form.errors,
    )

    if form.validate_on_submit():
        current_app.logger.debug("create_property form validated; form.errors=%s", form.errors)

        # Enforce subscription limits
        if not current_user.can_create_property():
            current_app.logger.info("User %s cannot create more properties (limit reached).", current_user.email)
            flash("Your plan does not allow you to add another property.", "warning")
            return redirect(url_for("select_property"))

        name = form.name.data.strip()
        password = form.password.data

        # Confirm password
        if not current_user.check_password(password):
            current_app.logger.info("User %s provided incorrect password when creating property.", current_user.email)
            flash("Incorrect password. Property not created.", "danger")
            return redirect(url_for("select_property"))

        # Create property with safe commit
        prop = Property(owner_id=current_user.id, name=name)
        try:
            db.session.add(prop)
            db.session.commit()
        except Exception:
            current_app.logger.exception("Failed to create property for user %s", current_user.email)
            db.session.rollback()
            flash("An error occurred while creating the property.", "danger")
            return redirect(url_for("select_property"))

        # Auto-activate property in session after successful commit
        session["active_property_id"] = prop.id
        current_app.logger.info("Set active_property_id=%s in session for user=%s", prop.id, current_user.email)

        audit(current_user, "property_created", f"id:{prop.id}")
        flash("New property created successfully!", "success")
        return redirect(url_for("dashboard"))

    # If POST but validation failed, log errors
    if request.method == "POST":
        current_app.logger.debug("create_property POST but validation failed; errors=%s", form.errors)

    return render_template("create_property.html", form=form)


@app.route("/logout")
@login_required
def logout():
    current_user.last_logout = datetime.utcnow()
    db.session.commit()
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("login"))


# -----------------------------------------------------
# FORGOT PASSWORD
# -----------------------------------------------------
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    form = ForgotPasswordForm()

    if form.validate_on_submit():
        value = form.email_or_phone.data.strip()

        # Detect email or phone
        if "@" in value:
            user = User.query.filter_by(email=value.lower()).first()
        else:
            normalized = normalize_msisdn(value)
            user = User.query.filter_by(login_phone=normalized).first()

        if not user:
            flash("No account found with that email or phone number.", "danger")
            return redirect("/forgot-password")

        # Generate reset code
        code = str(random.randint(100000, 999999))
        user.reset_code = code
        user.reset_code_expires_at = datetime.utcnow() + timedelta(minutes=10)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error saving reset code: {e}")
            flash("Something went wrong. Try again.", "danger")
            return redirect("/forgot-password")

        # Try SMS first
        sent_sms = send_sms_via_africastalking(
            user.login_phone, f"Your Rentana reset code is {code}"
        )

        # Fallback to email if SMS failed or credentials missing
        if not sent_sms:
            sent_email = send_reset_email(
                user.email,
                "Rentana Password Reset",
                f"Your Rentana password reset code is {code}",
            )
            if sent_email:
                flash("Reset code sent to your email.", "success")
            else:
                flash(
                    "Could not send reset code via SMS or email. Contact support.",
                    "danger",
                )
        else:
            flash("A reset code has been sent to your phone.", "success")

        return redirect("/reset-password")

    return render_template("forgot_password.html", form=form)


# -----------------------------------------------------
# RESET PASSWORD
# -----------------------------------------------------
@limiter.limit("5/minute")
@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    form = ResetPasswordForm()

    if form.validate_on_submit():
        identifier = form.identifier.data.strip()
        code = form.code.data.strip()
        password = form.password.data

        # email or phone
        if "@" in identifier:
            user = User.query.filter_by(email=identifier.lower()).first()
        else:
            normalized = normalize_msisdn(identifier)
            user = User.query.filter_by(login_phone=normalized).first()

        if not user:
            flash("Account not found.", "danger")
            return render_template("reset_password.html", form=form)

        now = datetime.utcnow()

        # validate reset code
        if user.reset_code != code:
            flash("Invalid reset code.", "danger")
            return render_template("reset_password.html", form=form)

        if not user.reset_code_expires_at or user.reset_code_expires_at < now:
            flash("Reset code expired.", "danger")
            return render_template("reset_password.html", form=form)

        # set new password
        user.set_password(password)
        user.reset_code = None
        user.reset_code_expires_at = None
        db.session.commit()

        flash("Password changed successfully.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html", form=form)


# ✅ Helper Functions
# =====================================
# DUPLICATEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE
##3def process_payment(phone, amount, receipt, note="")

# manifesss


@app.route("/manifest.json")
def manifest():
    return send_from_directory(
        "static", "manifest.json", mimetype="application/manifest+json"
    )


# Optional: health check
# ----------------------
@app.route("/webhook/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Webhook is alive"}), 200


# ----------------------
# Optional: simulate a test payment (offline)


# -----------------------
# -----------------------
# ======================================================
# 📊 Dashboard
# ======================================================

NAIROBI_TZ = timezone("Africa/Nairobi")


@app.route("/")
@login_required
@subscription_required
def dashboard():
    """
    Render landlord dashboard UI.
    Actual data is loaded via /dashboard_data
    """
    # Ensure a property is selected
    if "active_property_id" not in session:
        return redirect(url_for("select_property"))

    return render_template("dashboard.html")


@app.route("/dashboard_data")
@login_required
@subscription_required
def dashboard_data():
    """
    Return live dashboard data as JSON (PROPERTY-SCOPED):
      - Tenant details
      - Totals: expected, collected, outstanding
      - Collected percentage
    """

    # 🏠 Active property context
    property_id = session.get("active_property_id")
    if not property_id:
        return jsonify({"error": "No active property selected"}), 400

    # 🧭 Get tenants ONLY for active property
    tenants = (
        Tenant.query
        .filter_by(property_id=property_id)
        .order_by(Tenant.name.asc())
        .all()
    )

    # 💰 Compute totals
    total_expected = sum((t.total_due_since() or 0.0) for t in tenants)
    total_collected = sum((t.total_paid() or 0.0) for t in tenants)

    # Outstanding (never negative)
    total_outstanding = round(max(total_expected - total_collected, 0.0), 2)

    # Collection percentage
    collected_percent = (
        round((total_collected / total_expected) * 100, 2)
        if total_expected > 0
        else 0.0
    )

    # 🏠 Tenant table payload
    tenants_list = []
    for t in tenants:
        paid = t.total_paid() or 0.0
        due = t.total_due_since() or 0.0
        balance = round(paid - due, 2)

        tenants_list.append({
            "id": t.id,
            "name": t.name,
            "phone": t.phone,
            "house_no": t.house_no,
            "monthly_rent": float(t.monthly_rent or 0.0),
            "total_paid": float(paid),
            "total_due": float(due),
            "balance": float(balance),
            "formatted_balance": f"{balance:,.2f}",
        })

    # 📤 JSON response for dashboard UI
    return jsonify({
        "total_tenants": len(tenants),
        "total_expected": round(total_expected, 2),
        "total_collected": round(total_collected, 2),
        "total_outstanding": total_outstanding,
        "collected_percent": collected_percent,
        "tenants": tenants_list,
    })

# payment type
# -----------------------


# Tenants CRUD
# ----------------------


@app.route("/tenants")
@login_required
@subscription_required
def tenant_list():
    q = request.args.get("q", "", type=str).strip()
    page = request.args.get("page", 1, type=int)
    per_page = 20

    property_id = session.get("active_property_id")
    if not property_id:
        return redirect(url_for("select_property"))

    query = Tenant.query.filter(Tenant.property_id == property_id)

    if q:
        search = f"%{q.lower()}%"
        query = query.filter(
            or_(
                func.lower(Tenant.name).like(search),
                func.lower(Tenant.phone).like(search),
                func.lower(Tenant.house_no).like(search),
            )
        )

    pagination = query.order_by(Tenant.house_no.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({
            "rows": render_template("_tenant_rows.html", tenants=pagination.items),
            "pagination": render_template(
                "_tenant_pagination.html", pagination=pagination, query=q
            ),
        })

    return render_template(
        "tenant_list.html",
        tenants=pagination.items,
        pagination=pagination,
        query=q,
    )


@app.route("/tenant/add", methods=["GET", "POST"])
@login_required
@subscription_required
def tenant_add():
    # 🔒 Must have an active property
    property_id = session.get("active_property_id")
    if not property_id:
        flash("Please select a property first.", "warning")
        return redirect(url_for("select_property"))

    form = TenantForm()

    if form.validate_on_submit():
        try:
            t = Tenant(
                property_id=property_id,  # ✅ FIXED
                name=form.name.data.strip(),
                phone=form.phone.data.strip(),
                national_id=form.national_id.data.strip()
                if form.national_id.data
                else None,
                house_no=form.house_no.data.strip(),
                monthly_rent=float(form.monthly_rent.data),
                move_in_date=form.move_in_date.data or date.today(),
            )

            db.session.add(t)
            db.session.commit()

            audit(current_user, "tenant_added", meta=f"id:{t.id}")

            flash("Tenant added successfully.", "success")
            return redirect(url_for("dashboard"))

        except Exception as e:
            db.session.rollback()
            flash("Invalid tenant data.", "danger")
            print("TENANT ADD ERROR:", e)

    return render_template("add_tenant.html", form=form)


# ---------- EDIT TENANT ----------
@app.route("/tenant/<int:tenant_id>/edit", methods=["GET", "POST"])
@login_required
@subscription_required
@owner_required
def tenant_edit(tenant_id, _tenant_obj=None):

    # Ensure tenant object exists
    t = _tenant_obj or Tenant.query.get_or_404(tenant_id)

    if request.method == "POST":

        # Validate CSRF
        try:
            validate_csrf(request.form.get("csrf_token"))
        except ValidationError:
            flash("Invalid or missing CSRF token. Please refresh the page.", "danger")
            return render_template("edit_tenants.html", tenant=t)

        # Update fields
        t.name = (request.form.get("name") or "").strip()
        t.phone = (request.form.get("phone") or "").strip()
        t.national_id = (request.form.get("national_id") or "").strip()
        t.house_no = (request.form.get("house_no") or "").strip()

        try:
            t.monthly_rent = float(request.form.get("monthly_rent") or t.monthly_rent)
        except ValueError:
            flash("Monthly rent must be a valid number.", "danger")
            return render_template("edit_tenants.html", tenant=t)

        # Move-in date
        move_in = request.form.get("move_in_date") or str(t.move_in_date)
        try:
            t.move_in_date = datetime.strptime(move_in, "%Y-%m-%d").date()
        except ValueError:
            flash("Move-in date must be in format YYYY-MM-DD.", "danger")
            return render_template("edit_tenants.html", tenant=t)

        db.session.commit()
        audit(current_user, "tenant_edited", meta=f"id:{t.id}")

        flash("Tenant updated successfully!", "success")
        return redirect(url_for("tenant_list"))

    return render_template("edit_tenants.html", tenant=t)


# ---------- DELETE TENANT ----------
@app.route("/tenant/<int:tenant_id>/delete", methods=["POST"])
@login_required
@subscription_required
def tenant_delete(tenant_id):
    property_id = session.get("active_property_id")
    if not property_id:
        flash("Select a property first.", "warning")
        return redirect(url_for("select_property"))

    tenant = Tenant.query.get_or_404(tenant_id)

    # 🔒 HARD PROPERTY PERMISSION
    if tenant.property_id != property_id:
        abort(403)

    # ✅ CSRF validation
    try:
        validate_csrf(request.form.get("csrf_token"))
    except ValidationError:
        flash("Invalid or missing CSRF token.", "danger")
        return redirect(url_for("tenant_list"))

    db.session.delete(tenant)
    db.session.commit()

    audit(current_user, "tenant_deleted", meta=f"id:{tenant.id}")
    flash("Tenant deleted successfully!", "info")

    return redirect(url_for("tenant_list"))

# ---------- BULK DELETE ----------
# -----------------------
@app.route("/tenants/bulk-delete", methods=["POST"])
@login_required
@subscription_required
def tenant_bulk_delete():

    # Validate CSRF
    try:
        validate_csrf(request.form.get("csrf_token"))
    except ValidationError:
        flash("Invalid CSRF token. Bulk delete cancelled.", "danger")
        return redirect(url_for("tenant_list"))

    ids = request.form.getlist("tenant_ids")

    if not ids:
        flash("No tenants selected.", "warning")
        return redirect(url_for("tenant_list"))

    q = Tenant.query.filter(Tenant.id.in_(ids))

    if not current_user.is_admin:
        q = q.filter(Tenant.property_id == current_user.id)

    tenants = q.all()
    count = len(tenants)

    if count == 0:
        flash("No tenants found or permission denied.", "warning")
        return redirect(url_for("tenant_list"))

    try:
        for tenant in tenants:
            db.session.delete(tenant)

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        app.logger.exception("Bulk tenant delete failed")
        flash("Bulk delete failed. No changes were made.", "danger")
        return redirect(url_for("tenant_list"))

    # Audit AFTER successful commit only
    audit(
        current_user,
        "tenants_bulk_deleted",
        meta=f"count={count}, ids={','.join(ids)}",
    )

    flash(f"{count} tenant(s) deleted successfully.", "success")
    return redirect(url_for("tenant_list"))


# -----------------------
# Payments CRUD
# -----------------------
@app.route("/payment/add", methods=["GET", "POST"])
@login_required
@subscription_required
def payment_add():
    property_id = session.get("active_property_id")
    if not property_id:
        flash("Select a property first.", "warning")
        return redirect(url_for("select_property"))

    # Resolve tenant
    tenant_id = request.args.get("tenant_id") or request.form.get("tenant_id")
    if not tenant_id:
        flash("Tenant not specified.", "danger")
        return redirect(url_for("tenant_list"))

    tenant = Tenant.query.get_or_404(int(tenant_id))

    # 🔒 PROPERTY CHECK
    if tenant.property_id != property_id:
        abort(403)

    if request.method == "POST":
        password = (request.form.get("password_confirm") or "").strip()
        if not password or not current_user.check_password(password):
            flash("Incorrect password.", "danger")
            return render_template("add_payment.html", tenant=tenant)

        try:
            amount = float(request.form.get("amount") or 0)
        except ValueError:
            flash("Amount must be numeric.", "danger")
            return render_template("add_payment.html", tenant=tenant)

        if amount <= 0:
            flash("Amount must be greater than zero.", "danger")
            return render_template("add_payment.html", tenant=tenant)

        note = (request.form.get("note") or "").strip()

        import uuid
        from datetime import datetime

        transaction_id = (
            request.form.get("transaction_id")
            or f"MANUAL-{uuid.uuid4().hex[:8].upper()}"
        )

        payment = Payment(
            tenant_id=tenant.id,
            amount=amount,
            note=note,
            transaction_id=transaction_id,
            paid_at=datetime.utcnow(),
        )

        db.session.add(payment)
        db.session.commit()

        audit(
            current_user,
            "payment_added",
            meta=f"payment_id:{payment.id}, tenant_id:{tenant.id}",
        )

        flash("Payment added successfully.", "success")
        return redirect(url_for("tenant_list"))

    return render_template("add_payment.html", tenant=tenant)


@app.route("/payment/<int:payment_id>/edit", methods=["GET", "POST"])
@login_required
@subscription_required
def payment_edit(payment_id):
    property_id = session.get("active_property_id")

    payment = Payment.query.get_or_404(payment_id)

    # 🔒 PROPERTY CHECK VIA TENANT
    if payment.tenant.property_id != property_id:
        abort(403)

    if request.method == "POST":
        try:
            payment.amount = float(request.form.get("amount") or payment.amount)
        except ValueError:
            flash("Amount must be numeric.", "danger")
            return render_template("payment_edit.html", payment=payment)

        payment.note = request.form.get("note") or ""
        db.session.commit()

        audit(current_user, "payment_edited", meta=f"id:{payment.id}")
        flash("Payment updated.", "success")
        return redirect(url_for("tenant_list"))

    return render_template("payment_edit.html", payment=payment)


@app.route("/payments")
@login_required
@subscription_required
def payment_list():
    property_id = session.get("active_property_id")
    if not property_id:
        return redirect(url_for("select_property"))

    payments = (
        Payment.query
        .join(Tenant)
        .filter(Tenant.property_id == property_id)
        .order_by(Payment.paid_at.desc())
        .all()
    )

    return render_template("payment_list.html", payments=payments)


# Bulk pay
@app.route("/bulk_pay", methods=["POST"])
@login_required
@subscription_required
def bulk_pay():
    tenant_ids = request.form.getlist("tenant_ids")
    amount_raw = request.form.get("amount")
    if not tenant_ids or not amount_raw:
        flash("Tenant(s) or amount missing.", "warning")
        return redirect(url_for("tenant_list"))
    try:
        amount = float(amount_raw)
    except ValueError:
        flash("Invalid amount.", "danger")
        return redirect(url_for("tenant_list"))
    created = 0
    for tid in tenant_ids:
        t = Tenant.query.get(int(tid))
        if t and (t.owner_id == current_user.id or current_user.is_admin):
            p = Payment(tenant_id=t.id, amount=amount, note="Bulk payment")
            db.session.add(p)
            created += 1
    db.session.commit()
    audit(current_user, "bulk_pay", meta=f"ids:{','.join(tenant_ids)},amount:{amount}")
    flash(f"Bulk payments created for {created} tenant(s).", "success")
    return redirect(url_for("dashboard"))


# -----------------------
# Exports
# -----------------------
def make_csv_response(csv_text: str, filename="export.csv"):
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"},
    )


@app.route("/export/tenants.csv")
@login_required
@subscription_required
def export_tenants_csv():
    base_q = Tenant.query
    if not current_user.is_admin:
        base_q = base_q.filter_by(property_id=current_user.id)
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(
        [
            "id",
            "name",
            "phone",
            "national_id",
            "house_no",
            "monthly_rent",
            "move_in_date",
            "total_paid",
            "total_due",
            "balance",
        ]
    )
    for t in base_q.order_by(Tenant.name).all():
        cw.writerow(
            [
                t.id,
                t.name,
                t.phone,
                t.national_id,
                t.house_no,
                f"{t.monthly_rent:.2f}",
                t.move_in_date.isoformat(),
                f"{t.total_paid():.2f}",
                f"{t.total_due_since():.2f}",
                f"{t.balance:.2f}",
            ]
        )
    return make_csv_response(si.getvalue(), "tenants_export.csv")


# daraja register


@app.route("/register_daraja", methods=["POST"])
def register_daraja():
    env = request.form.get("env", "sandbox")
    key = request.form.get("consumer_key")
    secret = request.form.get("consumer_secret")
    shortcode = request.form.get("shortcode")
    callback = request.form.get("callback_url")

    base_url = (
        "https://api.safaricom.co.ke"
        if env == "live"
        else "https://sandbox.safaricom.co.ke"
    )
    result = register_urls(
        env.upper(), base_url, key, secret, shortcode, callback, live=(env == "live")
    )
    return jsonify(result)


@app.route("/export/payments.csv")
@login_required
@subscription_required
def export_payments_csv():
    base_q = Payment.query.join(Tenant)
    if not current_user.is_admin:
        base_q = base_q.filter(Tenant.property_id == current_user.id)
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["id", "tenant_id", "tenant_name", "amount", "note", "paid_at"])
    for p in base_q.order_by(Payment.paid_at.desc()).all():
        cw.writerow(
            [
                p.id,
                p.tenant_id,
                p.tenant.name,
                f"{p.amount:.2f}",
                p.note or "",
                p.paid_at.isoformat(),
            ]
        )
    return make_csv_response(si.getvalue(), "payments_export.csv")


# -----------------------
# APK & PWA
# -----------------------
@app.route("/apk/download")
@login_required
@ensure_apk_exists
def apk_download(_apk_filename=None):
    return send_from_directory(APK_FOLDER, _apk_filename, as_attachment=True)


@app.route("/apk/latest")
@login_required
@ensure_apk_exists
def apk_latest(_apk_filename=None):
    return jsonify({"filename": _apk_filename, "url": url_for("apk_download")})


@app.route("/service-worker.js")
def service_worker():
    return send_from_directory(app.static_folder, "service-worker.js")


# -----------------------
# Context processors / errors / CLI
# -----------------------

from datetime import datetime, date
import pytz

# Explicit Kenya timezone
TZ = pytz.timezone("Africa/Nairobi")


@app.context_processor
def inject_now():
    now = datetime.now(TZ)
    return {
        "current_year": now.year,
        "today": now.date(),
        "date": date,
        "datetime": datetime,
    }


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, message="Forbidden"), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Not Found"), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.exception("Internal Server Error", exc_info=e)
    return render_template("error.html", code=500, message="Server Error"), 500


# -----------------------
# CLI COMMANDS
# -----------------------


@app.cli.command("create-admin")
def create_admin():
    """Create an admin user (manual, production-safe)."""
    import getpass

    email = input("Admin email: ").strip().lower()
    if not email:
        print("❌ Email required.")
        return

    if User.query.filter_by(email=email).first():
        print("❌ User already exists.")
        return

    pwd = getpass.getpass("Password: ")
    pwd2 = getpass.getpass("Confirm password: ")

    if not pwd or pwd != pwd2:
        print("❌ Passwords do not match.")
        return

    confirm = input("Type YES to confirm admin creation: ")
    if confirm != "YES":
        print("❌ Aborted.")
        return

    user = User(email=email, is_admin=True)
    user.set_password(pwd)

    db.session.add(user)
    db.session.commit()

    print("✅ Admin created successfully.")


@app.cli.command("update-monthly-rent")
def update_monthly_rent_cli():
    """
    Monthly rent update (CRON SAFE).
    This replaces APScheduler completely.
    """
    from rentme.models import auto_update_all_unpaid_rents

    with app.app_context():
        try:
            auto_update_all_unpaid_rents()
            db.session.commit()
            print("✅ Monthly rent balances updated successfully.")
        except Exception as e:
            db.session.rollback()
            app.logger.exception("❌ Monthly rent update failed")
            raise e


# -----------------------
# Compatibility / Aliases
# -----------------------


@app.route("/add_tenant")
@login_required
def add_tenant_alias():
    return redirect(url_for("tenant_add"))


@app.route("/edit_tenant/<int:tenant_id>")
@login_required
def edit_tenant_alias(tenant_id):
    return redirect(url_for("tenant_edit", tenant_id=tenant_id))


@app.route("/add_payment")
@login_required
def add_payment_alias():
    tenant_id = request.args.get("tenant_id")
    if tenant_id:
        return redirect(url_for("payment_add", tenant_id=tenant_id))
    return redirect(url_for("payment_list"))


@app.route("/payment/edit-redirect")
@login_required
def payment_edit_redirect():
    return redirect(url_for("payment_list"))


# -----------------------
# Landlord Settings Import
# -----------------------

try:
    from rentme.landlord_settings import landlord_settings_bp
except ImportError as e:
    app.logger.warning("Failed to import landlord_settings: %s", e)

    # -----------------------
    # Run App (LOCAL DEV ONLY)
    # -----------------------
    import logging
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )

    logging.info(
        "🚀 Rentana Flask app starting on port %s...",
        os.getenv("PORT", 5000),
    )
