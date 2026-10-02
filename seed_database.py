import json
import urllib.request
import urllib.error
import sys

SUPABASE_URL = "https://ibpoypbtnnzafvkijhed.supabase.co"
ANON_KEY = "sb_publishable_OM1d2AoeVLsh_O9PeAdt7g_L7fXYkRB"

SAMPLE_NOTES = [
    {
        "title": "DBMS Complete Theory & Solved PYQs",
        "subject": "DBMS",
        "subject_code": "3150703",
        "college": "SVBIT",
        "semester": "Semester 5",
        "price": 49,
        "rating": 4.9,
        "reviews_count": 142,
        "purchases_count": 234,
        "pages": 78,
        "seller_name": "Kavya Trivedi",
        "tag": "Best Seller",
        "description": "Complete handwritten notes covering relational model, ER diagrams, normalization, SQL and university PYQs.",
        "file_name": "dbms_complete_theory.pdf"
    },
    {
        "title": "Web Technology Unit 1–5 Notes",
        "subject": "Web Technology",
        "subject_code": "3150710",
        "college": "GTU",
        "semester": "Semester 5",
        "price": 39,
        "rating": 4.8,
        "reviews_count": 96,
        "purchases_count": 181,
        "pages": 64,
        "seller_name": "Aarav Patel",
        "tag": "Verified",
        "description": "Exam-oriented notes covering HTML, CSS, JavaScript, HTTP and modern web concepts.",
        "file_name": "web_tech_notes.pdf"
    },
    {
        "title": "Data Structures Complete Revision Pack",
        "subject": "Data Structures",
        "subject_code": "3150702",
        "college": "Nirma University",
        "semester": "Semester 3",
        "price": 59,
        "rating": 4.7,
        "reviews_count": 74,
        "purchases_count": 128,
        "pages": 91,
        "seller_name": "Riya Shah",
        "tag": "Popular",
        "description": "Easy-to-revise notes with trees, graphs, sorting, searching and important university questions.",
        "file_name": "data_structures_revision.pdf"
    },
    {
        "title": "Operating Systems Exam Notes",
        "subject": "Operating Systems",
        "subject_code": "3150704",
        "college": "Gujarat University",
        "semester": "Semester 5",
        "price": 29,
        "rating": 4.6,
        "reviews_count": 51,
        "purchases_count": 97,
        "pages": 52,
        "seller_name": "Dev Mehta",
        "tag": "Verified",
        "description": "Concise OS notes for processes, scheduling, deadlocks, memory management and file systems.",
        "file_name": "os_exam_notes.pdf"
    },
    {
        "title": "Computer Networks Quick Revision",
        "subject": "Computer Networks",
        "subject_code": "3150711",
        "college": "GTU",
        "semester": "Semester 5",
        "price": 45,
        "rating": 4.8,
        "reviews_count": 63,
        "purchases_count": 143,
        "pages": 70,
        "seller_name": "Meera Joshi",
        "tag": "Popular",
        "description": "Layer-wise CN revision notes, protocols, diagrams, numericals and important exam questions.",
        "file_name": "cn_quick_revision.pdf"
    },
    {
        "title": "Java Programming Important Questions",
        "subject": "Java",
        "subject_code": "3150707",
        "college": "SVBIT",
        "semester": "Semester 4",
        "price": 25,
        "rating": 4.5,
        "reviews_count": 39,
        "purchases_count": 76,
        "pages": 45,
        "seller_name": "Harsh Patel",
        "tag": "Verified",
        "description": "Important Java concepts, OOP, exceptions, collections, threads and exam-focused answers.",
        "file_name": "java_important_questions.pdf"
    }
]

def make_request(url, method="GET", headers=None, data=None):
    if headers is None:
        headers = {}
    headers.setdefault("apikey", ANON_KEY)
    
    encoded_data = None
    if data is not None:
        encoded_data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def authenticate():
    email = "demo_seller@notemarket.ai"
    password = "password123"
    
    login_url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    try:
        data = make_request(login_url, method="POST", data={"email": email, "password": password})
        print(f"Logged in as demo seller: {email}")
        return data["access_token"], data["user"]["id"]
    except urllib.error.HTTPError as e:
        print(f"Login failed ({e.code}), attempting signup...")
        signup_url = f"{SUPABASE_URL}/auth/v1/signup"
        signup_data = {
            "email": email,
            "password": password,
            "data": {
                "full_name": "Kavya Trivedi",
                "college": "SVBIT",
                "branch": "Computer Engineering",
                "semester": "Semester 5"
            }
        }
        data = make_request(signup_url, method="POST", data=signup_data)
        print(f"Signed up demo seller: {email}")
        return data["access_token"], data["user"]["id"]

def seed_notes(token, user_id):
    check_url = f"{SUPABASE_URL}/rest/v1/notes?select=id,title"
    existing = make_request(check_url, headers={"Authorization": f"Bearer {token}"})
    print(f"Existing notes count in database: {len(existing)}")
    
    existing_titles = {n["title"] for n in existing}
    
    inserted_count = 0
    for item in SAMPLE_NOTES:
        if item["title"] in existing_titles:
            print(f"Skipping already existing note: {item['title']}")
            continue
            
        payload = {
            "seller_id": user_id,
            "title": item["title"],
            "description": item["description"],
            "subject": item["subject"],
            "subject_code": item["subject_code"],
            "college": item["college"],
            "semester": item["semester"],
            "price": item["price"],
            "rating": item["rating"],
            "reviews_count": item["reviews_count"],
            "purchases_count": item["purchases_count"],
            "pages": item["pages"],
            "seller_name": item["seller_name"],
            "tag": item["tag"],
            "file_path": f"{user_id}/{item['file_name']}",
            "status": "approved"
        }
        
        insert_url = f"{SUPABASE_URL}/rest/v1/notes"
        try:
            res = make_request(insert_url, method="POST", headers={
                "Authorization": f"Bearer {token}",
                "Prefer": "return=representation"
            }, data=payload)
            print(f"Inserted: {item['title']} (ID: {res[0]['id']})")
            inserted_count += 1
        except urllib.error.HTTPError as err:
            print(f"Failed to insert '{item['title']}': HTTP {err.code} - {err.read().decode('utf-8')}")

    print(f"\nDone! Successfully seeded {inserted_count} new notes.")

if __name__ == "__main__":
    try:
        token, user_id = authenticate()
        seed_notes(token, user_id)
    except Exception as e:
        print(f"Error during seeding: {e}", file=sys.stderr)
