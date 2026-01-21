from flask import Blueprint, request, jsonify, current_app
from rentme.extensions import db
from rentme.models import Subscription, SubscriptionIntent

mpesa_bp = Blueprint("mpesa", __name__, url_prefix="/mpesa")


@mpesa_bp.route("/callback", methods=["POST"])
def mpesa_callback():
    data = request.json
    current_app.logger.info("📩 MPESA CALLBACK: %s", data)

    api_ref = data.get("api_ref")
    status = data.get("state")

    intent = SubscriptionIntent.query.filter_by(reference=api_ref).first()
    if not intent:
        return jsonify(ok=False), 404

    if status == "COMPLETE":
        intent.status = "PAID"

        subscription = Subscription.activate_from_intent(intent)
        db.session.add(subscription)

    elif status == "FAILED":
        intent.status = "FAILED"

    db.session.commit()
    return jsonify(ok=True)
