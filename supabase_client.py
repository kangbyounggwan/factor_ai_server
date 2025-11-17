"""
Supabase Client for AI Server

Provides database connection and helper functions for AI model storage.
"""
import os
from supabase import create_client, Client
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger("uvicorn.error")

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env file")

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

logger.info(f"[Supabase] Client initialized: {SUPABASE_URL}")


def get_supabase_client() -> Client:
    """
    Get Supabase client instance
    """
    return supabase


def test_connection():
    """
    Test Supabase connection by querying tables
    """
    try:
        # Try to query ai_generated_models table
        response = supabase.table("ai_generated_models").select("id").limit(1).execute()
        logger.info(f"[Supabase] Connection test successful, found {len(response.data)} records")
        return True
    except Exception as e:
        logger.error(f"[Supabase] Connection test failed: {e}")
        return False


if __name__ == "__main__":
    # Test connection when run directly
    print(f"Supabase URL: {SUPABASE_URL}")
    print("Testing connection...")

    if test_connection():
        print("✅ Connection successful!")
    else:
        print("❌ Connection failed!")
