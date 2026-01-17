from rentme.services.subscriptions import admin_force_activate


@admin_bp.route("/subscriptions/force-activate/<int:user_id>")
@login_required
@admin_required
def force_activate_subscription(user_id):
    user = User.query.get_or_404(user_id)
    plan = Plan.query.filter_by(name="Pro").first_or_404()

    admin_force_activate(user, plan)

    audit(
        current_user,
        "admin_force_subscription",
        f"user_id={user.id}"
    )

    flash(f"Subscription activated for {user.email}", "success")
    return redirect(url_for("admin.users"))
