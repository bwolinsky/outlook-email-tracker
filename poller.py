"""Background email polling and processing logic."""
import logging
from datetime import datetime, timezone

import tracker
from email_fetcher import OutlookEmailFetcher
from topic_analyzer import TopicAnalyzer

logger = logging.getLogger(__name__)


def run_poll_cycle(fetcher: OutlookEmailFetcher, analyzer: TopicAnalyzer) -> dict:
    """
    Fetch new emails, analyze topics, and update the tracker.
    Returns a summary dict of what happened.
    """
    now = datetime.now(timezone.utc).isoformat()
    summary = {"fetched": 0, "new": 0, "updated": 0, "errors": []}

    try:
        last_poll = tracker.get_app_state("last_poll_time")

        raw_emails = fetcher.fetch_emails(since_datetime=last_poll)
        summary["fetched"] = len(raw_emails)

        existing_topic_names = [t["name"] for t in tracker.get_all_topics()]

        for raw in raw_emails:
            try:
                email = fetcher.parse_email(raw)
                analysis = analyzer.analyze(
                    subject=email["subject"],
                    body_preview=email["body_preview"],
                    full_body=email["full_body"],
                    sender_name=email["sender_name"],
                    existing_topics=existing_topic_names,
                )

                topic_id = tracker.get_or_create_topic(
                    name=analysis["topic"],
                    description=None,
                )

                is_new = tracker.upsert_email(
                    graph_id=email["graph_id"],
                    subject=email["subject"],
                    sender_name=email["sender_name"],
                    sender_email=email["sender_email"],
                    received_at=email["received_at"],
                    body_preview=email["body_preview"],
                    full_body=email["full_body"],
                    topic_id=topic_id,
                    summary=analysis["summary"],
                    action_items=analysis["action_items"],
                )

                if is_new:
                    summary["new"] += 1
                    if analysis["topic"] not in existing_topic_names:
                        existing_topic_names.append(analysis["topic"])
                    tracker.log_event(
                        event_type="new_email",
                        topic_name=analysis["topic"],
                        email_subject=email["subject"],
                        sender_email=email["sender_email"],
                        details=f"Priority: {analysis['priority']}. {analysis['summary'][:200]}",
                    )
                else:
                    summary["updated"] += 1

            except Exception as e:
                err = f"Error processing email '{raw.get('subject', '?')}': {e}"
                logger.warning(err)
                summary["errors"].append(err)

        tracker.set_app_state("last_poll_time", now)
        tracker.log_event(
            event_type="poll_complete",
            details=f"Fetched {summary['fetched']}, new {summary['new']}, errors {len(summary['errors'])}",
        )

    except Exception as e:
        err = f"Poll cycle failed: {e}"
        logger.error(err)
        summary["errors"].append(err)
        tracker.log_event(event_type="poll_error", details=err)

    return summary
