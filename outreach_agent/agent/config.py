from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    notion_token: str
    notion_database_id: str
    gemini_api_key: str
    gmail_address: str
    gmail_app_password: str
    template_path: str
    followup_1_template_path: str
    followup_2_template_path: str
    followup_intervals_days: tuple[int, ...]
    log_level: str


def load_config() -> Config:
    missing = []

    def require(key: str) -> str:
        val = os.getenv(key, "").strip()
        if not val:
            missing.append(key)
        return val

    notion_token = require("NOTION_TOKEN")
    notion_database_id = require("NOTION_DATABASE_ID")
    gemini_api_key = require("GEMINI_API_KEY")
    gmail_address = require("GMAIL_ADDRESS")
    gmail_app_password = require("GMAIL_APP_PASSWORD")

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Copy .env.example to .env and fill in the values."
        )

    raw_intervals = os.getenv("FOLLOWUP_INTERVALS_DAYS", "2,4")
    try:
        intervals = tuple(int(x.strip()) for x in raw_intervals.split(","))
        if len(intervals) != 2:
            raise ValueError
    except ValueError:
        raise ValueError(
            "FOLLOWUP_INTERVALS_DAYS must be two comma-separated integers, e.g. '2,4'"
        )

    return Config(
        notion_token=notion_token,
        notion_database_id=notion_database_id,
        gemini_api_key=gemini_api_key,
        gmail_address=gmail_address,
        gmail_app_password=gmail_app_password,
        template_path=os.getenv("TEMPLATE_PATH", "templates/outreach.txt"),
        followup_1_template_path=os.getenv("FOLLOWUP_1_TEMPLATE_PATH", "templates/followup_1.txt"),
        followup_2_template_path=os.getenv("FOLLOWUP_2_TEMPLATE_PATH", "templates/followup_2.txt"),
        followup_intervals_days=intervals,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
