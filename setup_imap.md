# Setup Guide — IMAP + .eml Upload

## Option A — IMAP (automatic polling, recommended)

### 1. Enable IMAP in Outlook

**Personal Outlook.com / Hotmail:**
1. Go to https://outlook.live.com → Settings (gear) → View all Outlook settings
2. Mail → Sync email → toggle **IMAP** on
3. Save

**Microsoft 365 work / school account:**
- Ask your IT admin to enable IMAP for your mailbox, or use
  [Exchange Admin Center → Recipients → Mailboxes → Mailbox features].

### 2. App Password (if you use 2FA — most accounts do)

1. Go to https://account.microsoft.com/security
2. Advanced security options → App passwords → Create new
3. Copy the generated password — this is your `IMAP_PASSWORD`

### 3. Configure the app

Copy `.env.example` to `.env` and fill in:

```
IMAP_EMAIL=you@outlook.com
IMAP_PASSWORD=<password or app password from step 2>
IMAP_HOST=outlook.office365.com
IMAP_PORT=993
ANTHROPIC_API_KEY=<your key from https://console.anthropic.com>
FLASK_SECRET_KEY=<any long random string>
```

Or skip `.env` and enter credentials via the web UI at `/settings` after starting the app.

### 4. Run

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000. The app connects via IMAP and polls every 5 minutes.

---

## Option B — Upload .eml files (no IMAP needed)

Use this if IMAP is blocked or you just want to process a batch of saved emails.

**Export from Outlook desktop:**
- Open an email → File → Save As → choose type **.eml** (or use "Save All Attachments" for bulk)

**Export from Outlook Web:**
- Open email → ⋯ (More actions) → Download → saves as `.eml`

**Drag and drop** the `.eml` files onto the upload zone on the dashboard.
Each file is analyzed by Claude and automatically categorized into a topic area.
