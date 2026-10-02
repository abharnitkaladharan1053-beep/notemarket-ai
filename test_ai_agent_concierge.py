"""
NoteMarket AI - Customer AI Concierge & Instant Verified Transaction Test Suite
Tests:
1. Customer Query Discovery & Best PDF Selection
2. Autonomous Quality, Syllabus Coverage & Legibility Verification
3. 'Already Paid' State Detection for Previously Purchased Notes
4. 1-Click Instant AI Transaction Settlement (with 'Payment Status: ALREADY PAID' & Download Entitlement)
5. In-Chat AI Concierge Natural Language Triggering
"""

import sys
import json
from pathlib import Path
import requests

# Prepend project root so backend can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure Windows UTF-8 console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:5500"

def test_1_find_best_note_autonomous_verification():
    print("\n--- TEST 1: Customer Query Discovery & Best PDF Selection ---")
    payload = {
        "query": "Find me the best comprehensive DBMS notes with solved PYQs for semester 5",
        "subject": "DBMS",
        "buyer_id": "test_student_101",
        "buyer_email": "student101@notemarket.ai"
    }

    r = requests.post(f"{BASE_URL}/api/ai/agent/find-best-note", json=payload, timeout=10)
    print("Status Code:", r.status_code)
    res = r.json()
    assert res.get("status") == "SUCCESS", "Expected status SUCCESS"

    best = res.get("best_note", {})
    badge = res.get("verification_badge", {})
    print(f"Selected Best Note: '{best.get('title')}' ({best.get('subject')})")
    print(f"Seller / Author:    {best.get('seller_name')} (Rating: {best.get('rating')}⭐)")
    print(f"Quality Score:      {badge.get('quality_score')}/100")
    print(f"Syllabus Coverage:  {badge.get('coverage_percentage')}%")
    print(f"Legibility Rating:  {badge.get('legibility')}")
    print(f"Fair Market Price:  INR {badge.get('fair_price')}")
    print(f"AI Rationale:       {res.get('recommendation_reason')}")
    print(f"Initial Payment:    {res.get('payment_status')}")

    assert badge.get("quality_score", 0) >= 90, "Quality score should be high"
    assert badge.get("coverage_percentage", 0) >= 70, "Coverage should be high"
    assert "DBMS" in best.get("subject", ""), "Should match DBMS"
    print(">>> PASS: AI Concierge autonomously verified and selected the best PDF.")
    return best

def test_2_instant_ai_purchase_and_already_paid(best_note):
    print("\n--- TEST 2: 1-Click Instant AI Transaction Settlement ---")
    note_id = str(best_note.get("id"))
    buyer_id = "test_student_101"
    buyer_email = "student101@notemarket.ai"

    # Execute 1-click instant AI purchase
    payload = {
        "note_id": note_id,
        "buyer_id": buyer_id,
        "buyer_email": buyer_email,
        "payment_method": "Instant Auto-Settled UPI"
    }

    r = requests.post(f"{BASE_URL}/api/ai/agent/instant-purchase", json=payload, timeout=10)
    print("Status Code:", r.status_code)
    res = r.json()
    receipt = res.get("receipt", {})

    print(f"Transaction Success:  {res.get('success')}")
    print(f"Payment Status:       {res.get('payment_status')}")
    print(f"Official Receipt:     {receipt.get('receipt_number')}")
    print(f"Amount Settled:       INR {receipt.get('amount_paid')}")
    print(f"Download Entitlement: {res.get('download_entitled')}")

    assert res.get("success") is True, "Purchase should succeed"
    assert res.get("payment_status") == "ALREADY PAID", "Payment status must be 'ALREADY PAID'"
    assert res.get("download_entitled") is True, "Download should be unlocked"
    print(">>> PASS: Transaction auto-settled and marked as ALREADY PAID.")

    print("\n--- TEST 3: 'Already Paid' Verification on Repeat Query ---")
    # Now query find-best-note again with the SAME user
    query_payload = {
        "query": "I need DBMS notes for university exams",
        "subject": "DBMS",
        "buyer_id": buyer_id,
        "buyer_email": buyer_email
    }
    r2 = requests.post(f"{BASE_URL}/api/ai/agent/find-best-note", json=query_payload, timeout=10)
    res2 = r2.json()
    print(f"Payment Status Detected: {res2.get('payment_status')}")
    print(f"Already Paid Flag:       {res2.get('already_paid')}")
    print(f"Recommended Action:      {res2.get('action')}")

    assert res2.get("already_paid") is True, "Must identify that user has already paid"
    assert res2.get("payment_status") == "ALREADY PAID", "Must show 'ALREADY PAID'"
    assert res2.get("action") == "download", "Action should be direct download"
    print(">>> PASS: AI Concierge recognized that user already paid and offered direct download.")

def test_4_natural_language_chat_concierge():
    print("\n--- TEST 4: Natural Language AI Chat Discovery Trigger ---")
    chat_payload = {
        "prompt": "Please find me the best Operating Systems notes for GTU exams",
        "model": "llama3.2"
    }

    r = requests.post(f"{BASE_URL}/api/ai/chat", json=chat_payload, timeout=10)
    print("Status Code:", r.status_code)
    res = r.json()
    reply = res.get("reply", "")
    print("Engine Source:", res.get("source"))
    print("\n--- AI Agent In-Chat Response Preview ---")
    print(reply[:500] + ("..." if len(reply) > 500 else ""))

    assert "Best Verified PDF" in reply or "Operating Systems" in reply, "Should recommend best PDF"
    assert "Quality Score" in reply, "Should show verified quality metrics"
    print(">>> PASS: Natural language query triggered autonomous AI Concierge recommendation.")

if __name__ == "__main__":
    print("=====================================================================")
    print("  NoteMarket AI - Autonomous Concierge Agent & Payment Verification  ")
    print("=====================================================================")
    best_note = test_1_find_best_note_autonomous_verification()
    test_2_instant_ai_purchase_and_already_paid(best_note)
    test_4_natural_language_chat_concierge()
    print("\n=====================================================================")
    print("  ALL AI CONCIERGE & TRANSACTION TESTS PASSED SUCCESSFULLY! ")
    print("=====================================================================")
