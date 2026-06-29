import json
import os
from datetime import datetime, timezone
from pathlib import Path

import msal
import requests

import config


class OutlookEmailFetcher:
    def __init__(self):
        self._cache = msal.SerializableTokenCache()
        self._load_cache()
        self._app = msal.PublicClientApplication(
            client_id=config.AZURE_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{config.AZURE_TENANT_ID}",
            token_cache=self._cache,
        )

    def _load_cache(self):
        cache_path = Path(config.TOKEN_CACHE_PATH)
        if cache_path.exists():
            self._cache.deserialize(cache_path.read_text())

    def _save_cache(self):
        if self._cache.has_state_changed:
            Path(config.TOKEN_CACHE_PATH).write_text(self._cache.serialize())

    def _get_token(self) -> str | None:
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(config.GRAPH_SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._save_cache()
                return result["access_token"]
        return None

    def is_authenticated(self) -> bool:
        return bool(self._get_token())

    def initiate_device_flow(self) -> dict:
        """Start device code auth flow. Returns flow dict with user_code and verification_uri."""
        flow = self._app.initiate_device_flow(scopes=config.GRAPH_SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Failed to create device flow: {flow.get('error_description', 'unknown error')}")
        return flow

    def complete_device_flow(self, flow: dict) -> bool:
        """Poll until the user completes authentication. Returns True on success."""
        result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" in result:
            self._save_cache()
            return True
        return False

    def _graph_get(self, path: str, params: dict = None) -> dict:
        token = self._get_token()
        if not token:
            raise RuntimeError("Not authenticated. Run auth flow first.")
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        resp = requests.get(
            f"{config.GRAPH_API_BASE}{path}",
            headers=headers,
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_current_user(self) -> dict:
        return self._graph_get("/me")

    def fetch_emails(self, since_datetime: str = None, max_count: int = None) -> list[dict]:
        """Fetch emails from the inbox, optionally filtered by datetime."""
        max_count = max_count or config.MAX_EMAILS_PER_POLL
        params = {
            "$select": "id,subject,from,receivedDateTime,bodyPreview,body",
            "$orderby": "receivedDateTime desc",
            "$top": min(max_count, 100),
        }
        if since_datetime:
            params["$filter"] = f"receivedDateTime gt {since_datetime}"

        results = []
        url = "/me/messages"

        while url and len(results) < max_count:
            if url.startswith("http"):
                # nextLink is a full URL
                token = self._get_token()
                headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
                resp = requests.get(url, headers=headers, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            else:
                data = self._graph_get(url, params if url == "/me/messages" else None)

            results.extend(data.get("value", []))
            url = data.get("@odata.nextLink")

        return results[:max_count]

    def parse_email(self, raw: dict) -> dict:
        """Normalize a raw Graph API email object."""
        sender = raw.get("from", {}).get("emailAddress", {})
        return {
            "graph_id": raw["id"],
            "subject": raw.get("subject", "(no subject)"),
            "sender_name": sender.get("name", ""),
            "sender_email": sender.get("address", ""),
            "received_at": raw.get("receivedDateTime", ""),
            "body_preview": raw.get("bodyPreview", ""),
            "full_body": raw.get("body", {}).get("content", ""),
            "body_type": raw.get("body", {}).get("contentType", "text"),
        }
