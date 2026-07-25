"""Entry point for the scheduler process.

Runs all background loops (watchdog, billing, trends, engagement, radar, etc.)
in a single process. Must NOT run inside the web server — these loops would
duplicate across uvicorn workers.

Usage:
    python run_scheduler.py
"""

import asyncio
import logging
import signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


async def _run():
    from app.scheduler.loops import run_all_loops

    loop = asyncio.get_running_loop()

    def _shutdown(sig, _frame):
        logging.getLogger(__name__).info(
            "[scheduler] Received %s, shutting down...", signal.Signals(sig).name
        )
        for task in asyncio.all_tasks(loop):
            task.cancel()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        await run_all_loops()
    except asyncio.CancelledError:
        pass

    logging.getLogger(__name__).info("[scheduler] Stopped.")


if __name__ == "__main__":
    asyncio.run(_run())
