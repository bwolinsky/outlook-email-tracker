import re
import anthropic
import config


class TopicAnalyzer:
    def __init__(self):
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def analyze(self, subject: str, body_preview: str, full_body: str,
                sender_name: str, existing_topics: list[str]) -> dict:
        """Analyze an email and return topic, summary, and action items."""

        # Prefer HTML-stripped body for context; fall back to preview
        body_text = self._strip_html(full_body) if full_body else body_preview
        body_text = body_text[:3000]  # cap to avoid large tokens

        existing_topics_str = (
            "\n".join(f"- {t}" for t in existing_topics)
            if existing_topics
            else "  (none yet)"
        )

        prompt = f"""You are an email topic organizer. Analyze the email below and respond with valid JSON only.

EXISTING TOPIC AREAS (prefer assigning to one of these if it fits naturally):
{existing_topics_str}

EMAIL:
Subject: {subject}
From: {sender_name}
Body excerpt:
{body_text}

Respond with this exact JSON structure:
{{
  "topic": "<concise topic area name, 2-4 words, Title Case>",
  "summary": "<1-2 sentence summary of the email content>",
  "action_items": ["<action item 1>", "<action item 2>"],
  "priority": "<high|medium|low>"
}}

Rules:
- "topic" should be a broad category (e.g., "Project Alpha", "HR & Benefits", "Finance", "Tech Support", "Sales Pipeline")
- Reuse an existing topic name if it fits; only create a new topic name when truly needed
- "action_items" should be an array of strings (can be empty [])
- "priority" is based on urgency/importance implied in the email
- Return ONLY the JSON, no other text"""

        message = self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        return self._parse_response(raw)

    def _parse_response(self, raw: str) -> dict:
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        import json
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: extract with regex
            topic_match = re.search(r'"topic"\s*:\s*"([^"]+)"', raw)
            summary_match = re.search(r'"summary"\s*:\s*"([^"]+)"', raw)
            data = {
                "topic": topic_match.group(1) if topic_match else "Uncategorized",
                "summary": summary_match.group(1) if summary_match else "",
                "action_items": [],
                "priority": "medium",
            }

        return {
            "topic": str(data.get("topic", "Uncategorized"))[:80],
            "summary": str(data.get("summary", ""))[:500],
            "action_items": [str(a) for a in data.get("action_items", [])],
            "priority": data.get("priority", "medium"),
        }

    @staticmethod
    def _strip_html(html: str) -> str:
        """Very lightweight HTML tag stripper."""
        text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"\s{2,}", " ", text)
        return text.strip()
