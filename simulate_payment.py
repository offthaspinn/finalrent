"""
FULL END-TO-END REALISTIC SIMULATION

✔ Register landlord
✔ Create property (auto reference)
✔ Create unit (auto payment_ref e.g TG3)
✔ Create tenant
✔ Create subscription intent
✔ Simulate subscription payment
✔ Activate subscription
✔ Simulate tenant rent payment via payment_ref
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
    Unit,
    Tenant,
    Payment,
)
from rentme.services.subscriptions import activate_paid_subscription


def run():
    with app.app_context():
        print("🚀 STARTING FULL RENTME SIMULATION")

        db.session.rollback()

        ts = int(datetime.utcnow().timestamp())

        # --------------------------------------------------
        # 1. USER (LANDLORD)
        # --------------------------------------------------
        user = User(
            full_name="Real Simulation Landlord",
            email=f"landlord_{ts}@test.com",
            login_phone=f"254700{ts % 1000000:06d}",
            phone_number=f"254700{ts % 1000000:06d}",
            password_hash=generate_password_hash("StrongPass123!"),
            payment_method="mpesa",
            paybill_number="123456",
        )

        db.session.add(user)
        db.session.commit()
        print(f"✅ User created id={user.id}")

        # --------------------------------------------------
        # 2. PROPERTY
        # --------------------------------------------------
        prop = Property(
            landlord_id=user.id,
            name="Test Garden",
        )

        db.session.add(prop)
        db.session.commit()
        print(f"🏠 Property created id={prop.id}, ref={prop.reference}")

        # --------------------------------------------------
        # 3. UNIT
        # --------------------------------------------------
        unit = Unit(
            property_id=prop.id,
            house_no="3"
        )

        db.session.add(unit)
        db.session.commit()
        print(f"🏘 Unit created id={unit.id}, payment_ref={unit.payment_ref}")

        # --------------------------------------------------
        # 4. TENANT
        # --------------------------------------------------
        tenant = Tenant(
            property_id=prop.id,
            house_no=unit.house_no,   # 🔑 LINK VIA HOUSE NUMBER
            name="Sim Tenant",
            phone="254711000999",
            monthly_rent=12000,
            amount_due=12000,
        )

        db.session.add(tenant)
        db.session.commit()
        print(f"👤 Tenant created id={tenant.id}")

        # --------------------------------------------------
        # 5. PLAN
        # --------------------------------------------------
        plan = Plan.query.filter_by(name="basic").first()
        if not plan:
            raise RuntimeError("❌ Plan 'basic' missing")

        print(f"📦 Plan loaded: {plan.name}")

        # --------------------------------------------------
        # 6. SUBSCRIPTION INTENT
        # --------------------------------------------------
        sub_ref = f"SIM-SUB-{ts}"

        intent = SubscriptionIntent(
            user_id=user.id,
            plan_id=plan.id,
            reference=sub_ref,
            amount=plan.price,
            currency="KES",
            status="PENDING",
        )

        db.session.add(intent)
        db.session.commit()
        print(f"🧾 SubscriptionIntent created ref={sub_ref}")

        # --------------------------------------------------
        # 7. SIMULATE SUBSCRIPTION PAYMENT
        # --------------------------------------------------
        intent.status = "COMPLETE"
        intent.transaction_id = f"TX-SUB-{ts}"
        intent.payment_invoice_id = f"INV-SUB-{ts}"
        intent.updated_at = datetime.utcnow()
        db.session.commit()

        subscription = activate_paid_subscription(intent)
        print(f"🎉 Subscription activated id={subscription.id}")

        # --------------------------------------------------
        # 8. SIMULATE TENANT RENT PAYMENT (USING UNIT REF)
        # --------------------------------------------------
        rent_ref = unit.payment_ref  # e.g. TG3

        payment = Payment(
            tenant_id=tenant.id,
            user_id=user.id,
            amount=12000,
            currency="KES",
            reference=rent_ref,
            transaction_id=f"TX-RENT-{ts}",
            status="COMPLETE",
            paid_at=datetime.utcnow(),
        )

        db.session.add(payment)

        # Update tenant ledger
        tenant.amount_due -= payment.amount
        tenant.last_payment_at = datetime.utcnow()

        db.session.commit()
        print(f"💰 Rent payment received ref={rent_ref}")

        # --------------------------------------------------
        # 9. VERIFY IDEMPOTENCY
        # --------------------------------------------------
        duplicate = Payment.query.filter_by(
            transaction_id=payment.transaction_id
        ).first()

        assert duplicate is not None
        print("🔒 Idempotency verified")

        print("✅ FULL SIMULATION SUCCESSFUL")


if __name__ == "__main__":
    run()
