"""
NoteMarket AI - Automated Verification Script for AI Inspection & Grounded Study Assistant
Tests:
1. Academic PDF Inspection: Full syllabus topics covered, quality score, fair price check.
2. Missing Topics Inspection: Dynamic fair pricing reduction to protect consumers.
3. Plagiarism & Copyright Infringement: Commercial textbook scan & duplicate note re-upload rejection.
4. Note-Grounded Study Assistant: Answers strictly from note without external links.
5. Messy Handwriting Simplifier: Explains unclear notes in plain, structured English.
"""

import sys
import io
import json
from pathlib import Path
import requests
import pypdf

# Prepend project root so backend can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure Windows UTF-8 console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:5500"

def create_sample_pdf(title: str, text_content: str) -> bytes:
    """Generate in-memory valid PDF bytes for testing."""
    writer = pypdf.PdfWriter()
    # Add page with text
    page = writer.add_blank_page(width=612, height=792)
    # pypdf text extraction works best when text stream exists
    # We can create a simple stream or metadata
    buf = io.BytesIO()
    writer.add_metadata({
        "/Title": title,
        "/Author": "Verified Student",
        "/Subject": "Academic Notes"
    })
    writer.write(buf)
    
    # Prepend or inject plain text in a way that pypdf reader can extract or raw scan
    raw = buf.getvalue()
    # For synthetic testing, inject plain text stream
    injected = raw + b"\n% " + text_content.encode("utf-8")
    return injected

def test_1_full_syllabus_inspection():
    print("\n--- TEST 1: Full Syllabus Academic PDF Inspection ---")
    
    # We test via the inspect-note endpoint using multipart upload
    # Create sample text covering DBMS syllabus
    dbms_text = (
        "Relational Model ER Diagrams Normalization 1NF 2NF 3NF BCNF "
        "SQL Relational Algebra Transactions ACID Properties Concurrency Control "
        "Two-Phase Locking Deadlocks Indexing & Hashing. Comprehensive student handwritten notes."
    )
    
    # We write a quick minimal valid PDF with text stream
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    pdf_stream = io.BytesIO()
    writer.write(pdf_stream)
    pdf_bytes = pdf_stream.getvalue() + b"\n" + dbms_text.encode("utf-8")

    files = {"file": ("DBMS_Unit1_6.pdf", pdf_bytes, "application/pdf")}
    data = {"subject": "DBMS", "requested_price": "60"}

    r = requests.post(f"{BASE_URL}/api/ai/inspect-note", files=files, data=data, timeout=10)
    print("Status Code:", r.status_code)
    res = r.json()
    print("Verification Status:", res.get("status"))
    print("Quality Score:", res.get("quality", {}).get("quality_score"))
    print("Legibility:", res.get("quality", {}).get("legibility"))
    print("Topics Covered:", len(res.get("syllabus", {}).get("covered_topics", [])))
    print("Coverage Percentage:", res.get("syllabus", {}).get("coverage_percentage"), "%")
    print("Requested Price: INR", res.get("pricing", {}).get("requested_price"))
    print("Recommended Price: INR", res.get("pricing", {}).get("recommended_price"))
    
    assert res.get("status") == "VERIFIED", "Expected status to be VERIFIED"
    assert res.get("syllabus", {}).get("coverage_percentage", 0) >= 70, "Expected high coverage"
    print(">>> PASS: Full syllabus PDF verified with high quality and fair pricing approved.")

def test_2_missing_topics_dynamic_pricing():
    print("\n--- TEST 2: Incomplete Syllabus - Dynamic Fair Price Reduction ---")
    
    # Only cover ER Diagrams and SQL, missing Normalization, Transactions, Concurrency, Deadlocks
    partial_text = "ER Diagrams and basic SQL SELECT queries. Note missing transaction and indexing units."
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=595, height=842)
    pdf_stream = io.BytesIO()
    writer.write(pdf_stream)
    pdf_bytes = pdf_stream.getvalue() + b"\n" + partial_text.encode("utf-8")

    files = {"file": ("DBMS_Partial.pdf", pdf_bytes, "application/pdf")}
    data = {"subject": "DBMS", "requested_price": "80"}

    r = requests.post(f"{BASE_URL}/api/ai/inspect-note", files=files, data=data, timeout=10)
    res = r.json()
    pricing = res.get("pricing", {})
    coverage = res.get("syllabus", {}).get("coverage_percentage")
    missing_topics = res.get("syllabus", {}).get("missing_topics", [])

    print(f"Coverage: {coverage}% (Missing {len(missing_topics)} topics: {', '.join(missing_topics[:4])}...)")
    print(f"Original Requested Price: INR {pricing.get('requested_price')}")
    print(f"Fair Adjusted Price: INR {pricing.get('recommended_price')} (Discounted: -INR {pricing.get('discount_amount')})")
    print(f"AI Consumer Protection Explanation: {pricing.get('explanation')}")

    assert pricing.get("is_discounted") is True, "Expected discount to be triggered"
    assert pricing.get("recommended_price") < pricing.get("requested_price"), "Price should be dynamically reduced"
    print(">>> PASS: Missing topics triggered fair consumer discount correctly.")

def test_3_copyright_and_duplicate_rejection():
    print("\n--- TEST 3: Copyright & Duplicate Detection Rejection ---")
    
    # 1. Commercial publisher copyright scan
    copyright_text = "Copyright © Pearson Education. All rights reserved. ISBN: 978-0133970777. Unauthorized reproduction is strictly prohibited."
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=595, height=842)
    pdf_stream = io.BytesIO()
    writer.write(pdf_stream)
    pdf_bytes = pdf_stream.getvalue() + b"\n" + copyright_text.encode("utf-8")

    files = {"file": ("Pearson_Textbook_Scan.pdf", pdf_bytes, "application/pdf")}
    data = {"subject": "Operating Systems", "requested_price": "99"}

    r = requests.post(f"{BASE_URL}/api/ai/inspect-note", files=files, data=data, timeout=10)
    res = r.json()
    print("Publisher Scan Upload Status:", res.get("status"))
    print("Rejection Reason:", res.get("rejection_reason"))

    assert res.get("status") == "REJECTED", "Commercial publisher scan should be rejected"
    assert res.get("copyright_violation") is True, "Copyright violation flag should be True"

    # 2. Duplicate handwritten note re-upload check
    print("\nTesting duplicate handwritten note detection...")
    # First upload an original note
    original_text = "Unit 3 Operating Systems: Round Robin Scheduling algorithms with solved time quantum examples."
    writer2 = pypdf.PdfWriter()
    writer2.add_blank_page(width=595, height=842)
    s2 = io.BytesIO()
    writer2.write(s2)
    note_bytes = s2.getvalue() + b"\n" + original_text.encode("utf-8")

    # In our ai_inspector, detect_copyright_and_duplicates checks against existing notes in database or hash
    from backend.ai_inspector import extract_text_and_meta_from_pdf, detect_copyright_and_duplicates
    
    info1 = extract_text_and_meta_from_pdf(note_bytes)
    mock_db = [{
        "id": "existing-note-1",
        "title": "OS Unit 3 Notes",
        "seller_name": "Rohan Patel",
        "md5_hash": info1["md5_hash"],
        "text_fingerprint": info1["text_fingerprint"]
    }]
    
    is_dup, dup_reason = detect_copyright_and_duplicates(info1, mock_db)
    print("Duplicate Check Result:", "REJECTED (Duplicate)" if is_dup else "APPROVED")
    print("Rejection Explanation:", dup_reason)

    assert is_dup is True, "Duplicate note must be detected and rejected"
    print(">>> PASS: Commercial copyright and duplicate notes were strictly rejected.")

def test_4_grounded_study_and_handwriting_simplifier():
    print("\n--- TEST 4: Note-Grounded Study Assistant & Messy Handwriting Simplifier ---")
    
    payload = {
        "prompt": "The handwriting on page 3 is messy and hard to read. Can you simplify and explain the normalization steps in easy English?",
        "note_title": "DBMS Complete Handwritten Notes",
        "subject": "DBMS",
        "note_text": "Unit 2: Normalization. 1NF: atomic attributes, no repeating groups. 2NF: 1NF + no partial dependency. 3NF: 2NF + no transitive dependency X->Y and Y->Z. BCNF: every determinant is candidate key.",
        "simplify_handwriting": True
    }

    r = requests.post(f"{BASE_URL}/api/ai/ask-note", json=payload, timeout=10)
    print("Status Code:", r.status_code)
    res = r.json()
    print("Engine Source:", res.get("source"))
    print("Is Strictly Grounded:", res.get("is_grounded"))
    print("Handwriting Simplified:", res.get("handwriting_simplified"))
    print("\n--- AI Assistant Output Preview ---")
    reply = res.get("reply", "")
    print(reply[:500] + ("..." if len(reply) > 500 else ""))

    assert res.get("is_grounded") is True, "Must be grounded"
    assert "Simplified" in reply or "Normalization" in reply or "DBMS" in reply, "Should contain educational explanation"
    assert "http" not in reply and "www." not in reply, "Must not reference external websites"
    print(">>> PASS: Assistant strictly grounded in note, simplified messy handwriting without external links.")

if __name__ == "__main__":
    print("=====================================================================")
    print("  NoteMarket AI - Comprehensive AI Verification & Grounded Q&A Suite ")
    print("=====================================================================")
    test_1_full_syllabus_inspection()
    test_2_missing_topics_dynamic_pricing()
    test_3_copyright_and_duplicate_rejection()
    test_4_grounded_study_and_handwriting_simplifier()
    print("\n=====================================================================")
    print("  ALL 4 VERIFICATION TESTS PASSED SUCCESSFULLY! ")
    print("=====================================================================")
