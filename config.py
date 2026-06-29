import os
from dotenv import load_dotenv

load_dotenv()

# IMAP credentials (can also be set via the web UI; stored in DB)
IMAP_EMAIL = os.environ.get("IMAP_EMAIL", "")
IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD", "")
IMAP_HOST = os.environ.get("IMAP_HOST", "outlook.office365.com")
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
IMAP_FOLDER = os.environ.get("IMAP_FOLDER", "INBOX")

# Anthropic API Key
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Flask
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))

# Polling
POLL_INTERVAL_MINUTES = int(os.environ.get("POLL_INTERVAL_MINUTES", "5"))
MAX_EMAILS_PER_POLL = int(os.environ.get("MAX_EMAILS_PER_POLL", "50"))

# Storage
DATABASE_PATH = os.environ.get("DATABASE_PATH", "email_tracker.db")
