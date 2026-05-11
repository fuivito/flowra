from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

from .config import Config

logger = logging.getLogger(__name__)

_MODEL = "gemini-2.5-flash"

_SYSTEM_PROMPT = """You are an expert B2B copywriter helping a startup called Flowra reach out to Italian CFOs.
Flowra is an AI-powered cash flow intelligence platform for SMEs.

Your job is to personalize a provided email template for a specific recipient.
You will be given the template and the recipient's details.

Rules:
- Replace all placeholders like {{first_name}}, {{company_name}}, etc. with real values from the contact details
- Keep the tone professional but warm and concise
- Do not invent facts about the recipient's company that aren't provided
- The email must be in the same language as the template (Italian or English)
- Return ONLY valid JSON in this exact format, no markdown, no explanation:
{"subject": "...", "body": "..."}
"""


class GeminiDrafter:
    def __init__(self, config: Config) -> None:
        genai.configure(api_key=config.gemini_api_key)
        self._model = genai.GenerativeModel(
            model_name=_MODEL,
            system_instruction=_SYSTEM_PROMPT,
        )

    def personalize_email(
        self,
        template_path: str,
        contact: dict,
        subject_override: str | None = None,
    ) -> tuple[str, str]:
        template = self._load_template(template_path)
        prompt = self._build_prompt(template, contact, subject_override)
        raw = self._call_with_backoff(prompt)
        generated_subject, body = self._parse_response(raw)
        subject = subject_override if subject_override is not None else generated_subject
        return subject, body

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _load_template(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(
                f"Template not found at '{path}'. "
                "Create the file and add your email template before running the agent."
            )
        content = p.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"Template at '{path}' is empty. Add your email content first.")
        return content

    def _build_prompt(self, template: str, contact: dict, subject_override: str | None = None) -> str:
        subject_instruction = (
            f"\nSUBJECT LINE: Use exactly this subject in the JSON subject field: {subject_override}"
            if subject_override is not None
            else ""
        )
        return (
            f"TEMPLATE:\n{template}\n\n"
            f"RECIPIENT DETAILS:\n"
            f"- Full name: {contact.get('full_name') or contact.get('first_name', '')}\n"
            f"- First name: {contact.get('first_name', '')}\n"
            f"- Last name: {contact.get('last_name', '')}\n"
            f"- Job title: {contact.get('job_title', '')}\n"
            f"- Company: {contact.get('company_name', '')}\n"
            f"- Company domain: {contact.get('company_domain', '')}\n"
            f"- Location: {contact.get('location', '')}\n"
            f"{subject_instruction}\n"
            "Personalize the template for this recipient and return JSON."
        )

    def _call_with_backoff(self, prompt: str, max_retries: int = 3) -> str:
        for attempt in range(max_retries):
            try:
                response = self._model.generate_content(prompt)
                return response.text
            except ResourceExhausted:
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) * 15
                    logger.warning("Gemini rate limit hit, waiting %ss", wait)
                    time.sleep(wait)
                else:
                    raise

    def _parse_response(self, raw: str) -> tuple[str, str]:
        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        try:
            data = json.loads(cleaned)
            subject = str(data.get("subject", "")).strip()
            body = str(data.get("body", "")).strip()
            if not subject or not body:
                raise ValueError("Empty subject or body in Gemini response")
            return subject, body
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse Gemini response as JSON: %s\nRaw: %s", e, raw[:500])
            raise ValueError(f"Gemini returned malformed JSON: {e}") from e
