# rentme/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, FloatField, DateField
from wtforms.validators import DataRequired, Email, EqualTo, Optional, Length


# ======================================================
# 🔐 REGISTER FORM
# ======================================================
class RegisterForm(FlaskForm):
    full_name = StringField(
        "Full Name",
        validators=[DataRequired()],
        render_kw={
            "autocomplete": "off",
            "autocapitalize": "off",
            "spellcheck": "false",
        },
    )

    email = StringField(
        "Email",
        validators=[DataRequired(), Email()],
        render_kw={"autocomplete": "off", "inputmode": "email"},
    )

    login_phone = StringField(
        "Phone", render_kw={"autocomplete": "off", "inputmode": "tel"}
    )

    password = PasswordField(
        "Password",
        validators=[DataRequired()],
        render_kw={"autocomplete": "new-password"},
    )

    confirm = PasswordField(
        "Confirm Password",
        validators=[DataRequired(), EqualTo("password")],
        render_kw={"autocomplete": "new-password"},
    )

    submit = SubmitField("Register")


# ======================================================
# 🔑 LOGIN FORM
# ======================================================
class LoginForm(FlaskForm):
    identifier = StringField(
        "Email or Phone",
        validators=[DataRequired()],
        render_kw={"autocomplete": "off", "inputmode": "text"},
    )

    password = PasswordField(
        "Password",
        validators=[DataRequired()],
        render_kw={"autocomplete": "new-password"},
    )

    submit = SubmitField("Login")


# ======================================================
# 🔁 FORGOT PASSWORD
# ======================================================
class ForgotPasswordForm(FlaskForm):
    email_or_phone = StringField(
        "Email or Phone",
        validators=[DataRequired()],
        render_kw={
            "autocomplete": "off",
            "autocapitalize": "off",
            "spellcheck": "false",
        },
    )

    submit = SubmitField("Send Reset Code")


# ======================================================
# 🏠 TENANT FORM
# ======================================================
class TenantForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[DataRequired()],
        render_kw={"autocomplete": "off"}
    )

    phone = StringField(
        "Phone",
        validators=[DataRequired()],
        render_kw={"autocomplete": "off", "inputmode": "tel"},
    )

    national_id = StringField(
        "National ID",
        validators=[Optional()],
        render_kw={"autocomplete": "off"}
    )

    house_no = StringField(
        "House No",
        validators=[DataRequired()],
        render_kw={"autocomplete": "off"}
    )

    monthly_rent = FloatField(
        "Monthly Rent",
        validators=[DataRequired()],
        render_kw={"autocomplete": "off", "inputmode": "numeric"},
    )

    move_in_date = DateField(
        "Move-in Date",
        format="%Y-%m-%d",
        validators=[Optional()],
        render_kw={"autocomplete": "off"},
    )

    submit = SubmitField("Save")


# ======================================================
# ======================================================
# 💳 LANDLORD MPESA + KCB / PAYMENT SETTINGS
# ======================================================
class PaymentSettingsForm(FlaskForm):
    # ----------------------------
    # MPesa Fields
    # ----------------------------
    payment_method = SelectField(
        "Payment Method",
        choices=[
            ("", "Select"),
            ("Paybill", "Paybill (C2B)"),
            ("Till", "Till / BuyGoods"),
            ("Send Money", "Send Money (P2P)"),
        ],
        validators=[Optional()],
        render_kw={"autocomplete": "off"},
    )

    paybill_number = StringField(
        "Paybill Number", validators=[Optional()], render_kw={"autocomplete": "off"}
    )

    till_number = StringField(
        "Till / BuyGoods Number",
        validators=[Optional()],
        render_kw={"autocomplete": "off"},
    )

    send_money_number = StringField(
        "Send Money Receiver (phone)",
        validators=[Optional()],
        render_kw={"autocomplete": "off", "inputmode": "tel"},
    )

    phone_number = StringField(
        "Display Phone (optional)",
        validators=[Optional()],
        render_kw={"autocomplete": "off"},
    )

    mpesa_consumer_key = StringField(
        "Daraja: Consumer Key",
        validators=[Optional()],
        render_kw={"autocomplete": "off"},
    )

    mpesa_consumer_secret = PasswordField(
        "Daraja: Consumer Secret",
        validators=[Optional()],
        render_kw={"autocomplete": "new-password"},
    )

    mpesa_shortcode = StringField(
        "BusinessShortCode / Shortcode",
        validators=[Optional()],
        render_kw={"autocomplete": "off"},
    )

    mpesa_passkey = PasswordField(
        "Daraja: Passkey",
        validators=[Optional()],
        render_kw={"autocomplete": "new-password"},
    )

    mpesa_mode = SelectField(
        "Daraja Mode",
        choices=[("production", "Production"), ("sandbox", "Sandbox")],
        validators=[Optional()],
        render_kw={"autocomplete": "off"},
    )

    callback_url = StringField(
        "MPesa Callback URL (optional)",
        validators=[Optional()],
        render_kw={"autocomplete": "off"},
    )

    # ----------------------------
    # KCB Fields
    # ----------------------------
    kcb_api_key = StringField(
        "KCB API Key",
        validators=[Optional()],
        render_kw={"autocomplete": "off"},
    )

    kcb_paybill = StringField(
        "KCB Paybill",
        validators=[Optional()],
        render_kw={"autocomplete": "off"},
    )

    kcb_env = SelectField(
        "KCB Mode",
        choices=[("sandbox", "Sandbox"), ("live", "Live")],
        validators=[Optional()],
        render_kw={"autocomplete": "off"},
    )

    kcb_callback_url = StringField(
        "KCB Callback URL (optional)",
        validators=[Optional()],
        render_kw={"autocomplete": "off"},
    )

    submit = SubmitField("Save Settings")

# 🔐 RESET PASSWORD
# ======================================================
class ResetPasswordForm(FlaskForm):
    identifier = StringField(
        "Email or Phone", validators=[DataRequired()], render_kw={"autocomplete": "off"}
    )

    code = StringField(
        "Reset Code", validators=[DataRequired()], render_kw={"autocomplete": "off"}
    )

    password = PasswordField(
        "New Password",
        validators=[DataRequired(), Length(min=6)],
        render_kw={"autocomplete": "new-password"},
    )

    confirm_password = PasswordField(
        "Confirm Password",
        validators=[DataRequired(), EqualTo("password")],
        render_kw={"autocomplete": "new-password"},
    )

    submit = SubmitField("Reset Password")


# ======================================================
# 📦 SUBSCRIPTION FORM
# ======================================================
# ======================================================
# 💳 SUBSCRIPTION / PAYMENT FORM
# ======================================================
class SubscriptionForm(FlaskForm):
    phone = StringField(
        "M-Pesa Phone Number",
        validators=[DataRequired()],
        render_kw={
            "autocomplete": "off",
            "inputmode": "tel",
            "placeholder": "07XXXXXXXX"
        }
    )

    submit = SubmitField("Subscribe & Pay")


# 🏠 CREATE PROPERTY FORM
# ======================================================
class CreatePropertyForm(FlaskForm):
    name = StringField(
        "Property Name",
        validators=[DataRequired()],
        render_kw={"autocomplete": "off", "placeholder": "Enter property name"}
    )

    password = PasswordField(
        "Confirm Password",
        validators=[DataRequired()],
        render_kw={"autocomplete": "new-password", "placeholder": "Confirm your password"}
    )

    submit = SubmitField("Create")    
