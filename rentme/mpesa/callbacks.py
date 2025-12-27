from flask import request, jsonify, session
from rentme.services.subscriptions import activate_subscription


@mpesa_bp.route("/mpesa/subscription-callback", methods=["POST"])
def subscription_callback():
    data = request.get_json()

    result_code = data["Body"]["stkCallback"]["ResultCode"]

    if result_code == 0:
        user_id = session.get("stk_user_id")
        plan_id = session.get("pending_plan")

        activate_subscription(user_id, plan_id)

        session.pop("pending_plan", None)

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})
