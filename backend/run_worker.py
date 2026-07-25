"""Entry point for the arq worker process.

Usage:
    python run_worker.py
"""

import logging
import sys

# Force all logging to stdout so Railway captures it
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)

print(f"[worker] Python {sys.version}", flush=True)

import arq
from app.workers.tasks import WorkerSettings

print("[worker] Imports OK, starting arq worker...", flush=True)

if __name__ == "__main__":
    arq.run_worker(WorkerSettings)  # type: ignore[arg-type]
