import sys
sys.stdout.reconfigure(encoding='utf-8')
import urllib.request
import json

BASE = "http://127.0.0.1:5500"

def post(endpoint, payload):
    req = urllib.request.Request(
        f"{BASE}{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get(endpoint):
    req = urllib.request.Request(f"{BASE}{endpoint}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def patch(endpoint, payload):
    req = urllib.request.Request(
        f"{BASE}{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

print("=== TESTING SUPPORT BACKEND ===")

# 1. Test FAQs endpoint
faqs = get("/api/support/faqs")
print(f"1. FAQs retrieved: {len(faqs['faqs'])} FAQ items available")

# 2. Submit Support Ticket
ticket_data = {
    "name": "Rohan Sharma",
    "email": "rohan.sharma@gtu.edu",
    "category": "Download Issue",
    "subject": "Unable to download DBMS unit 4 notes after UPI payment",
    "message": "I paid INR 49 via UPI (ref: UPI-984728) but the download link timed out. Please assist.",
    "note_id": "c687ce52-dbca-46ad-a2db-53ff8fc8c2dd",
    "note_title": "DBMS Complete Theory & Solved PYQs",
    "priority": "High"
}
res = post("/api/support/tickets", ticket_data)
ticket_id = res["ticket_id"]
print(f"2. Ticket Created successfully: ID = {ticket_id}, Status = {res['status']}")

# 3. Track Ticket Status
tracking = get(f"/api/support/tickets/{ticket_id}")
print(f"3. Ticket Tracking Verified: Found = {tracking['found']}, Subject: '{tracking['ticket']['subject']}'")

# 4. Admin Response and Status Update
update_payload = {
    "status": "resolved",
    "reply": "Your payment reference UPI-984728 was verified. We have reset your signed download link in 'My Purchases'. You can also download directly from your dashboard.",
    "admin_name": "NoteMarket Support Desk"
}
update_res = patch(f"/api/support/tickets/{ticket_id}/status", update_payload)
print(f"4. Ticket Resolution: Status = {update_res['ticket']['status']}, Replies = {len(update_res['ticket']['replies'])}")
print(f"   Admin Reply Snippet: '{update_res['ticket']['replies'][0]['message'][:80]}...'")

# 5. List all tickets
ticket_list = get("/api/support/tickets")
print(f"5. All Tickets Count: {ticket_list['total_tickets']} tickets logged in support desk")

print("\n>>> SUPPORT SYSTEM BACKEND VERIFICATION SUCCESSFUL! <<<")
