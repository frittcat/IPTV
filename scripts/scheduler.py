from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app import init_db, export_files, report, health_check, sync


def run():
    init_db(); last_live = last_vod = 0.0
    interval = max(3600, int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "3600")))
    while True:
        now = time.time()
        try:
            if now - last_live >= 24 * 3600:
                os.environ.setdefault("ADMIN_PASSWORD_HASH", "")
                # The scheduler is trusted inside the container and calls deterministic jobs directly.
                sync.__wrapped__() if hasattr(sync, "__wrapped__") else sync()
                last_live = now
            health_check(20)
            report()
        except Exception as exc:
            print(f"scheduler error: {exc}", flush=True)
        time.sleep(interval)

if __name__ == "__main__": run()
