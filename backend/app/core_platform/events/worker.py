"""Outbox worker entrypoint: ``python -m app.core_platform.events.worker``.

Processes pending outbox entries once (or in a loop with --loop).
Requires DATABASE_URL. Safe to run multiple instances (SKIP LOCKED).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.core_platform.events.publisher import run_once
from app.core_platform.shared.settings import get_settings
from app.db.session import dispose_engine, get_session_factory, reset_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("outbox.worker")


async def _session_run(limit: int) -> dict[str, int]:
    reset_engine()
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("Database session factory not configured")
    async with factory() as session:
        return await run_once(session, limit=limit)


async def main_async(limit: int, loop: bool, interval: float) -> None:
    get_settings().require_database_url()
    while True:
        try:
            stats = await _session_run(limit)
            logger.info(
                "outbox.batch claimed=%s published=%s failed=%s",
                stats["claimed"],
                stats["published"],
                stats["failed"],
            )
        except Exception:
            logger.exception("outbox.batch_error")
        if not loop:
            break
        await asyncio.sleep(interval)
    await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tawala Core outbox publisher")
    parser.add_argument("--limit", type=int, default=20, help="Max rows per batch")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument(
        "--interval", type=float, default=5.0, help="Seconds between batches in loop mode"
    )
    args = parser.parse_args(argv)
    asyncio.run(main_async(args.limit, args.loop, args.interval))
    return 0


if __name__ == "__main__":
    sys.exit(main())
