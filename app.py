import base64
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from flask import (Flask, flash, jsonify, redirect, render_template,
                   request, url_for)

import config
import poller
import tracker
from email_fetcher import OutlookEmailFetcher
from topic_analyzer import TopicAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

fetcher = OutlookEmailFetcher()
analyzer = TopicAnalyzer()
scheduler = BackgroundScheduler(daemon=True)


# ── IMAP credential helpers ────────────────────────────────────────────────────

def _load_imap_credentials() -> tuple[str, str, str, int]:
    """Return (email, password, host, port) from DB > env > defaults."""
    email = tracker.get_app_state("imap_email") or config.IMAP_EMAIL
    pw_b64 = tracker.get_app_state("imap_password_b64")
    password = base64.b64decode(pw_b64).decode() if pw_b64 else config.IMAP_PASSWORD
    host = tracker.get_app_state("imap_host") or config.IMAP_HOST
    port_str = tracker.get_app_state("imap_port") or str(config.IMAP_PORT)
    return email, password, host, int(port_str)


def _ensure_connected() -> bool:
    """Connect to IMAP using stored credentials if not already connected."""
    if fetcher.is_authenticated():
        return True
    email, password, host, port = _load_imap_credentials()
    if not email or not password:
        return False
    try:
        fetcher.connect(email, password, host, port)
        return True
    except Exception as e:
        logger.warning("IMAP connect failed: %s", e)
        return False


# ── Scheduled polling ─────────────────────────────────────────────────────────

def _scheduled_poll():
    if not _ensure_connected():
        logger.info("Scheduled poll skipped — no credentials configured")
        return
    logger.info("Scheduled poll starting")
    result = poller.run_poll_cycle(fetcher, analyzer)
    logger.info("Scheduled poll done: %s", result)
    # Reconnect check: IMAP connection may have dropped
    if result.get("errors"):
        fetcher.disconnect()


scheduler.add_job(
    _scheduled_poll,
    "interval",
    minutes=config.POLL_INTERVAL_MINUTES,
    id="email_poll",
    replace_existing=True,
)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    needs_setup = not bool(
        tracker.get_app_state("imap_email") or config.IMAP_EMAIL
    )
    topics = tracker.get_all_topics()
    stats = tracker.get_stats()
    log = tracker.get_recent_log(25)
    return render_template("index.html",
                           topics=topics, stats=stats, log=log,
                           needs_setup=needs_setup)


@app.route("/topic/<int:topic_id>")
def topic_detail(topic_id):
    with tracker.get_db() as conn:
        topic = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        return "Topic not found", 404
    emails = tracker.get_emails_by_topic(topic_id)
    return render_template("topic.html", topic=dict(topic), emails=emails)


# ── Settings (IMAP credentials) ───────────────────────────────────────────────

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        imap_email = request.form.get("imap_email", "").strip()
        imap_password = request.form.get("imap_password", "").strip()
        imap_host = request.form.get("imap_host", "outlook.office365.com").strip()
        imap_port = request.form.get("imap_port", "993").strip()

        if not imap_email or not imap_password:
            flash("Email and password are required.", "danger")
            return redirect(url_for("settings"))

        # Test connection before saving
        test_fetcher = OutlookEmailFetcher()
        try:
            test_fetcher.connect(imap_email, imap_password, imap_host, int(imap_port))
            test_fetcher.disconnect()
        except Exception as e:
            flash(f"Connection failed: {e}", "danger")
            return redirect(url_for("settings"))

        tracker.set_app_state("imap_email", imap_email)
        tracker.set_app_state("imap_password_b64",
                              base64.b64encode(imap_password.encode()).decode())
        tracker.set_app_state("imap_host", imap_host)
        tracker.set_app_state("imap_port", imap_port)

        # Force reconnect
        fetcher.disconnect()

        tracker.log_event("settings_saved", details=f"IMAP configured for {imap_email}")
        flash("IMAP settings saved and connection verified!", "success")
        return redirect(url_for("index"))

    email, _, host, port = _load_imap_credentials()
    return render_template("settings.html", imap_email=email, imap_host=host, imap_port=port)


# ── Manual refresh ────────────────────────────────────────────────────────────

@app.route("/refresh", methods=["POST"])
def manual_refresh():
    if not _ensure_connected():
        return jsonify({"error": "IMAP not configured. Go to /settings first."}), 400
    # Reconnect each manual poll to avoid stale connection
    fetcher.disconnect()
    if not _ensure_connected():
        return jsonify({"error": "IMAP connect failed"}), 500
    result = poller.run_poll_cycle(fetcher, analyzer)
    return jsonify(result)


# ── .eml file upload ─────────────────────────────────────────────────────────

@app.route("/upload", methods=["POST"])
def upload_eml():
    files = request.files.getlist("eml_files")
    if not files:
        return jsonify({"error": "No files provided"}), 400

    results = {"processed": 0, "new": 0, "errors": []}
    existing_topic_names = [t["name"] for t in tracker.get_all_topics()]

    for f in files:
        if not f.filename:
            continue
        try:
            raw = f.read()
            email_data = OutlookEmailFetcher.parse_eml_bytes(raw)

            analysis = analyzer.analyze(
                subject=email_data["subject"],
                body_preview=email_data["body_preview"],
                full_body=email_data["full_body"],
                sender_name=email_data["sender_name"],
                existing_topics=existing_topic_names,
            )

            topic_id = tracker.get_or_create_topic(analysis["topic"])
            is_new = tracker.upsert_email(
                graph_id=email_data["graph_id"],
                subject=email_data["subject"],
                sender_name=email_data["sender_name"],
                sender_email=email_data["sender_email"],
                received_at=email_data["received_at"],
                body_preview=email_data["body_preview"],
                full_body=email_data["full_body"],
                topic_id=topic_id,
                summary=analysis["summary"],
                action_items=analysis["action_items"],
            )

            results["processed"] += 1
            if is_new:
                results["new"] += 1
                if analysis["topic"] not in existing_topic_names:
                    existing_topic_names.append(analysis["topic"])
                tracker.log_event(
                    event_type="upload_email",
                    topic_name=analysis["topic"],
                    email_subject=email_data["subject"],
                    sender_email=email_data["sender_email"],
                    details=f"Uploaded .eml. {analysis['summary'][:150]}",
                )
        except Exception as e:
            results["errors"].append(f"{f.filename}: {e}")

    return jsonify(results)


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/topics")
def api_topics():
    return jsonify(tracker.get_all_topics())


@app.route("/api/topics/<int:topic_id>/emails")
def api_topic_emails(topic_id):
    return jsonify(tracker.get_emails_by_topic(topic_id))


@app.route("/api/log")
def api_log():
    limit = int(request.args.get("limit", 50))
    return jsonify(tracker.get_recent_log(limit))


@app.route("/api/stats")
def api_stats():
    return jsonify(tracker.get_stats())


# ── Startup ───────────────────────────────────────────────────────────────────

def create_app():
    tracker.init_db()
    if not scheduler.running:
        scheduler.start()
    return app


if __name__ == "__main__":
    create_app()
    logger.info("Starting Outlook Email Tracker on port %d", config.FLASK_PORT)
    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=False)
