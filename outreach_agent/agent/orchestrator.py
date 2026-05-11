from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from .config import Config, load_config
from .notion_client import NotionOutreachClient
from .gemini_client import GeminiDrafter
from .email_sender import GmailSender
from . import scheduler

logger = logging.getLogger(__name__)

_SEND_DELAY = 2  # seconds between sends to respect Gmail rate limits

_AB_SUBJECTS = [
    "15 minuti – flusso di cassa",
    "Domanda",
    "Feedback rapido su un'idea",
    "Hai 15 minuti, {{first_name}}?",
]


def run(config: Config | None = None) -> None:
    if config is None:
        config = load_config()

    notion = NotionOutreachClient(config)
    gemini = GeminiDrafter(config)
    sender = GmailSender(config)

    sent_new = 0
    sent_followup = 0
    skipped = 0
    errors = 0

    # ── Phase A: initial outreach ──────────────────────────────────────────────
    logger.info("Phase A — fetching contacts with status 'To reach out'")
    new_contacts = notion.fetch_contacts_to_reach_out()
    logger.info("Found %d contact(s) to reach out to", len(new_contacts))

    for i, contact in enumerate(new_contacts):
        page_id = contact["page_id"]
        email = contact["email"]
        name = contact.get("full_name") or contact.get("first_name") or email

        raw_subject = _AB_SUBJECTS[i % len(_AB_SUBJECTS)]
        subject_override = raw_subject.replace("{{first_name}}", contact.get("first_name") or "")

        try:
            subject, body = gemini.personalize_email(config.template_path, contact, subject_override)
        except Exception as e:
            logger.error("Gemini failed for %s: %s", name, e)
            notion.write_agent_note(page_id, f"Gemini error: {e}")
            errors += 1
            continue

        # Lock the row before sending to prevent duplicate sends on re-run
        notion.lock_contact(page_id)

        sent_at = _now_iso()
        success, message_id = sender.send(email, subject, body)

        if success:
            notion.mark_email1_sent(page_id, sent_at, message_id, subject)
            logger.info("[NEW] Sent to %s (%s)", name, email)
            sent_new += 1
        else:
            notion.revert_to_reach_out(page_id)
            notion.write_agent_note(page_id, f"Send failed at {sent_at} — check logs")
            errors += 1

        time.sleep(_SEND_DELAY)

    # ── Phase B: follow-ups ────────────────────────────────────────────────────
    logger.info("Phase B — fetching contacts due for follow-up")
    followup_contacts = notion.fetch_contacts_due_for_followup()
    logger.info("Found %d contact(s) in follow-up pipeline", len(followup_contacts))

    for contact in followup_contacts:
        page_id = contact["page_id"]
        email = contact["email"]
        name = contact.get("full_name") or contact.get("first_name") or email
        followup_count = contact["followup_count"]
        previous_status = contact["status"]

        if not scheduler.is_due(contact, config.followup_intervals_days):
            skipped += 1
            continue

        followup_num = followup_count + 1  # 1 or 2
        template_path = (
            config.followup_1_template_path if followup_num == 1
            else config.followup_2_template_path
        )

        try:
            subject, body = gemini.personalize_email(template_path, contact)
        except Exception as e:
            logger.error("Gemini failed for follow-up %d to %s: %s", followup_num, name, e)
            notion.write_agent_note(page_id, f"Gemini error (follow-up {followup_num}): {e}")
            errors += 1
            continue

        notion.lock_contact(page_id)

        sent_at = _now_iso()
        success, _ = sender.send(
            email, subject, body,
            reply_to_message_id=contact.get("thread_message_id") or None,
            reply_to_subject=contact.get("thread_subject") or None,
        )

        if success:
            notion.mark_followup_sent(page_id, followup_num, sent_at)
            logger.info("[FOLLOW-UP %d] Sent to %s (%s)", followup_num, name, email)
            sent_followup += 1
        else:
            notion.revert_followup_status(page_id, previous_status)
            notion.write_agent_note(page_id, f"Follow-up {followup_num} send failed at {sent_at}")
            errors += 1

        time.sleep(_SEND_DELAY)

    logger.info(
        "Run complete — new: %d, follow-ups: %d, skipped (not due): %d, errors: %d",
        sent_new, sent_followup, skipped, errors,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
