from __future__ import annotations

import os
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import init_db, report, sync
from backend.health_worker import run_health_batch


def run():
    init_db()
    last_live_sync = 0.0
    last_report = 0.0
    interval = max(300, int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "900")))
    live_limit = max(1, min(200, int(os.getenv("HEALTH_LIVE_BATCH", "30"))))
    vod_limit = max(1, min(100, int(os.getenv("HEALTH_VOD_BATCH", "15"))))

    while True:
        now = time.time()
        try:
            # Keep source discovery/sync independent from health rotation. Existing
            # stream state is no longer reset by the health worker itself.
            if now - last_live_sync >= 24 * 3600:
                os.environ.setdefault("ADMIN_PASSWORD_HASH", "")
                sync.__wrapped__() if hasattr(sync, "__wrapped__") else sync()
                last_live_sync = now

            summary = run_health_batch(live_limit=live_limit, vod_limit=vod_limit)
            print(f"health batch: {summary}", flush=True)

            if now - last_report >= 6 * 3600:
                report()
                last_report = now
        except Exception as exc:
            print(f"scheduler error: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    run()
