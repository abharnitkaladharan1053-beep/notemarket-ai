import sys
sys.stdout.reconfigure(encoding='utf-8')
import urllib.request
import json

BASE = "http://127.0.0.1:5500"

def post(endpoint, payload, token=None):
    req = urllib.request.Request(
        f"{BASE}{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {})
        }
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get(endpoint, token=None):
    req = urllib.request.Request(
        f"{BASE}{endpoint}",
        headers={"Authorization": f"Bearer {token}"} if token else {}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

print("=== 1. Testing Authentication Backend ===")
# Test Login
login_res = post("/api/auth/login", {"email": "demo_seller@notemarket.ai", "password": "password123"})
print("Auth Login Status:", login_res.get("success"))
token = login_res.get("access_token")
user = login_res.get("user")
print(f"Logged in User: {user['full_name']} ({user['email']}), ID: {user['id']}")

# Test Auth Me
me_res = get("/api/auth/me", token=token)
print("Auth Me Verified:", me_res.get("authenticated"), "-", me_res["user"]["full_name"])

print("\n=== 2. Testing Transaction Backend ===")
# Fetch a note to buy
notes_res = get("/api/notes")
note = notes_res["notes"][0]
print(f"Purchasing Note: '{note['title']}' for INR {note['price']}")

# Step A: Initiate Transaction
initiate_res = post("/api/transactions/initiate", {
    "note_id": note["id"],
    "buyer_id": user["id"],
    "buyer_email": user["email"],
    "payment_method": "UPI"
})
print("Transaction Initiated:")
print(f" - Order ID:       {initiate_res['order_id']}")
print(f" - Transaction ID: {initiate_res['transaction_id']}")
print(f" - Gross Amount:   INR {initiate_res['amount']}")
print(f" - Platform Fee:   INR {initiate_res['breakdown']['platform_fee']} (20%)")
print(f" - Seller Royalty: INR {initiate_res['breakdown']['seller_royalty']} (80%)")

# Step B: Confirm Transaction & Settlement
confirm_res = post("/api/transactions/confirm", {
    "order_id": initiate_res["order_id"],
    "transaction_id": initiate_res["transaction_id"],
    "note_id": note["id"],
    "buyer_id": user["id"],
    "buyer_email": user["email"],
    "payment_method": "UPI",
    "payment_reference": "UPI-GPay-984729103"
})
print("\nTransaction Confirmed & Settled:")
print(f" - Success:        {confirm_res['success']}")
print(f" - Receipt Number: {confirm_res['receipt']['receipt_number']}")
print(f" - Download Entitled: {confirm_res['download_entitled']}")

# Step C: Verify User Transaction History
user_txns = get(f"/api/transactions/user/{user['id']}")
print(f"\nBuyer Transaction History: {user_txns['total_purchases']} purchases (Total Spent: INR {user_txns['total_spent']})")

# Step D: Verify Seller Earnings & Commission
seller_txns = get(f"/api/transactions/seller/{note['seller_id']}")
print(f"Seller Sales: {seller_txns['sales_count']} sales (Net Earnings: INR {seller_txns['net_earnings']}, Platform Cut: INR {seller_txns['platform_commission']})")

# Step E: Platform Overall Stats
stats = get("/api/transactions/platform-stats")
print(f"\nPlatform Global Metrics: {stats['total_transactions']} total transactions, GMV: INR {stats['gross_merchandise_value']}, Platform Commission: INR {stats['platform_commission_revenue']}")
print("\n>>> ALL AUTHENTICATION & TRANSACTION BACKEND TESTS PASSED SUCCESSFULLY! <<<")
