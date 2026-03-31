from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .client import ResyClient
from .config import load_config
from .logging_config import setup_logging
from .notifications import build_notifiers, notify_all
from .retry import retry_booking

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="ResyBot — Resy reservation sniper")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--restaurant",
        type=str,
        default=None,
        help="Book only the named restaurant (default: all)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config.logging)
    logger.info("ResyBot starting")

    notifiers = build_notifiers(config.notifications)

    restaurants = config.restaurants
    if args.restaurant:
        restaurants = [r for r in restaurants if r.name == args.restaurant]
        if not restaurants:
            logger.error("Restaurant '%s' not found in config", args.restaurant)
            sys.exit(1)

    any_success = False
    with ResyClient(config.auth.api_key, config.auth.auth_token) as client:
        for restaurant in restaurants:
            logger.info("=== Processing: %s ===", restaurant.name)
            try:
                confirmation = retry_booking(client, restaurant, config.settings)
                notify_all(
                    notifiers,
                    restaurant.name,
                    confirmation,
                    failure_reason="No matching slots found within timeout",
                )
                if confirmation:
                    any_success = True
            except Exception:
                logger.exception("Unexpected error for %s", restaurant.name)
                notify_all(
                    notifiers,
                    restaurant.name,
                    None,
                    failure_reason="Unexpected error — check logs",
                )

    sys.exit(0 if any_success else 1)


if __name__ == "__main__":
    main()
