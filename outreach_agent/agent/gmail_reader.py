from __future__ import annotations

import imaplib
import logging

logger = logging.getLogger(__name__)


def fetch_reply_senders(
    gmail_address: str,
    gmail_app_password: str,
    contact_emails: list[str],
) -> set[str]:
    """Return the subset of contact_emails that have sent at least one message to the inbox."""
    if not contact_emails:
        return set()

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        mail.login(gmail_address, gmail_app_password)
        mail.select("inbox")

        replied: set[str] = set()
        for addr in contact_emails:
            _, data = mail.search(None, "FROM", f'"{addr}"')
            if data and data[0]:
                replied.add(addr.lower())
                logger.debug("Reply found from %s", addr)

        return replied
    finally:
        try:
            mail.logout()
        except Exception:
            pass
