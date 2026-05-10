from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from notion_client import Client
from notion_client.errors import APIResponseError

from .config import Config

logger = logging.getLogger(__name__)

# ── Notion property names ──────────────────────────────────────────────────────
PROP_COMPANY_NAME = "Company Name"
PROP_FIRST_NAME = "First Name"
PROP_LAST_NAME = "Last Name"
PROP_FULL_NAME = "Full Name"
PROP_JOB_TITLE = "Job Title"
PROP_LOCATION = "Location"
PROP_COMPANY_DOMAIN = "Company Domain"
PROP_LINKEDIN = "LinkedIn Profile"
PROP_WORK_EMAIL = "Work Email"

# Agent-managed columns
PROP_STATUS = "Status"
PROP_EMAIL1_SENT_AT = "Email 1 sent at"
PROP_FOLLOWUP1_SENT_AT = "Follow-up 1 sent at"
PROP_FOLLOWUP2_SENT_AT = "Follow-up 2 sent at"
PROP_LAST_EMAIL_SENT_AT = "Last email sent at"
PROP_FOLLOWUP_COUNT = "Follow-up count"
PROP_AGENT_NOTES = "Agent notes"

# Status values
STATUS_TO_REACH_OUT = "To reach out"
STATUS_SENDING = "Sending..."
STATUS_EMAIL1_SENT = "Email 1 sent"
STATUS_FOLLOWUP1_SENT = "Follow-up 1 sent"
STATUS_FOLLOWUP2_SENT = "Follow-up 2 sent"
STATUS_REPLIED = "Replied"
STATUS_DONE = "Done"


class NotionOutreachClient:
    def __init__(self, config: Config) -> None:
        self._client = Client(auth=config.notion_token)
        self._db_id = config.notion_database_id

    # ── Public read methods ────────────────────────────────────────────────────

    def fetch_contacts_to_reach_out(self) -> list[dict]:
        results = self._query(
            filter={
                "and": [
                    {"property": PROP_STATUS, "select": {"equals": STATUS_TO_REACH_OUT}},
                    {"property": PROP_WORK_EMAIL, "email": {"is_not_empty": True}},
                ]
            }
        )
        return [self._parse_contact(p) for p in results]

    def fetch_contacts_due_for_followup(self) -> list[dict]:
        results = self._query(
            filter={
                "or": [
                    {"property": PROP_STATUS, "select": {"equals": STATUS_EMAIL1_SENT}},
                    {"property": PROP_STATUS, "select": {"equals": STATUS_FOLLOWUP1_SENT}},
                ]
            }
        )
        return [self._parse_contact(p) for p in results]

    # ── Public write methods ───────────────────────────────────────────────────

    def lock_contact(self, page_id: str) -> None:
        self._update(page_id, {PROP_STATUS: {"select": {"name": STATUS_SENDING}}})

    def mark_email1_sent(self, page_id: str, sent_at: str) -> None:
        self._update(page_id, {
            PROP_STATUS: {"select": {"name": STATUS_EMAIL1_SENT}},
            PROP_EMAIL1_SENT_AT: {"date": {"start": sent_at}},
            PROP_LAST_EMAIL_SENT_AT: {"date": {"start": sent_at}},
            PROP_FOLLOWUP_COUNT: {"number": 0},
        })

    def mark_followup_sent(self, page_id: str, followup_num: int, sent_at: str) -> None:
        if followup_num == 1:
            status = STATUS_FOLLOWUP1_SENT
            date_prop = PROP_FOLLOWUP1_SENT_AT
        else:
            status = STATUS_FOLLOWUP2_SENT
            date_prop = PROP_FOLLOWUP2_SENT_AT

        patch: dict[str, Any] = {
            PROP_STATUS: {"select": {"name": status}},
            date_prop: {"date": {"start": sent_at}},
            PROP_LAST_EMAIL_SENT_AT: {"date": {"start": sent_at}},
            PROP_FOLLOWUP_COUNT: {"number": followup_num},
        }
        if followup_num == 2:
            patch[PROP_STATUS] = {"select": {"name": STATUS_DONE}}
        self._update(page_id, patch)

    def revert_to_reach_out(self, page_id: str) -> None:
        self._update(page_id, {PROP_STATUS: {"select": {"name": STATUS_TO_REACH_OUT}}})

    def revert_followup_status(self, page_id: str, previous_status: str) -> None:
        self._update(page_id, {PROP_STATUS: {"select": {"name": previous_status}}})

    def write_agent_note(self, page_id: str, note: str) -> None:
        self._update(page_id, {PROP_AGENT_NOTES: {"rich_text": [{"text": {"content": note[:2000]}}]}})

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _query(self, filter: dict) -> list[dict]:
        pages: list[dict] = []
        cursor = None
        while True:
            kwargs: dict[str, Any] = {"database_id": self._db_id, "filter": filter}
            if cursor:
                kwargs["start_cursor"] = cursor
            resp = self._retry(lambda: self._client.databases.query(**kwargs))
            pages.extend(resp["results"])
            if not resp.get("has_more"):
                break
            cursor = resp["next_cursor"]
        return pages

    def _update(self, page_id: str, properties: dict) -> None:
        self._retry(lambda: self._client.pages.update(page_id=page_id, properties=properties))

    def _retry(self, fn, max_retries: int = 3):
        for attempt in range(max_retries):
            try:
                return fn()
            except APIResponseError as e:
                if e.status == 429 and attempt < max_retries - 1:
                    wait = 2 ** attempt * 5
                    logger.warning("Notion rate limit hit, waiting %ss", wait)
                    time.sleep(wait)
                else:
                    raise

    def _parse_contact(self, page: dict) -> dict:
        props = page["properties"]

        def text(key: str) -> str:
            p = props.get(key, {})
            ptype = p.get("type")
            if ptype == "title":
                return "".join(t["plain_text"] for t in p.get("title", []))
            if ptype == "rich_text":
                return "".join(t["plain_text"] for t in p.get("rich_text", []))
            if ptype == "email":
                return p.get("email") or ""
            if ptype == "url":
                return p.get("url") or ""
            if ptype == "select":
                sel = p.get("select")
                return sel["name"] if sel else ""
            return ""

        def number(key: str) -> int:
            p = props.get(key, {})
            return int(p.get("number") or 0)

        def date(key: str) -> str | None:
            p = props.get(key, {})
            d = p.get("date")
            return d["start"] if d else None

        return {
            "page_id": page["id"],
            "company_name": text(PROP_COMPANY_NAME),
            "first_name": text(PROP_FIRST_NAME),
            "last_name": text(PROP_LAST_NAME),
            "full_name": text(PROP_FULL_NAME),
            "job_title": text(PROP_JOB_TITLE),
            "location": text(PROP_LOCATION),
            "company_domain": text(PROP_COMPANY_DOMAIN),
            "linkedin": text(PROP_LINKEDIN),
            "email": text(PROP_WORK_EMAIL),
            "status": text(PROP_STATUS),
            "followup_count": number(PROP_FOLLOWUP_COUNT),
            "last_email_sent_at": date(PROP_LAST_EMAIL_SENT_AT),
        }
