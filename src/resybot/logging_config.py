from __future__ import annotations

import logging
from pathlib import Path

from .config import LoggingConfig


def setup_logging(config: LoggingConfig) -> None:
    """Configure file + console logging with millisecond timestamps."""
    log_path = Path(config.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Millisecond-precision timestamps for timing analysis
    fmt = "%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # File handler always logs DEBUG (full detail for post-mortem)
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    # Console logs at configured level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, config.level.upper()))
    console_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    # Suppress noisy third-party debug logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)
    logging.getLogger("h2").setLevel(logging.WARNING)

    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[file_handler, console_handler],
    )
