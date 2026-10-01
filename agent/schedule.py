"""Daylight-saving-aware schedule gate for the weekly refresh.

GitHub Actions cron schedules run in UTC, so the workflow is triggered by two crons
(``0 23 * * 1`` and ``0 0 * * 2``). Exactly one of them corresponds to Monday 7 p.m. in
US Eastern time depending on whether daylight saving time is in effect. This module decides
whether the cron that fired is the right one.

Usage: ``python -m agent.schedule "<cron expression>"`` prints ``run=true`` or ``run=false``.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
TARGET_WEEKDAY = 1  # cron day-of-week: Monday
TARGET_HOUR = 19  # 7 p.m.


def should_run(cron: str | None, now: datetime | None = None) -> bool:
    """Return True if ``cron`` (UTC) fires at Monday 7 p.m. Eastern at time ``now``.

    An empty cron (manual or push trigger) always runs.
    """
    if not cron or not cron.strip():
        return True
    fields = cron.split()
    if len(fields) != 5 or not fields[1].isdigit() or not fields[4].isdigit():
        return False
    utc_hour, utc_weekday = int(fields[1]), int(fields[4])
    now = now or datetime.now(timezone.utc)
    offset_hours = int(now.astimezone(EASTERN).utcoffset().total_seconds() // 3600)
    local_hour = utc_hour + offset_hours
    local_weekday = (utc_weekday + local_hour // 24) % 7
    return local_weekday == TARGET_WEEKDAY and local_hour % 24 == TARGET_HOUR


if __name__ == "__main__":
    print(f"run={'true' if should_run(sys.argv[1] if len(sys.argv) > 1 else '') else 'false'}")
