# NoteMarket AI — Backend Documentation

## 1. Quick Start
To start the full backend server and run NoteMarket AI:

```bash
python start_server.py
```

Then open your browser at:
👉 **`http://localhost:5500`**

---

## 2. Architecture Overview
NoteMarket AI operates on a modern hybrid backend architecture:

1. **Supabase Cloud BaaS (Database, Auth & Storage)**:
   - **Database**: PostgreSQL storing `profiles`, `notes`, `purchases`, `reviews`, `wishlists`, and `reports`.
   - **Auth**: Email/Password authentication with automatic profile creation via Postgres triggers (`on_auth_user_created`).
   - **Storage**: Private `notes` bucket for storing uploaded PDF study materials with Row Level Security.
   - **Row Level Security (RLS)**: Protects user profile edits, note uploads, and order history.

2. **Python Backend Server (`backend/server.py`)**:
   - Built with **FastAPI** & **Uvicorn**.
   - Serves the frontend web app on port `5500`.
   - `/api/health`: Health status of Supabase connection and Local AI engine.
   - `/api/notes`: Proxies and delivers approved academic notes.
   - `/api/checkout/create-order`: Generates encrypted order references for UPI/Card checkout.
   - `/api/ai/chat`: AI Study Assistant endpoint that proxies queries to local **Ollama** (`llama3.2`) with built-in curriculum fallback notes when offline.

3. **Database Seeding (`scripts/seed_database.py`)**:
   - Automatically populates verified university notes (DBMS, Web Tech, OS, Data Structures, Computer Networks, Java) into your live Supabase database.
   - Run anytime via:
     ```bash
     python scripts/seed_database.py
     ```

---

## 3. Database SQL Setup

### Step A: Initial Schema
Run `supabase/schema.sql` in your Supabase Dashboard → SQL Editor if setting up a fresh project.

### Step B: Advanced Policies & Helper RPCs
Run `supabase/update_policies.sql` in Supabase SQL Editor. This enables:
- `purchases_insert_own` and `purchases_update_own` RLS policies.
- Stored procedure `complete_note_purchase` for atomic purchases and purchase counters.
- Stored procedure `moderate_note` for Admin approval and rejection.
- Secure storage read access for purchased notes.

---

## 4. Key Workflows Wired in Frontend

- **Live Dynamic Catalog**: Notes are fetched in real-time from Supabase where `status = 'approved'`.
- **Student Auth**: Full login, signup, session restoration, and reactive navbar state (Profile Avatar / Logout).
- **Sell Notes**: PDF upload directly into Supabase Storage + metadata insertion into `notes` with `status: 'pending'`.
- **Seller Dashboard**: Real-time tracking of uploaded notes, approval statuses, total sales, and 80% creator earnings.
- **Admin Moderation Dashboard**: Real-time view of pending submissions with live "Approve" and "Reject" buttons.
- **Checkout & Secure Downloads**: Generates verified order records and unlocks signed PDF downloads or structured study packs.
- **Wishlist**: Real-time heart toggle syncing to Supabase `wishlists`.
- **Local AI Study Assistant**: Floating widget connected to Ollama and backend study proxy.
