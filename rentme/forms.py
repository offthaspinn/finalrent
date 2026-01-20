# rentme/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, FloatField, DateField
from wtforms.validators import DataRequired, Email, EqualTo, Optional, Length


# ======================================================
# 🔐 REGISTER FORM
class RegisterForm(FlaskForm):
    first_name = StringField(
        "First Name",
        validators=[DataRequired()],
        render_kw={
            "autocomplete": "given-name",
            "autocapitalize": "words",
            "spellcheck": "false",
        },
    )

    last_name = StringField(
        "Last Name",
        validators=[DataRequired()],
        render_kw={
            "autocomplete": "family-name",
            "autocapitalize": "words",
            "spellcheck": "false",
        },
    )

    email = StringField(
        "Email",
        validators=[DataRequired(), Email()],
        render_kw={"autocomplete": "off", "inputmode": "email"},
    )

    login_phone = StringField(
        "Phone",
        render_kw={"autocomplete": "off", "inputmode": "tel"},
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
# 💳 LANDLORD MPESA 
# ======================================================
class PaymentSettingsForm(FlaskForm):
    # ----------------------------
    # Payment Display / Routing
    # ----------------------------
    payment_method = SelectField(
        "Payment Method",
        choices=[
            ("", "Select"),
            ("Paybill", "Paybill"),
            ("Till", "Till / BuyGoods"),
            ("SendMoney", "Send Money"),
        ],
        validators=[Optional()],
    )

    phone_number = StringField(
        "Display Phone (optional)",
        validators=[Optional()],
    )

    # ----------------------------
    # Bank Payout (optional)
    # ----------------------------
    bank_name = StringField("Bank Name", validators=[Optional()])
    bank_account_name = StringField("Account Name", validators=[Optional()])
    bank_account_number = StringField("Account Number", validators=[Optional()])
    bank_branch = StringField("Branch", validators=[Optional()])

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


# ======================================================
# 🏠 UNIT FORM
# ======================================================
class UnitForm(FlaskForm):
    house_no = StringField(
        "House / Unit Number",
        validators=[DataRequired(), Length(max=20)],
        render_kw={
            "autocomplete": "off",
            "placeholder": "e.g. A1, B2, 101"
        }
    )

    submit = SubmitField("Save Unit")
