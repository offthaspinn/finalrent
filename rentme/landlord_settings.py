# rentme/landlord_settings.py
import os
import base64
import requests
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from .extensions import db
from .models import LandlordSettings
from .forms import PaymentSettingsForm
from .security.crypto import encrypt, decrypt

# -------------------------------------------------
# -------------------------------------------------
# BLUEPRINT (updated unique name)
# -------------------------------------------------
landlord_settings_bp = Blueprint("landlord_settings_bp", __name__, url_prefix="/landlord")

# -------------------------------------------------
# Helper: get or create the landlord's settings row
# -------------------------------------------------
def get_or_create_settings():
    s = LandlordSettings.query.filter_by(user_id=current_user.id).first()

    if not s:
        s = LandlordSettings(
            user_id=current_user.id,
            master_paybill="INTASEND",
            master_account_format="PR-XXXX-U-XX",
        )
        db.session.add(s)
        db.session.commit()

    return s

# -------------------------------------------------
# SETTINGS PAGE — GET + POST
@landlord_settings_bp.route("/payment", methods=["GET", "POST"])
@login_required
def payment_settings():
    settings = get_or_create_settings()
    form = PaymentSettingsForm(obj=settings)

    if form.validate_on_submit():
        settings.bank_name = form.bank_name.data
        settings.bank_account_name = form.bank_account_name.data
        settings.bank_account_number = form.bank_account_number.data
        settings.bank_branch = form.bank_branch.data

        db.session.commit()
        flash("Payout settings updated", "success")
        return redirect(url_for("landlord_settings_bp.payment_settings"))

    return render_template(
        "settings_payment.html",
        form=form,
        settings=settings,   # for read-only master paybill display
        properties=current_user.properties,
    )
