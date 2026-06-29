import logging
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

import config
import tracker
import poller
from email_fetcher import OutlookEmailFetcher
from topic_analyzer import TopicAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

# Singletons shared across requests and scheduler
fetcher = OutlookEmailFetcher()
analyzer = TopicAnalyzer()
scheduler = BackgroundScheduler(daemon=True)

# In-memory store for the active device flow (only one auth at a time)
_auth_flow: dict | None = None
_auth_lock = threading.Lock()


# ── Scheduled polling ─────────────────────────────────────────────────────────

def _scheduled_poll():
    if not fetcher.is_authenticated():
        return
    logger.info("Scheduled poll starting")
    result = poller.run_poll_cycle(fetcher, analyzer)
    logger.info("Scheduled poll done: %s", result)


scheduler.add_job(
    _scheduled_poll,
    "interval",
    minutes=config.POLL_INTERVAL_MINUTES,
    id="email_poll",
    replace_existing=True,
)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if not fetcher.is_authenticated():
        return redirect(url_for("auth_start"))
    topics = tracker.get_all_topics()
    stats = tracker.get_stats()
    log = tracker.get_recent_log(20)
    return render_template("index.html", topics=topics, stats=stats, log=log)


@app.route("/topic/<int:topic_id>")
def topic_detail(topic_id):
    if not fetcher.is_authenticated():
        return redirect(url_for("auth_start"))
    with tracker.get_db() as conn:
        topic = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        return "Topic not found", 404
    emails = tracker.get_emails_by_topic(topic_id)
    return render_template("topic.html", topic=dict(topic), emails=emails)


@app.route("/auth")
def auth_start():
    global _auth_flow
    with _auth_lock:
        _auth_flow = fetcher.initiate_device_flow()
    return render_template("auth.html", flow=_auth_flow)


@app.route("/auth/poll")
def auth_poll():
    """AJAX endpoint the auth page polls to detect when login completes."""
    global _auth_flow
    with _auth_lock:
        if _auth_flow is None:
            return jsonify({"status": "no_flow"})
        if fetcher.is_authenticated():
            return jsonify({"status": "authenticated"})
        success = fetcher.complete_device_flow(_auth_flow)
        if success:
            _auth_flow = None
            tracker.log_event("auth", details="User authenticated via device flow")
            return jsonify({"status": "authenticated"})
        return jsonify({"status": "pending"})


@app.route("/refresh", methods=["POST"])
def manual_refresh():
    if not fetcher.is_authenticated():
        return jsonify({"error": "Not authenticated"}), 401
    result = poller.run_poll_cycle(fetcher, analyzer)
    return jsonify(result)


# ── API endpoints ─────────────────────────────────────────────────────────────

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
    logger.info("Poll interval: every %d minutes", config.POLL_INTERVAL_MINUTES)
    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=False)
