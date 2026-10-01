from datetime import datetime, timezone

import pytest

from agent.schedule import should_run

EDT_MONDAY = datetime(2026, 10, 5, 23, 0, tzinfo=timezone.utc)  # Mon 7 p.m. EDT
EST_TUESDAY = datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)  # Mon 7 p.m. EST


@pytest.mark.parametrize("cron, now, expected", [
    ("0 23 * * 1", EDT_MONDAY, True),
    ("0 0 * * 2", EDT_MONDAY.replace(day=6, hour=0), False),
    ("0 0 * * 2", EST_TUESDAY, True),
    ("0 23 * * 1", EST_TUESDAY.replace(day=9, hour=23), False),
    ("", EDT_MONDAY, True),
    (None, EDT_MONDAY, True),
    ("bogus", EDT_MONDAY, False),
])
def test_should_run(cron, now, expected):
    assert should_run(cron, now) is expected
