"""Loguru logging setup for Tawala Core.

Default level: DEBUG (override with LOG_LEVEL).
"""

from __future__ import annotations

import sys

from loguru import logger

_configured = False


def setup_logging(level: str = "DEBUG") -> None:
    """Configure loguru once. Safe to call from lifespan and tests."""
    global _configured
    if _configured:
        logger.remove()
    else:
        logger.remove()  # drop default sink so we control format/level
    level_name = (level or "DEBUG").upper()
    logger.add(
        sys.stderr,
        level=level_name,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        enqueue=False,
        backtrace=True,
        diagnose=level_name == "DEBUG",
    )
    _configured = True
    logger.debug("logging configured level={}", level_name)


def get_logger():
    """Return the shared loguru logger."""
    return logger
