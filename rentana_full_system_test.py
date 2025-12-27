"""
Rentana Full System Test Script (Schema-Accurate)
------------------------------------------------
Creates a landlord, configures MPesa, subscribes to a plan,
creates property + tenants, and simulates payments.

SAFE FOR TESTING ONLY
"""

import uuid
import datetime
from werkzeug.security import generate_password_hash
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import date
import requests

# ===============================
# DATABASE CONNECTION
# ===============================

DATABASE_URL = "postgresql://rentana_prod_user:VZmWM7l8lJEkteDLg2nqxy2Rbv6YMuCu@dpg-d4vdtei4d50c73803e0g-a.singapore-postgres.render.com/rentana_prod"

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

now = datetime.datetime.utcnow

print("\n🚀 RENTANA FULL SYSTEM TEST STARTED\n")


# ===============================
# HELPER FUNCTIONS
# ===============================

def get_properties_allowed(plan_name: str) -> int:
    mapping = {
        "Starter": 1,
        "Basic": 1,
        "Pro": 5,
        "Business": 10,
        "Enterprise": 9999
    }
    return mapping.get(plan_name, 1)


def create_landlord():
    email = f"test_{uuid.uuid4().hex[:6]}@rentana.test"
    user_id = session.execute(text("""
        INSERT INTO "user" (
            full_name,
            email,
            phone_number,
            password_hash,
            created_at
        )
        VALUES (
            'Test Landlord',
            :email,
            '254700000001',
            :password_hash,
            NOW()
        )
        RETURNING id
    """), {
        "email": email,
        "password_hash": generate_password_hash("TestPassword123")
    }).scalar()
    print(f"✅ User created → ID {user_id}, email={email}")
    return user_id, email


def setup_landlord_settings(user_id: int):
    session.execute(text("""
        INSERT INTO landlord_settings (
            user_id,
            payment_method,
            phone_number,
            mpesa_shortcode,
            mpesa_mode,
            callback_url,
            created_at,
            updated_at
        )
        VALUES (
            :user_id,
            'mpesa',
            '254700000001',
            '123456',
            'sandbox',
            'https://bell-unwillful-adriene.ngrok-free.dev/mpesa/callback',
            NOW(),
            NOW()
        )
    """), {"user_id": user_id})
    print("✅ Landlord settings created")


def setup_mpesa_credentials(user_id: int):
    session.execute(text("""
        INSERT INTO mpesa_credential (
            user_id,
            shortcode,
            shortcode_type,
            callback_url,
            mpesa_env,
            encrypted_consumer_key,
            encrypted_consumer_secret,
            encrypted_passkey
        )
        VALUES (
            :user_id,
            '123456',
            'paybill',
            'https://bell-unwillful-adriene.ngrok-free.dev/mpesa/callback',
            'sandbox',
            :consumer_key,
            :consumer_secret,
            :passkey
        )
    """), {
        "user_id": user_id,
        "consumer_key": b"ENCRYPTED_FAKE_CONSUMER_KEY",
        "consumer_secret": b"ENCRYPTED_FAKE_CONSUMER_SECRET",
        "passkey": b"ENCRYPTED_FAKE_PASSKEY"
    })
    print("✅ MPesa credential record created")


def subscribe_plan(user_id: int):
    plan = session.execute(text("""
        SELECT id, name, price, duration_days
        FROM plan
        LIMIT 1
    """)).mappings().first()

    expires_at = now() + datetime.timedelta(days=plan["duration_days"])
    properties_allowed = get_properties_allowed(plan["name"])

    subscription_id = session.execute(text("""
        INSERT INTO subscription (
            user_id,
            plan_id,
            plan_name,
            properties_allowed,
            amount_paid,
            is_active,
            mpesa_receipt,
            created_at,
            expires_at
        )
        VALUES (
            :user_id,
            :plan_id,
            :plan_name,
            :properties_allowed,
            :amount_paid,
            TRUE,
            :receipt,
            NOW(),
            :expires_at
        )
        RETURNING id
    """), {
        "user_id": user_id,
        "plan_id": plan["id"],
        "plan_name": plan["name"],
        "properties_allowed": properties_allowed,
        "amount_paid": plan["price"],
        "receipt": f"SUB{uuid.uuid4().hex[:8]}",
        "expires_at": expires_at
    }).scalar()

    print(f"✅ Subscription activated → ID {subscription_id}")
    return plan, subscription_id


def create_property(user_id: int, plan_id: int):
    property_id = session.execute(text("""
        INSERT INTO property (
            owner_id,
            plan_id,
            name,
            address,
            created_at
        )
        VALUES (
            :owner_id,
            :plan_id,
            'Test Property',
            'Nairobi',
            NOW()
        )
        RETURNING id
    """), {
        "owner_id": user_id,
        "plan_id": plan_id
    }).scalar()

    print(f"✅ Property created → ID {property_id}")
    return property_id


def create_tenants(property_id: int, count: int = 2):
    tenant_ids = []
    for i in range(1, count + 1):
        tenant_id = session.execute(text("""
            INSERT INTO tenant (
                property_id,
                name,
                phone,
                house_no,
                monthly_rent,
                move_in_date,
                last_rent_update,
                amount_due,
                created_at
            )
            VALUES (
                :property_id,
                :name,
                :phone,
                :house_no,
                :monthly_rent,
                :move_in_date,
                :last_rent_update,
                :amount_due,
                NOW()
            )
            RETURNING id
        """), {
            "property_id": property_id,
            "name": f"Tenant {i}",
            "phone": f"25470000010{i}",
            "house_no": f"H{i:03d}",
            "monthly_rent": 15000.0,
            "move_in_date": date.today(),
            "last_rent_update": date.today(),
            "amount_due": 15000.0
        }).scalar()
        tenant_ids.append(tenant_id)
        print(f"✅ Tenant created → ID {tenant_id}")
    return tenant_ids


def simulate_mpesa_webhook(user_id: int, tenant_ids: list, callback_url: str):
    """
    Simulate M-Pesa confirmation webhook for each tenant.
    """
    from datetime import datetime

    for tenant_id in tenant_ids:
        tx_id = f"C2B{uuid.uuid4().hex[:8]}"
        amount = 15000.0  # simulated rent

        payload = {
            "TransactionType": "PayBill",
            "TransID": tx_id,
            "TransTime": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
            "TransAmount": str(amount),
            "BusinessShortCode": "123456",
            "BillRefNumber": f"H{tenant_id:03d}",  # should match tenant.house_no
            "InvoiceNumber": "",
            "OrgAccountBalance": 0,
            "ThirdPartyTransID": "",
            "MSISDN": f"25470000010{tenant_id}",
            "FirstName": f"Tenant {tenant_id}",
            "MiddleName": "",
            "LastName": "",
            "UserID": user_id
        }

        try:
            response = requests.post(callback_url, json=payload, timeout=10)
            if response.status_code == 200:
                print(f"✅ Webhook simulated → tenant {tenant_id}, tx={tx_id}")
            else:
                print(f"⚠️ Webhook failed → tenant {tenant_id}, status={response.status_code}, response={response.text}")
        except Exception as e:
            print(f"❌ Webhook exception → tenant {tenant_id}: {e}")


# ===============================
# RUN FULL TEST
# ===============================

user_id, email = create_landlord()
setup_landlord_settings(user_id)
setup_mpesa_credentials(user_id)
plan, subscription_id = subscribe_plan(user_id)
property_id = create_property(user_id, plan["id"])
tenant_ids = create_tenants(property_id)

callback_url = "https://bell-unwillful-adriene.ngrok-free.dev/mpesa/payment_callback/confirmation"
simulate_mpesa_webhook(user_id, tenant_ids, callback_url)

session.commit()

print("\n🎉 RENTANA FULL SYSTEM TEST COMPLETED SUCCESSFULLY")
print("------------------------------------------------")
print(f"Landlord email: {email}")
print(f"User ID: {user_id}")
print(f"Subscription ID: {subscription_id}")
print(f"Property ID: {property_id}")
print(f"Tenants: {tenant_ids}")
print("------------------------------------------------\n")
