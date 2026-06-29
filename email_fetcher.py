"""IMAP-based email fetcher for Outlook / Microsoft 365."""
import email as email_lib
import email.message
import imaplib
import re
import ssl
from datetime import datetime, timezone
from email.header import decode_header as _decode_header
from email.utils import parsedate_to_datetime

import config


def _decode_str(value: str | bytes | None, charset: str | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(charset or "utf-8", errors="replace")
    return value


def decode_mime_words(raw: str) -> str:
    """Decode RFC-2047 encoded header words."""
    if not raw:
        return ""
    parts = _decode_header(raw)
    return "".join(_decode_str(part, enc) for part, enc in parts)


def strip_html(html: str) -> str:
    text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    for esc, ch in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'")]:
        text = text.replace(esc, ch)
    return re.sub(r"\s{2,}", " ", text).strip()


def parse_email_message(msg: email.message.Message) -> dict:
    """Convert a parsed email.Message into our standard dict."""
    subject = decode_mime_words(msg.get("Subject", "(no subject)"))
    from_raw = decode_mime_words(msg.get("From", ""))
    # Parse "Name <addr>" or just "addr"
    m = re.match(r"^(.*?)\s*<([^>]+)>$", from_raw)
    if m:
        sender_name, sender_email = m.group(1).strip().strip('"'), m.group(2).strip()
    else:
        sender_name, sender_email = "", from_raw.strip()

    # Date
    received_at = ""
    date_str = msg.get("Date", "")
    if date_str:
        try:
            received_at = parsedate_to_datetime(date_str).astimezone(timezone.utc).isoformat()
        except Exception:
            received_at = date_str

    # Body: prefer plain text, fall back to HTML
    body_text = ""
    body_html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not body_text:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                body_text = _decode_str(payload, charset)
            elif ct == "text/html" and not body_html:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                body_html = _decode_str(payload, charset)
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        raw_body = _decode_str(payload, charset)
        if msg.get_content_type() == "text/html":
            body_html = raw_body
        else:
            body_text = raw_body

    full_body = body_text or strip_html(body_html)
    body_preview = full_body[:500].replace("\n", " ").strip()

    # Stable ID from Message-ID header; fall back to subject+date hash
    msg_id = msg.get("Message-ID", "").strip("<>").strip()
    if not msg_id:
        import hashlib
        msg_id = hashlib.sha1(f"{subject}{received_at}".encode()).hexdigest()

    return {
        "graph_id": msg_id,
        "subject": subject,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "received_at": received_at,
        "body_preview": body_preview,
        "full_body": full_body[:8000],
    }


class OutlookEmailFetcher:
    """Connects to Outlook/Microsoft 365 (or any IMAP server) via IMAP over SSL."""

    def __init__(self):
        self._imap: imaplib.IMAP4_SSL | None = None

    # ── Connection ─────────────────────────────────────────────────────────────

    def connect(self, email_addr: str, password: str,
                host: str = None, port: int = None) -> None:
        host = host or config.IMAP_HOST
        port = port or config.IMAP_PORT
        ctx = ssl.create_default_context()
        self._imap = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
        self._imap.login(email_addr, password)

    def disconnect(self):
        if self._imap:
            try:
                self._imap.logout()
            except Exception:
                pass
            self._imap = None

    def is_authenticated(self) -> bool:
        if not self._imap:
            return False
        try:
            self._imap.noop()
            return True
        except Exception:
            return False

    # ── Fetching ───────────────────────────────────────────────────────────────

    def fetch_emails(self, since_datetime: str = None,
                     max_count: int = None, folder: str = "INBOX") -> list[dict]:
        if not self._imap:
            raise RuntimeError("Not connected — call connect() first.")

        max_count = max_count or config.MAX_EMAILS_PER_POLL
        self._imap.select(folder, readonly=True)

        # IMAP SINCE uses DD-Mon-YYYY; derive date from ISO datetime string
        if since_datetime:
            try:
                dt = datetime.fromisoformat(since_datetime.replace("Z", "+00:00"))
                since_str = dt.strftime("%d-%b-%Y")
                typ, data = self._imap.search(None, f'(SINCE "{since_str}")')
            except Exception:
                typ, data = self._imap.search(None, "ALL")
        else:
            typ, data = self._imap.search(None, "ALL")

        if typ != "OK":
            return []

        ids = data[0].split()
        # Fetch most recent first
        ids = ids[::-1][:max_count]

        results = []
        for uid in ids:
            try:
                typ, msg_data = self._imap.fetch(uid, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                results.append(parse_email_message(msg))
            except Exception:
                continue

        return results

    # ── .eml file parsing ─────────────────────────────────────────────────────

    @staticmethod
    def parse_eml_bytes(data: bytes) -> dict:
        """Parse a raw .eml file into our standard email dict."""
        msg = email_lib.message_from_bytes(data)
        return parse_email_message(msg)
