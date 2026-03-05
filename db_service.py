"""
db_service.py — Flask-compatible Supabase client.
No Streamlit imports. Reads credentials from .env (or chatbot/.env as fallback).
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Try root .env first, then chatbot/.env
load_dotenv()
if not os.getenv("SUPABASE_URL"):
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "chatbot", ".env"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise EnvironmentError(
        "SUPABASE_URL and SUPABASE_KEY must be set in .env or chatbot/.env"
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
