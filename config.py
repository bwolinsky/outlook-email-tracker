import os
from dotenv import load_dotenv

load_dotenv()

AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")
AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID", "common")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))
POLL_INTERVAL_MINUTES = int(os.environ.get("POLL_INTERVAL_MINUTES", "5"))
MAX_EMAILS_PER_POLL = int(os.environ.get("MAX_EMAILS_PER_POLL", "50"))
DATABASE_PATH = os.environ.get("DATABASE_PATH", "email_tracker.db")
TOKEN_CACHE_PATH = os.environ.get("TOKEN_CACHE_PATH", ".token_cache.json")

GRAPH_SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/User.Read",
    "offline_access",
]

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
