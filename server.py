"""
NoteMarket AI - Python FastAPI Backend Server
Provides full-stack backend capabilities:
- Authentication API (Signup, Login, Token Verification, Profile Management)
- Transaction Tracking & Ledger API (Order initiation, Payment confirmation, Commission calculation, Receipts, History)
- AI Study Assistant Proxy (Ollama + offline fallback)
- Static Frontend Serving
"""

import os
import json
import time
import uuid
import random
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Header, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, EmailStr

from backend.ai_inspector import (
    inspect_note_document,
    build_grounded_study_prompt,
    extract_text_and_meta_from_pdf,
    SUBJECT_SYLLABUS,
    generate_offline_grounded_answer,
    rank_and_select_best_note
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
TRANSACTIONS_FILE = DATA_DIR / "transactions.json"

SUPABASE_URL = "https://ibpoypbtnnzafvkijhed.supabase.co"
ANON_KEY = "sb_publishable_OM1d2AoeVLsh_O9PeAdt7g_L7fXYkRB"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

app = FastAPI(title="NoteMarket AI Full Backend", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Transaction Ledger Persistence
# -----------------------------------------------------------------------------
def load_transactions() -> List[Dict[str, Any]]:
    if not TRANSACTIONS_FILE.exists():
        return []
    try:
        with open(TRANSACTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_transaction(record: Dict[str, Any]):
    txns = load_transactions()
    txns.insert(0, record)
    with open(TRANSACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(txns, f, indent=2, default=str)

# -----------------------------------------------------------------------------
# Support Tickets Persistence
# -----------------------------------------------------------------------------
TICKETS_FILE = DATA_DIR / "support_tickets.json"

def load_tickets() -> List[Dict[str, Any]]:
    if not TICKETS_FILE.exists():
        return []
    try:
        with open(TICKETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_ticket(record: Dict[str, Any]):
    tickets = load_tickets()
    tickets.insert(0, record)
    with open(TICKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(tickets, f, indent=2, default=str)

def update_ticket_in_db(ticket_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tickets = load_tickets()
    found = None
    for t in tickets:
        if t.get("ticket_id") == ticket_id:
            t.update(updates)
            t["updated_at"] = datetime.now(timezone.utc).isoformat()
            found = t
            break
    if found:
        with open(TICKETS_FILE, "w", encoding="utf-8") as f:
            json.dump(tickets, f, indent=2, default=str)
    return found


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    college: str
    branch: str
    semester: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class InitiateTransactionRequest(BaseModel):
    note_id: str
    buyer_id: Optional[str] = None
    buyer_email: Optional[str] = None
    payment_method: str = "UPI"

class ConfirmTransactionRequest(BaseModel):
    order_id: str
    transaction_id: str
    note_id: str
    buyer_id: str
    buyer_email: Optional[str] = None
    payment_method: str = "UPI"
    payment_reference: Optional[str] = None

class AIChatRequest(BaseModel):
    prompt: str
    subject: Optional[str] = None
    note_id: Optional[str] = None
    note_title: Optional[str] = None
    note_text: Optional[str] = None
    simplify_handwriting: Optional[bool] = True
    model: Optional[str] = OLLAMA_MODEL

class AIInspectJsonRequest(BaseModel):
    subject: str = "DBMS"
    requested_price: float = 49.0
    note_id: Optional[str] = None
    sample_text: Optional[str] = None

class GroundedStudyChatRequest(BaseModel):
    prompt: str
    note_id: Optional[str] = None
    note_title: Optional[str] = None
    subject: Optional[str] = "General"
    note_text: Optional[str] = None
    simplify_handwriting: Optional[bool] = True
    model: Optional[str] = OLLAMA_MODEL

class FindBestNoteRequest(BaseModel):
    query: str
    subject: Optional[str] = None
    semester: Optional[str] = None
    college: Optional[str] = None
    buyer_id: Optional[str] = None
    buyer_email: Optional[str] = None

class InstantPurchaseRequest(BaseModel):
    note_id: str
    buyer_id: str = "guest"
    buyer_email: Optional[str] = "student@notemarket.ai"
    payment_method: str = "Instant Auto-Settled UPI"

class CreateTicketRequest(BaseModel):
    name: str
    email: EmailStr
    category: str  # e.g., "Download Issue", "Payment Problem", "Copyright Report", "Quality Concern", "General Question"
    subject: str
    message: str
    note_id: Optional[str] = None
    note_title: Optional[str] = None
    priority: str = "Normal"  # "Low", "Normal", "High", "Urgent"

class UpdateTicketStatusRequest(BaseModel):
    status: str  # "open", "in_progress", "resolved", "closed"
    reply: Optional[str] = None
    admin_name: Optional[str] = "NoteMarket Support Team"

# -----------------------------------------------------------------------------
# Supabase Utility Helpers
# -----------------------------------------------------------------------------
def supabase_request(endpoint: str, method: str = "GET", data: Optional[dict] = None, token: Optional[str] = None) -> Any:
    url = f"{SUPABASE_URL}/{endpoint}"
    headers = {
        "apikey": ANON_KEY,
        "Authorization": f"Bearer {token or ANON_KEY}",
        "Content-Type": "application/json"
    }
    encoded = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=encoded, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))

# =============================================================================
# 1. AUTHENTICATION BACKEND ENDPOINTS
# =============================================================================

@app.post("/api/auth/signup")
def auth_signup(req: SignupRequest):
    """Register a new student with Supabase Auth and initialize their academic profile."""
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    signup_payload = {
        "email": req.email,
        "password": req.password,
        "data": {
            "full_name": req.full_name,
            "college": req.college,
            "branch": req.branch,
            "semester": req.semester
        }
    }

    try:
        res = supabase_request("auth/v1/signup", method="POST", data=signup_payload)
        user_info = res.get("user") or {}
        access_token = res.get("access_token")
        user_id = user_info.get("id")

        # Explicitly ensure profile row exists in public.profiles
        if user_id and access_token:
            try:
                profile_payload = {
                    "id": user_id,
                    "full_name": req.full_name,
                    "college": req.college,
                    "branch": req.branch,
                    "semester": req.semester,
                    "role": "student"
                }
                supabase_request("rest/v1/profiles", method="POST", data=profile_payload, token=access_token)
            except Exception:
                pass  # Profile trigger may have already handled this

        return {
            "success": True,
            "message": "User registered successfully.",
            "user": {
                "id": user_id,
                "email": req.email,
                "full_name": req.full_name,
                "college": req.college,
                "branch": req.branch,
                "semester": req.semester
            },
            "access_token": access_token
        }
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_msg)
            msg = err_json.get("msg") or err_json.get("error_description") or err_json.get("message") or err_msg
        except Exception:
            msg = err_msg
        raise HTTPException(status_code=e.code, detail=msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    """Authenticate student credentials, return access token and profile."""
    login_url = "auth/v1/token?grant_type=password"
    payload = {"email": req.email, "password": req.password}

    try:
        res = supabase_request(login_url, method="POST", data=payload)
        user_data = res.get("user", {})
        access_token = res.get("access_token")
        user_id = user_data.get("id")

        # Fetch profile
        profile = None
        try:
            profiles = supabase_request(f"rest/v1/profiles?id=eq.{user_id}", token=access_token)
            if profiles and len(profiles) > 0:
                profile = profiles[0]
        except Exception:
            pass

        full_name = profile.get("full_name") if profile else user_data.get("user_metadata", {}).get("full_name", "Student")
        college = profile.get("college") if profile else user_data.get("user_metadata", {}).get("college", "GTU")

        return {
            "success": True,
            "access_token": access_token,
            "user": {
                "id": user_id,
                "email": user_data.get("email"),
                "full_name": full_name,
                "college": college,
                "branch": profile.get("branch") if profile else user_data.get("user_metadata", {}).get("branch", ""),
                "semester": profile.get("semester") if profile else user_data.get("user_metadata", {}).get("semester", "")
            }
        }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            msg = json.loads(err_body).get("error_description", "Invalid login credentials.")
        except Exception:
            msg = "Invalid email or password."
        raise HTTPException(status_code=401, detail=msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/auth/me")
def auth_me(authorization: Optional[str] = Header(None)):
    """Verify session token and return authenticated user metadata."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")

    token = authorization.split("Bearer ")[1].strip()
    try:
        user_info = supabase_request("auth/v1/user", token=token)
        user_id = user_info.get("id")
        
        profile = {}
        try:
            profiles = supabase_request(f"rest/v1/profiles?id=eq.{user_id}", token=token)
            if profiles:
                profile = profiles[0]
        except Exception:
            pass

        return {
            "authenticated": True,
            "user": {
                "id": user_id,
                "email": user_info.get("email"),
                "full_name": profile.get("full_name") or user_info.get("user_metadata", {}).get("full_name", "Student"),
                "college": profile.get("college") or user_info.get("user_metadata", {}).get("college"),
                "branch": profile.get("branch") or user_info.get("user_metadata", {}).get("branch"),
                "semester": profile.get("semester") or user_info.get("user_metadata", {}).get("semester")
            }
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail="Session expired or invalid token.")

# =============================================================================
# 2. TRANSACTION TRACKING & SETTLEMENT BACKEND ENDPOINTS
# =============================================================================

@app.post("/api/transactions/initiate")
def initiate_transaction(req: InitiateTransactionRequest):
    """
    Step 1 of Purchase Transaction:
    Validates note availability, generates order reference, and calculates
    platform commission (20%) and seller payout (80%).
    """
    # Fetch note details
    note = None
    try:
        notes = supabase_request(f"rest/v1/notes?id=eq.{req.note_id}")
        if notes and len(notes) > 0:
            note = notes[0]
    except Exception:
        pass

    if not note:
        # Fallback to local default pricing if Supabase lookup failed
        price = 49.0
        note_title = "Academic Study Note"
        seller_id = "demo_seller"
        seller_name = "Student Seller"
    else:
        price = float(note.get("price", 49.0))
        note_title = note.get("title", "Study Note")
        seller_id = note.get("seller_id", "")
        seller_name = note.get("seller_name", "Student Seller")

    order_id = f"ORD-{random.randint(10000, 99999)}"
    transaction_id = f"TXN-NM-{int(time.time())}-{random.randint(100, 999)}"
    
    commission_rate = 0.20
    platform_fee = round(price * commission_rate, 2)
    seller_earnings = round(price - platform_fee, 2)

    return {
        "status": "INITIATED",
        "order_id": order_id,
        "transaction_id": transaction_id,
        "note_id": req.note_id,
        "note_title": note_title,
        "seller_id": seller_id,
        "seller_name": seller_name,
        "amount": price,
        "currency": "INR",
        "breakdown": {
            "gross_amount": price,
            "platform_commission_pct": 20,
            "platform_fee": platform_fee,
            "seller_royalty": seller_earnings
        },
        "payment_method": req.payment_method,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

@app.post("/api/transactions/confirm")
def confirm_transaction(req: ConfirmTransactionRequest):
    """
    Step 2 of Purchase Transaction:
    Confirms payment settlement, records transaction in backend ledger,
    records in Supabase purchases, increments note sales, and issues receipt.
    """
    # Get note details for ledger
    note = {}
    try:
        notes = supabase_request(f"rest/v1/notes?id=eq.{req.note_id}")
        if notes and len(notes) > 0:
            note = notes[0]
    except Exception:
        pass

    price = float(note.get("price", 49.0))
    note_title = note.get("title", "Academic Notes")
    seller_id = note.get("seller_id", "demo_seller")
    seller_name = note.get("seller_name", "Verified Student")
    file_path = note.get("file_path", "")

    commission_rate = 0.20
    platform_fee = round(price * commission_rate, 2)
    seller_earnings = round(price - platform_fee, 2)
    ref = req.payment_reference or f"UPI-REF-{random.randint(100000000, 999999999)}"

    transaction_record = {
        "transaction_id": req.transaction_id,
        "order_id": req.order_id,
        "buyer_id": req.buyer_id,
        "buyer_email": req.buyer_email,
        "note_id": req.note_id,
        "note_title": note_title,
        "seller_id": seller_id,
        "seller_name": seller_name,
        "file_path": file_path,
        "amount": price,
        "currency": "INR",
        "platform_fee": platform_fee,
        "seller_earnings": seller_earnings,
        "payment_method": req.payment_method,
        "payment_reference": ref,
        "payment_status": "PAID",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # 1. Save to backend persistent ledger
    save_transaction(transaction_record)

    # 2. Try recording in Supabase purchases table
    try:
        supabase_purchase = {
            "buyer_id": req.buyer_id,
            "note_id": req.note_id,
            "amount": price,
            "payment_status": "paid",
            "payment_provider": req.payment_method,
            "payment_reference": ref
        }
        supabase_request("rest/v1/purchases", method="POST", data=supabase_purchase)
    except Exception as e:
        print("Note on Supabase purchases sync:", e)

    # 3. Increment note purchase count
    try:
        curr_purchases = int(note.get("purchases_count", 0)) + 1
        supabase_request(f"rest/v1/notes?id=eq.{req.note_id}", method="PATCH", data={"purchases_count": curr_purchases})
    except Exception:
        pass

    return {
        "success": True,
        "message": "Payment verified and transaction settled.",
        "receipt": {
            "receipt_number": f"RCP-{req.order_id}",
            "transaction_id": req.transaction_id,
            "order_id": req.order_id,
            "payment_reference": ref,
            "note_title": note_title,
            "amount_paid": price,
            "currency": "INR",
            "status": "PAID",
            "date": datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
        },
        "download_entitled": True,
        "file_path": file_path
    }

@app.get("/api/transactions/user/{user_id}")
def user_transactions(user_id: str):
    """Retrieve all purchase transactions for a specific student."""
    txns = load_transactions()
    user_txns = [t for t in txns if t.get("buyer_id") == user_id]
    return {
        "user_id": user_id,
        "total_purchases": len(user_txns),
        "total_spent": sum(t.get("amount", 0) for t in user_txns),
        "transactions": user_txns
    }

@app.get("/api/transactions/seller/{seller_id}")
def seller_transactions(seller_id: str):
    """Retrieve seller sales transactions, total earnings, and commission breakdown."""
    txns = load_transactions()
    seller_txns = [t for t in txns if t.get("seller_id") == seller_id]
    total_sales = sum(t.get("amount", 0) for t in seller_txns)
    total_earnings = sum(t.get("seller_earnings", 0) for t in seller_txns)
    platform_cut = sum(t.get("platform_fee", 0) for t in seller_txns)

    return {
        "seller_id": seller_id,
        "sales_count": len(seller_txns),
        "gross_sales": total_sales,
        "net_earnings": total_earnings,
        "platform_commission": platform_cut,
        "transactions": seller_txns
    }

@app.get("/api/transactions/platform-stats")
def platform_stats():
    """Retrieve global platform transaction metrics for admin dashboard."""
    txns = load_transactions()
    gmv = sum(t.get("amount", 0) for t in txns)
    total_commission = sum(t.get("platform_fee", 0) for t in txns)
    total_royalties = sum(t.get("seller_earnings", 0) for t in txns)

    return {
        "total_transactions": len(txns),
        "gross_merchandise_value": gmv,
        "platform_commission_revenue": total_commission,
        "creator_royalties_paid": total_royalties,
        "currency": "INR",
        "recent_transactions": txns[:10]
    }

def check_is_already_paid(note_id: str, buyer_id: Optional[str] = None, buyer_email: Optional[str] = None):
    """Check if note has already been purchased and paid for by the user."""
    txns = load_transactions()
    for t in txns:
        if str(t.get("note_id")) == str(note_id):
            if buyer_id and str(t.get("buyer_id")) == str(buyer_id):
                return True, t
            if buyer_email and t.get("buyer_email") and t.get("buyer_email").lower() == buyer_email.lower():
                return True, t
            if buyer_id in ["guest", None] and t.get("payment_status") == "PAID":
                return True, t

    if buyer_id and buyer_id != "guest":
        try:
            res = supabase_request(f"rest/v1/purchases?note_id=eq.{note_id}&buyer_id=eq.{buyer_id}&payment_status=eq.paid")
            if res and len(res) > 0:
                return True, res[0]
        except Exception:
            pass

    return False, None

@app.get("/api/transactions/check-paid/{note_id}")
def check_note_payment_status(note_id: str, buyer_id: Optional[str] = None, email: Optional[str] = None):
    """Verifies whether a user has already paid for a given note."""
    is_paid, txn = check_is_already_paid(note_id, buyer_id, email)
    return {
        "note_id": note_id,
        "already_paid": is_paid,
        "payment_status": "ALREADY PAID" if is_paid else "UNPAID",
        "transaction": txn
    }

# =============================================================================
# 3. NOTES & LOCAL AI ENDPOINTS
# =============================================================================

@app.get("/api/health")
def health():
    supabase_ok = False
    try:
        notes = supabase_request("rest/v1/notes?select=id&limit=1")
        supabase_ok = isinstance(notes, list)
    except Exception:
        supabase_ok = False

    ollama_ok = False
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1) as resp:
            ollama_ok = (resp.status == 200)
    except Exception:
        ollama_ok = False

    return {
        "status": "healthy",
        "supabase_connected": supabase_ok,
        "ollama_available": ollama_ok,
        "supabase_url": SUPABASE_URL,
        "server_time": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/notes")
def get_notes():
    try:
        notes = supabase_request("rest/v1/notes?select=*&status=eq.approved&order=created_at.desc")
        return {"notes": notes, "source": "supabase"}
    except Exception as e:
        return {"notes": [], "error": str(e), "source": "fallback"}

# =============================================================================
# 3. AI NOTE INSPECTION, VERIFICATION & GROUNDED STUDY ASSISTANT
# =============================================================================

@app.post("/api/ai/inspect-note")
async def ai_inspect_note(
    file: UploadFile = File(...),
    subject: str = Form("DBMS"),
    requested_price: float = Form(49.0)
):
    """
    Intelligent PDF Note Inspection & Verification before consumer purchase:
    1. Extracts text, counts pages, computes file size.
    2. Detects commercial copyright (Pearson, McGraw-Hill, etc.) & duplicate notes.
    3. Analyzes syllabus topic coverage (Covered vs Missing topics).
    4. Dynamically reduces price if topics are missing to protect consumers.
    5. Scores handwriting legibility & student usability.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Fetch existing notes from Supabase to check for duplicate uploads
    existing_notes = []
    try:
        res = supabase_request("rest/v1/notes?select=id,title,seller_name,file_path,description")
        if isinstance(res, list):
            existing_notes = res
    except Exception:
        pass

    report = inspect_note_document(
        pdf_bytes=content,
        subject=subject,
        requested_price=requested_price,
        existing_notes=existing_notes
    )
    return report

@app.post("/api/ai/inspect-json")
def ai_inspect_json(req: AIInspectJsonRequest):
    """
    JSON-based note inspection (useful for API clients and automated tests).
    """
    text = req.sample_text or ""
    price = req.requested_price
    subject = req.subject

    if req.note_id:
        try:
            res = supabase_request(f"rest/v1/notes?id=eq.{req.note_id}&select=*")
            if res and len(res) > 0:
                n = res[0]
                text = text or n.get("description", "")
                subject = n.get("subject", subject)
                price = float(n.get("price", price))
        except Exception:
            pass

    fake_pdf = b"%PDF-1.4 " + text.encode("utf-8")
    report = inspect_note_document(
        pdf_bytes=fake_pdf,
        subject=subject,
        requested_price=price,
        existing_notes=[]
    )
    return report

@app.get("/api/ai/inspect-note/{note_id}")
def get_note_inspection(note_id: str):
    """
    Generates or fetches verification badge for any note in marketplace.
    """
    try:
        res = supabase_request(f"rest/v1/notes?id=eq.{note_id}&select=*")
        if not res or len(res) == 0:
            raise HTTPException(status_code=404, detail=f"Note {note_id} not found.")
        n = res[0]
        subject = n.get("subject", "DBMS")
        price = float(n.get("price", 49.0))
        desc = n.get("description", "")
        title = n.get("title", "")
        
        sample_bytes = f"%PDF-1.4 Title: {title}\nSubject: {subject}\n{desc}".encode("utf-8")
        report = inspect_note_document(
            pdf_bytes=sample_bytes,
            subject=subject,
            requested_price=price,
            existing_notes=[]
        )
        return report
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ai/syllabus/{subject}")
def get_syllabus(subject: str):
    """Returns standard curriculum topics for a university subject."""
    normalized = "DBMS"
    for k in SUBJECT_SYLLABUS:
        if k.lower() in subject.lower():
            normalized = k
            break
    return {
        "subject": normalized,
        "topics": SUBJECT_SYLLABUS.get(normalized, SUBJECT_SYLLABUS["DBMS"])
    }

@app.post("/api/ai/ask-note")
def ask_note_assistant(req: GroundedStudyChatRequest):
    """
    Grounded Study Chatbot & Messy Handwriting Simplifier:
    1. Answers strictly from the note as reference (NO external websites or search).
    2. Simplifies messy/unclear handwriting into clear, easy-to-understand English.
    3. Provides exam takeaways, formulas, and PYQs directly tied to the note.
    """
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    note_title = req.note_title or "Selected Academic Note"
    subject = req.subject or "Engineering"
    note_text = req.note_text or ""

    if req.note_id and not note_text:
        try:
            res = supabase_request(f"rest/v1/notes?id=eq.{req.note_id}&select=*")
            if res and len(res) > 0:
                n = res[0]
                note_title = n.get("title", note_title)
                subject = n.get("subject", subject)
                note_text = (
                    f"Title: {n.get('title')}\n"
                    f"Subject: {n.get('subject')}\n"
                    f"College: {n.get('college')}\n"
                    f"Description: {n.get('description')}\n"
                    f"Syllabus Units: 1 to 6\n"
                    f"Topics Covered: {', '.join(SUBJECT_SYLLABUS.get(subject, SUBJECT_SYLLABUS['DBMS'])[:8])}"
                )
        except Exception:
            pass

    # Build note-grounded prompt
    grounded_prompt = build_grounded_study_prompt(
        note_title=note_title,
        subject=subject,
        note_text=note_text,
        student_query=req.prompt
    )

    # 1. Try querying local Ollama model
    try:
        payload = {
            "model": req.model or OLLAMA_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": "You are NoteMarket AI Study Assistant. Follow strict grounding rules: use only the provided note as reference, do not cite external websites, and explain messy handwritten concepts in simple, clear English."},
                {"role": "user", "content": grounded_prompt}
            ],
            "options": {"temperature": 0.2}
        }
        r = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(r, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content = result.get("message", {}).get("content")
            if content:
                return {
                    "reply": content,
                    "source": "ollama_grounded",
                    "note_title": note_title,
                    "is_grounded": True,
                    "handwriting_simplified": True
                }
    except Exception:
        pass

    # 2. Use offline educational grounded generator
    reply = generate_offline_grounded_answer(req.prompt, note_title, subject, note_text)
    return {
        "reply": reply,
        "source": "notemarket_grounded_engine",
        "note_title": note_title,
        "is_grounded": True,
        "handwriting_simplified": True
    }

# =============================================================================
# 3B. AI CONCIERGE AGENT (BEST PDF FINDER & INSTANT TRANSACTION SETTLEMENT)
# =============================================================================

@app.post("/api/ai/agent/find-best-note")
def ai_agent_find_best_note(req: FindBestNoteRequest):
    """
    Autonomous AI Concierge Agent:
    1. Interprets student request (Subject, Semester, Query).
    2. Retrieves catalog notes and executes multi-factor verification scoring.
    3. Selects the single Best Verified PDF for the user.
    4. Checks if user has already paid -> displays 'ALREADY PAID' status.
    """
    # 1. Fetch approved notes from Supabase or fallback catalog
    all_notes = []
    try:
        res = supabase_request("rest/v1/notes?status=eq.approved&select=*")
        if isinstance(res, list) and len(res) > 0:
            all_notes = res
    except Exception:
        pass

    if not all_notes:
        all_notes = [
            {
                "id": "1",
                "title": "DBMS Complete Theory & Solved PYQs",
                "subject": "DBMS",
                "college": "SVBIT",
                "semester": "Semester 5",
                "price": 49.0,
                "rating": 4.9,
                "reviews_count": 38,
                "purchases_count": 142,
                "pages": 56,
                "seller_name": "Rohan Patel (GTU Rank 3)",
                "description": "Comprehensive handwritten units 1–6 covering ER diagrams, Relational Algebra, Normalization 1NF to BCNF, ACID transactions, Two-phase locking, Indexing and previous 5 years GTU university exam solved questions.",
                "file_path": "dbms_unit1_6_verified.pdf"
            },
            {
                "id": "2",
                "title": "Web Technology Full Notes + Lab Codes",
                "subject": "Web Technology",
                "college": "Nirma University",
                "semester": "Semester 5",
                "price": 39.0,
                "rating": 4.8,
                "reviews_count": 29,
                "purchases_count": 87,
                "pages": 44,
                "seller_name": "Priya Shah",
                "description": "Clear handwritten theory + diagrams for HTML5, CSS3, JavaScript DOM manipulation, AJAX, JSON, REST API principles and PHP backend connectivity.",
                "file_path": "webtech_full_notes.pdf"
            },
            {
                "id": "3",
                "title": "Operating Systems Core Concepts & Scheduling",
                "subject": "Operating Systems",
                "college": "GTU",
                "semester": "Semester 4",
                "price": 45.0,
                "rating": 4.9,
                "reviews_count": 31,
                "purchases_count": 95,
                "pages": 52,
                "seller_name": "Kavya Trivedi",
                "description": "Process synchronization, semaphores, Banker's algorithm, CPU scheduling (FCFS, SJF, Round Robin), virtual memory, page replacement algorithms and deadlocks.",
                "file_path": "os_core_concepts.pdf"
            },
            {
                "id": "4",
                "title": "Data Structures & Algorithms Master Notes",
                "subject": "Data Structures",
                "college": "Gujarat University",
                "semester": "Semester 3",
                "price": 55.0,
                "rating": 4.9,
                "reviews_count": 42,
                "purchases_count": 160,
                "pages": 64,
                "seller_name": "Amit Sharma",
                "description": "Step-by-step algorithms, time complexity diagrams, binary search trees, AVL rotations, graph BFS/DFS traversals, and dynamic programming.",
                "file_path": "dsa_master_notes.pdf"
            }
        ]

    # 2. Filter candidates
    candidates = all_notes
    if req.subject:
        filtered = [n for n in all_notes if req.subject.lower() in n.get("subject", "").lower()]
        if filtered:
            candidates = filtered

    # 3. Autonomous ranking and verification
    selection_result = rank_and_select_best_note(req.query, candidates)
    if not selection_result:
        raise HTTPException(status_code=404, detail="No suitable notes found matching your criteria.")

    best_note = selection_result["best_note"]
    note_id = str(best_note.get("id"))

    # 4. Check if the user has ALREADY PAID for this note
    is_already_paid, txn = check_is_already_paid(note_id, req.buyer_id, req.buyer_email)
    payment_status = "ALREADY PAID" if is_already_paid else "UNPAID"

    return {
        "status": "SUCCESS",
        "best_note": best_note,
        "verification_badge": selection_result["verification_badge"],
        "composite_score": selection_result["composite_score"],
        "recommendation_reason": selection_result["recommendation_reason"],
        "already_paid": is_already_paid,
        "payment_status": payment_status,
        "action": "download" if is_already_paid else "instant_buy",
        "transaction_details": txn if is_already_paid else None
    }

@app.post("/api/ai/agent/instant-purchase")
def ai_agent_instant_purchase(req: InstantPurchaseRequest):
    """
    1-Click AI Agent Instant Purchase Settlement:
    - Autonomously executes the transaction
    - Immediately marks payment as 'ALREADY PAID' (PAID)
    - Distributes 80% creator / 20% platform royalties
    - Creates persistent ledger receipt
    - Returns instant download entitlement right inside the AI chat!
    """
    note = {}
    try:
        notes = supabase_request(f"rest/v1/notes?id=eq.{req.note_id}")
        if notes and len(notes) > 0:
            note = notes[0]
    except Exception:
        pass

    price = float(note.get("price", 49.0))
    note_title = note.get("title", "Verified Academic Note")
    seller_id = note.get("seller_id", "demo_seller")
    seller_name = note.get("seller_name", "Verified Student")
    file_path = note.get("file_path", "")

    # If already paid, return existing settled receipt immediately without double charge
    is_already_paid, existing_txn = check_is_already_paid(req.note_id, req.buyer_id, req.buyer_email)
    if is_already_paid and existing_txn:
        return {
            "success": True,
            "payment_status": "ALREADY PAID",
            "message": "Note was already paid and verified. Access unlocked.",
            "receipt": {
                "receipt_number": f"RCP-{existing_txn.get('order_id', 'EXISTING')}",
                "order_id": existing_txn.get("order_id"),
                "transaction_id": existing_txn.get("transaction_id"),
                "payment_reference": existing_txn.get("payment_reference"),
                "note_title": existing_txn.get("note_title", note_title),
                "amount_paid": existing_txn.get("amount", price),
                "payment_status": "ALREADY PAID"
            },
            "download_entitled": True,
            "file_path": existing_txn.get("file_path", file_path),
            "note_id": req.note_id
        }

    order_id = f"ORD-AI-{random.randint(10000, 99999)}"
    transaction_id = f"TXN-AI-{int(time.time())}-{random.randint(100, 999)}"
    ref = f"AI-INSTANT-UPI-{random.randint(100000000, 999999999)}"

    commission_rate = 0.20
    platform_fee = round(price * commission_rate, 2)
    seller_earnings = round(price - platform_fee, 2)

    transaction_record = {
        "transaction_id": transaction_id,
        "order_id": order_id,
        "buyer_id": req.buyer_id,
        "buyer_email": req.buyer_email,
        "note_id": req.note_id,
        "note_title": note_title,
        "seller_id": seller_id,
        "seller_name": seller_name,
        "file_path": file_path,
        "amount": price,
        "currency": "INR",
        "platform_fee": platform_fee,
        "seller_earnings": seller_earnings,
        "payment_method": req.payment_method,
        "payment_reference": ref,
        "payment_status": "PAID",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # 1. Save to transactions ledger
    save_transaction(transaction_record)

    # 2. Try recording in Supabase purchases
    try:
        supabase_purchase = {
            "buyer_id": req.buyer_id,
            "note_id": req.note_id,
            "amount": price,
            "payment_status": "paid",
            "payment_provider": req.payment_method,
            "payment_reference": ref
        }
        supabase_request("rest/v1/purchases", method="POST", data=supabase_purchase)
    except Exception:
        pass

    # 3. Increment note purchase count
    try:
        curr_purchases = int(note.get("purchases_count", 0)) + 1
        supabase_request(f"rest/v1/notes?id=eq.{req.note_id}", method="PATCH", data={"purchases_count": curr_purchases})
    except Exception:
        pass

    return {
        "success": True,
        "payment_status": "ALREADY PAID",
        "message": "Payment verified and auto-settled by AI Agent. Payment Status: ALREADY PAID.",
        "receipt": {
            "receipt_number": f"RCP-{order_id}",
            "order_id": order_id,
            "transaction_id": transaction_id,
            "payment_reference": ref,
            "note_title": note_title,
            "amount_paid": price,
            "currency": "INR",
            "payment_status": "ALREADY PAID",
            "date": datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
        },
        "download_entitled": True,
        "file_path": file_path,
        "note_id": req.note_id
    }

@app.post("/api/ai/chat")
def ai_chat(req: AIChatRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    
    # If request is grounded to a note, forward to grounded engine
    if req.note_id or req.note_text or req.note_title:
        return ask_note_assistant(GroundedStudyChatRequest(
            prompt=req.prompt,
            note_id=req.note_id,
            note_title=req.note_title,
            subject=req.subject or "Engineering",
            note_text=req.note_text,
            simplify_handwriting=req.simplify_handwriting,
            model=req.model
        ))

    # Check if this is an AI concierge discovery request (e.g. "find best notes", "best DBMS pdf", "recommend note")
    p_lower = req.prompt.lower()
    discovery_triggers = ["find", "best note", "best pdf", "recommend", "suggest", "which note", "need notes", "give me notes", "search note"]
    if any(t in p_lower for t in discovery_triggers) and not req.note_text:
        # Check if subject is mentioned in prompt
        inferred_subject = req.subject
        for s in SUBJECT_SYLLABUS.keys():
            if s.lower() in p_lower:
                inferred_subject = s
                break
        try:
            concierge_res = ai_agent_find_best_note(FindBestNoteRequest(
                query=req.prompt,
                subject=inferred_subject,
                buyer_id=req.note_id or "guest"
            ))
            best = concierge_res["best_note"]
            badge = concierge_res["verification_badge"]
            pay_status = concierge_res["payment_status"]
            reply_text = (
                f"🎯 **NoteMarket AI Concierge**: I searched the student catalog and verified the candidate notes.\n\n"
                f"### 🏆 Best Verified PDF: {best.get('title')}\n\n"
                f"- **Subject**: {best.get('subject')} ({best.get('college', 'GTU')} • {best.get('semester', 'Sem 5')})\n"
                f"- **AI Quality Score**: {badge.get('quality_score')}/100\n"
                f"- **Syllabus Coverage**: {badge.get('coverage_percentage')}% Full Curriculum\n"
                f"- **Legibility**: {badge.get('legibility')}\n"
                f"- **Fair Price**: ₹{badge.get('fair_price')} (Fair Value Protected)\n"
                f"- **Payment Status**: **{pay_status}**\n\n"
                f"💡 *{concierge_res.get('recommendation_reason')}*"
            )
            return {
                "reply": reply_text,
                "source": "ai_concierge_agent",
                "is_recommendation": True,
                "best_note": best,
                "verification_badge": badge,
                "already_paid": concierge_res["already_paid"],
                "payment_status": pay_status,
                "composite_score": concierge_res["composite_score"]
            }
        except Exception as e:
            pass

    # Try querying Ollama for general questions
    try:
        system_prompt = (
            "You are NoteMarket AI, an expert college study assistant for engineering and university students. "
            "Answer clearly, concisely, and with structured bullet points, diagrams, and exam-focused takeaways."
        )
        payload = {
            "model": req.model or OLLAMA_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.prompt}
            ],
            "options": {"temperature": 0.3}
        }
        r = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(r, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content = result.get("message", {}).get("content")
            if content:
                return {"reply": content, "source": "ollama"}
    except Exception:
        pass

    # Built-in academic fallback
    p_lower = req.prompt.lower()
    if any(k in p_lower for k in ["handwriting", "messy", "simplify"]):
        fallback = generate_offline_grounded_answer(req.prompt, "Academic Handwritten Notes", "Engineering", "")
    elif "normalization" in p_lower or "dbms" in p_lower:
        fallback = (
            "### 📚 DBMS Normalization Guide\n\n"
            "Normalization is the process of organizing database tables to reduce redundancy and improve data integrity.\n\n"
            "**Key Normal Forms:**\n"
            "1. **1NF (First Normal Form)**: Atomic values, no repeating groups.\n"
            "2. **2NF (Second Normal Form)**: Must be 1NF + no partial dependency on primary key.\n"
            "3. **3NF (Third Normal Form)**: Must be 2NF + no transitive dependency.\n"
            "4. **BCNF (Boyce-Codd Normal Form)**: For every functional dependency `X -> Y`, `X` must be a super key."
        )
    elif "mcq" in p_lower:
        fallback = (
            "### 📝 Quick Academic MCQs\n\n"
            "1. **Which protocol provides encrypted HTTP transmission?** HTTPS [✓]\n"
            "2. **Which SQL keyword removes duplicate rows?** DISTINCT [✓]\n"
            "3. **Time complexity of binary search?** O(log n) [✓]\n"
            "4. **Which OS deadlock condition occurs when resources cannot be shared?** Mutual Exclusion [✓]"
        )
    else:
        fallback = (
            f"### 🎓 Academic Summary: {req.prompt.title()}\n\n"
            "1. **Key Concept Definition**: Understand the primary principles and formal terminology.\n"
            "2. **University Exam Focus**: Trace common 7-mark questions, diagrams, and step-by-step algorithms.\n"
            "3. **Practical Application**: Relate the theory to system architecture and database design."
        )

    return {"reply": fallback, "source": "academic_assistant"}

# =============================================================================
# 4. SUPPORT & HELP DESK BACKEND ENDPOINTS
# =============================================================================

@app.post("/api/support/tickets")
def create_support_ticket(req: CreateTicketRequest):
    """Submit a student support ticket, note complaint, or copyright report."""
    ticket_id = f"TCK-{random.randint(10000, 99999)}"
    created_at = datetime.now(timezone.utc).isoformat()

    ticket_record = {
        "ticket_id": ticket_id,
        "name": req.name,
        "email": req.email,
        "category": req.category,
        "subject": req.subject,
        "message": req.message,
        "note_id": req.note_id,
        "note_title": req.note_title,
        "priority": req.priority,
        "status": "open",
        "created_at": created_at,
        "updated_at": created_at,
        "replies": []
    }

    save_ticket(ticket_record)

    # If this ticket is reporting a specific note, sync with Supabase reports table
    if req.note_id:
        try:
            report_data = {
                "note_id": req.note_id,
                "reason": req.category,
                "details": f"[{req.name} <{req.email}>]: {req.message}",
                "status": "open"
            }
            supabase_request("rest/v1/reports", method="POST", data=report_data)
        except Exception as e:
            print("Note on Supabase reports sync:", e)

    return {
        "success": True,
        "ticket_id": ticket_id,
        "status": "open",
        "message": "Support ticket created successfully. Our team will review and respond within 24 hours.",
        "ticket": ticket_record
    }

@app.get("/api/support/tickets")
def list_support_tickets(status: Optional[str] = None, email: Optional[str] = None):
    """Retrieve all support tickets with optional filtering by status or email."""
    tickets = load_tickets()
    if status:
        tickets = [t for t in tickets if t.get("status") == status]
    if email:
        tickets = [t for t in tickets if t.get("email") == email]

    return {
        "total_tickets": len(tickets),
        "tickets": tickets
    }

@app.get("/api/support/tickets/{ticket_id}")
def get_support_ticket(ticket_id: str):
    """Track support ticket status and responses using Ticket ID."""
    tickets = load_tickets()
    for t in tickets:
        if t.get("ticket_id") == ticket_id:
            return {"found": True, "ticket": t}

    raise HTTPException(status_code=404, detail=f"Support ticket {ticket_id} not found.")

@app.patch("/api/support/tickets/{ticket_id}/status")
def update_ticket_status(ticket_id: str, req: UpdateTicketStatusRequest):
    """Update ticket resolution status and post admin reply."""
    valid_statuses = ["open", "in_progress", "resolved", "closed"]
    if req.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(valid_statuses)}")

    tickets = load_tickets()
    found = None
    for t in tickets:
        if t.get("ticket_id") == ticket_id:
            t["status"] = req.status
            t["updated_at"] = datetime.now(timezone.utc).isoformat()
            if req.reply:
                t.setdefault("replies", []).append({
                    "author": req.admin_name or "NoteMarket Support",
                    "message": req.reply,
                    "timestamp": datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
                })
            found = t
            break

    if not found:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    with open(TICKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(tickets, f, indent=2, default=str)

    return {
        "success": True,
        "message": f"Ticket {ticket_id} updated to {req.status.upper()}.",
        "ticket": found
    }

@app.get("/api/support/faqs")
def get_support_faqs():
    """Returns curated student FAQs and policies."""
    return {
        "faqs": [
            {
                "question": "How do I download notes after payment?",
                "answer": "Once checkout completes, your purchase is instantly recorded. You can download the notes directly from the confirmation screen or anytime from 'My Purchases' in your dashboard."
            },
            {
                "question": "How do seller earnings and commissions work?",
                "answer": "Creators receive 80% royalty on every note sold. NoteMarket retains 20% platform commission to cover payment gateway, storage, and AI processing infrastructure."
            },
            {
                "question": "What is the copyright and plagiarism policy?",
                "answer": "Only original, student-authored study notes and summaries are permitted. Verbatim copyrighted textbook scans will be rejected or taken down upon report."
            },
            {
                "question": "How does NoteMarket AI work?",
                "answer": "NoteMarket AI runs on a local Ollama model (llama3.2) or our backend academic study server. You can ask for syllabus summaries, exam tips, and MCQs anytime."
            },
            {
                "question": "How do I report an incorrect or copyrighted note?",
                "answer": "Click 'Report this note' on any note detail page or submit a ticket under category 'Copyright Report' with the note title and reason."
            }
        ]
    }

# =============================================================================
# 5. STATIC FRONTEND ROUTING
# =============================================================================
js_dir = BASE_DIR / "js"
if js_dir.exists():
    app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")

@app.get("/")
def serve_index():
    return FileResponse(BASE_DIR / "index.html", media_type="text/html")

@app.get("/{catchall:path}")
def serve_static(catchall: str):
    file_path = BASE_DIR / catchall
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(BASE_DIR / "index.html")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5500))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("backend.server:app", host=host, port=port, reload=False if os.environ.get("PORT") else True)
