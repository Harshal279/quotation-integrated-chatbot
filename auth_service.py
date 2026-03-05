"""
auth_service.py — Flask-compatible port of chatbot/auth.py.
Uses db_service.supabase instead of the Streamlit-dependent chatbot/db.py.
All function signatures are identical so chatbot logic can be reused directly.
"""

import re
import hashlib
from datetime import datetime

from db_service import supabase


# ─── Password & Key Helpers ──────────────────────────────────────────────────

def hash_pw(pw: str) -> str:
    """SHA-256 hash of a password string."""
    return hashlib.sha256(pw.strip().encode()).hexdigest()


def company_key(company: str) -> str:
    """Normalised key from company name (used as login ID)."""
    return re.sub(r"[^a-z0-9_]", "_", company.strip().lower())


# ─── User CRUD ───────────────────────────────────────────────────────────────

def register_user(name: str, company: str, phone: str, email: str, password: str) -> tuple:
    """Register a new user with role='user'. Returns (success, key_or_error)."""
    key = company_key(company)
    if not key:
        return False, "Company name is invalid."
    try:
        existing = supabase.table("users").select("id").eq("key", key).execute()
        if existing.data:
            return False, "A company with that name is already registered."
    except Exception as e:
        return False, f"Database connection error. ({type(e).__name__})"
    try:
        supabase.table("users").insert({
            "key": key,
            "name": name.strip(),
            "company": company.strip(),
            "phone": phone.strip(),
            "email": email.strip(),
            "pw_hash": hash_pw(password),
            "role": "user",
        }).execute()
        return True, key
    except Exception as e:
        return False, f"Registration failed: {e}"


def login_user(company: str, password: str) -> tuple:
    """Authenticate a user. Returns (success, key_or_error, user_dict)."""
    key = company_key(company)
    try:
        result = supabase.table("users").select("*").eq("key", key).execute()
    except Exception as e:
        return False, f"Database connection error. ({type(e).__name__})", {}
    if not result.data:
        return False, "Company not found. Please register first.", {}
    user = result.data[0]
    if user["pw_hash"] != hash_pw(password):
        return False, "Wrong password.", {}
    return True, key, {
        "key": user["key"],
        "name": user["name"],
        "company": user["company"],
        "phone": user.get("phone", ""),
        "email": user.get("email", ""),
        "role": user.get("role", "user"),
    }


def is_admin(user: dict) -> bool:
    """Check if a user dict has the admin role."""
    return user.get("role") == "admin"


# ─── Chat History ─────────────────────────────────────────────────────────────

def save_history(user_key: str, session_id: str, messages: list, title: str):
    """Save/update a chat session to Supabase (full-replace strategy)."""
    try:
        supabase.table("chats").delete().eq("user_key", user_key).eq("session_id", session_id).execute()
        rows = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg["role"] == "user":
                user_msg = msg["content"]
                assistant_msg = ""
                if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                    assistant_msg = messages[i + 1]["content"]
                    i += 1
                rows.append({
                    "user_key": user_key, "session_id": session_id, "title": title,
                    "user_message": user_msg, "assistant_response": assistant_msg,
                })
            elif msg["role"] == "assistant" and not rows:
                rows.append({
                    "user_key": user_key, "session_id": session_id, "title": title,
                    "user_message": "", "assistant_response": msg["content"],
                })
            i += 1
        if rows:
            supabase.table("chats").insert(rows).execute()
    except Exception:
        pass


def list_histories(user_key: str) -> list:
    """List all saved chat sessions for a user, newest first."""
    try:
        result = (
            supabase.table("chats")
            .select("session_id, title, created_at")
            .eq("user_key", user_key)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
        return []
    sessions = {}
    for row in result.data:
        sid = row["session_id"]
        if sid not in sessions:
            sessions[sid] = {
                "title": row["title"] or "Untitled",
                "saved_at": _iso_to_ts(row["created_at"]),
                "messages": [],
            }
        sessions[sid]["messages"].append(1)
    items = sorted(sessions.items(), key=lambda x: x[1]["saved_at"], reverse=True)
    return [(f"{sid}.json", meta) for sid, meta in items]


def load_history_file(user_key: str, filename: str) -> dict:
    """Load a specific chat session. Returns dict with 'messages' list."""
    session_id = filename.replace(".json", "")
    result = (
        supabase.table("chats")
        .select("user_message, assistant_response, title, created_at")
        .eq("user_key", user_key)
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    )
    messages, title = [], "Untitled"
    for row in result.data:
        title = row.get("title", title)
        if row["user_message"]:
            messages.append({"role": "user", "content": row["user_message"]})
        if row["assistant_response"]:
            messages.append({"role": "assistant", "content": row["assistant_response"]})
    return {"messages": messages, "title": title}


def delete_history_file(user_key: str, filename: str):
    """Delete a saved chat session."""
    session_id = filename.replace(".json", "")
    supabase.table("chats").delete().eq("user_key", user_key).eq("session_id", session_id).execute()


def make_title(messages: list) -> str:
    """Generate a title from the first user message."""
    for m in messages:
        if m["role"] == "user":
            txt = m["content"].strip().replace("\n", " ")
            return txt[:45] + ("…" if len(txt) > 45 else "")
    return "Untitled chat"


# ─── Admin Helpers ────────────────────────────────────────────────────────────

def list_all_users() -> list:
    """Return all registered users (for admin dashboard)."""
    result = (
        supabase.table("users")
        .select("key, name, company, phone, email, role, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def list_all_chats(user_filter: str = None, limit: int = 100) -> list:
    """Return chats across all users (admin only)."""
    query = supabase.table("chats").select(
        "id, user_key, session_id, title, user_message, assistant_response, created_at"
    )
    if user_filter:
        query = query.eq("user_key", user_filter)
    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data


def admin_delete_session(user_key: str, session_id: str):
    """Delete all chat rows for a given session (admin only)."""
    supabase.table("chats").delete().eq("user_key", user_key).eq("session_id", session_id).execute()


# ─── Internal Helpers ─────────────────────────────────────────────────────────

def _iso_to_ts(iso_str: str) -> float:
    """Convert ISO datetime string to Unix timestamp."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0
