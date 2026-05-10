from __future__ import annotations

import logging
import smtplib
import ssl
import time
from email.mime.text import MIMEText
from email.utils import make_msgid

from .config import Config

logger = logging.getLogger(__name__)

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 465
_MAX_RETRIES = 3
_RETRY_WAIT = 30


class GmailSender:
    def __init__(self, config: Config) -> None:
        self._address = config.gmail_address
        self._password = config.gmail_app_password

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to_message_id: str | None = None,
        reply_to_subject: str | None = None,
    ) -> tuple[bool, str | None]:
        """Returns (success, message_id). message_id is None on failure."""
        message_id = make_msgid()
        msg = self._build_message(to, subject, body, message_id, reply_to_message_id, reply_to_subject)
        for attempt in range(_MAX_RETRIES):
            try:
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT, context=ctx) as server:
                    server.login(self._address, self._password)
                    server.sendmail(self._address, to, msg.as_string())
                logger.info("Email sent to %s — subject: %s", to, subject)
                return True, message_id
            except smtplib.SMTPAuthenticationError:
                logger.error("Gmail authentication failed. Check GMAIL_ADDRESS and GMAIL_APP_PASSWORD.")
                return False, None
            except smtplib.SMTPException as e:
                if attempt < _MAX_RETRIES - 1:
                    logger.warning("SMTP error (attempt %d/%d): %s — retrying in %ds", attempt + 1, _MAX_RETRIES, e, _RETRY_WAIT)
                    time.sleep(_RETRY_WAIT)
                else:
                    logger.error("Failed to send email to %s after %d attempts: %s", to, _MAX_RETRIES, e)
                    return False, None
        return False, None

    def _build_message(
        self,
        to: str,
        subject: str,
        body: str,
        message_id: str,
        reply_to_message_id: str | None,
        reply_to_subject: str | None,
    ) -> MIMEText:
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = self._address
        msg["To"] = to
        msg["Message-ID"] = message_id

        if reply_to_message_id:
            # Thread as a reply — Gmail uses these headers to group into the same thread
            msg["In-Reply-To"] = reply_to_message_id
            msg["References"] = reply_to_message_id
            original = reply_to_subject or subject
            clean = original.removeprefix("Re: ").removeprefix("RE: ")
            msg["Subject"] = f"Re: {clean}"
        else:
            msg["Subject"] = subject

        return msg
