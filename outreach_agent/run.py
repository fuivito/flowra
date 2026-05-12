import argparse
import logging
import sys

from agent.config import load_config
from agent.orchestrator import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flowra outreach agent")
    parser.add_argument(
        "--followup",
        action="store_true",
        help="Check Gmail for replies, mark them in Notion, then send Follow-up 1 now",
    )
    args = parser.parse_args()

    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    run(config, check_replies=args.followup, force_followups=args.followup)
