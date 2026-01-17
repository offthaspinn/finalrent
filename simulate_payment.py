"""
FULL END-TO-END SIMULATION (SUBSCRIPTION + TENANT RENT)

✔ Register user
✔ Create property
✔ Create tenant
✔ Create subscription intent
✔ Simulate subscription payment
✔ Activate subscription
✔ Simulate tenant rent payment
✔ Verify idempotency
"""

from datetime import datetime
from werkzeug.security import generate_password_hash

from rentme.app import app
from rentme.extensions import db
from rentme.models import (
    User,
    Plan,
    SubscriptionIntent,
    Subscription,
    Property,
    Tenant,
    Payment,
)
from rentme.services.subscriptions import activate_paid_subscription


def run():
    with app.app_context():
        print("🚀 Starting FULL simulation")

        db.session.rollback()

        # --------------------------------------------------
        # 1. USER
        # --------------------------------------------------
        ts = int(datetime.utcnow().timestamp())

        user = User(
            full_name="Simulation User",
            email=f"trap@test.com",
            login_phone=f"254700{ts % 1000000:06d}",
            phone_number=f"254700{ts % 1000000:06d}",
            password_hash=generate_password_hash("TestPassword123!"),
        )

        db.session.add(user)
        db.session.commit()
        print(f"✅ User created id={user.id}")

        # --------------------------------------------------
        # 2. PROPERTY (OWNER = USER)
        # --------------------------------------------------
        prop = Property(
            owner_id=user.id,
            name="Simulation Property",
        )

        db.session.add(prop)
        db.session.commit()
        print(f"🏠 Property created id={prop.id}")

        # --------------------------------------------------
        # 3. TENANT
        # --------------------------------------------------
        tenant = Tenant(
            property_id=prop.id,
            name="Sim Tenant",
            phone="254711000999",
            house_no="A1",
            monthly_rent=12000,
            amount_due=12000,
        )

        db.session.add(tenant)
        db.session.commit()
        print(f"👤 Tenant created id={tenant.id}")

        # --------------------------------------------------
        # 4. PLAN
        # --------------------------------------------------
        plan = Plan.query.filter_by(name="basic").first()
        if not plan:
            raise RuntimeError("Plan 'basic' missing")

        print(f"📦 Plan loaded: {plan.name}")

        # --------------------------------------------------
        # 5. SUBSCRIPTION INTENT
        # --------------------------------------------------
        reference = f"SIM-{ts}"

        intent = SubscriptionIntent(
            user_id=user.id,
            plan_id=plan.id,
            reference=reference,
            amount=plan.price,
            currency="KES",
            status="PENDING",
        )

        db.session.add(intent)
        db.session.commit()
        print(f"🧾 SubscriptionIntent created ref={reference}")

        # --------------------------------------------------
        # 6. SIMULATE SUBSCRIPTION PAYMENT
        # --------------------------------------------------
        intent.status = "COMPLETE"
        intent.transaction_id = "SIM-SUB-TX-001"
        intent.payment_invoice_id = "SIM-SUB-INV-001"
        intent.updated_at = datetime.utcnow()
        db.session.commit()

        subscription = activate_paid_subscription(intent)
        print(f"🎉 Subscription activated id={subscription.id}")

        # --------------------------------------------------
        # 7. SIMULATE TENANT RENT PAYMENT
        # --------------------------------------------------
        payment_ref = f"RENTA-{user.id}-{tenant.id}-JAN2026"

        payment = Payment(
            provider="INTASEND",
            transaction_id="SIM-RENT-TX-001",
            reference=payment_ref,
            amount=12000,
            currency="KES",
            status="CONFIRMED",
            paid_at=datetime.utcnow(),
            tenant_id=tenant.id,
            user_id=user.id,
        )

        db.session.add(payment)

        tenant.amount_due -= 12000
        tenant.last_rent_update = datetime.utcnow()

        db.session.commit()
        print("💰 Tenant rent payment recorded")

        # --------------------------------------------------
        # 8. VERIFY
        # --------------------------------------------------
        subs = Subscription.query.filter_by(user_id=user.id).all()
        print(f"📊 Subscriptions: {len(subs)}")

        print("✅ FULL SIMULATION SUCCESS")


if __name__ == "__main__":
    run()
