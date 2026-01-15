from rentme.models import Subscription, Property

def can_create_property(user_id: int) -> tuple[bool, str | None]:
    subscription = (
        Subscription.query
        .filter_by(user_id=user_id, is_active=True)
        .first()
    )

    if not subscription:
        return False, "You do not have an active subscription."

    current_count = Property.query.filter_by(owner_id=user_id).count()

    if current_count >= subscription.properties_allowed:
        return (
            False,
            f"Your plan allows only {subscription.properties_allowed} properties."
        )

    return True, None
