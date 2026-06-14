from datetime import datetime
from zoneinfo import ZoneInfo


SYRIA_TIMEZONE = ZoneInfo("Asia/Damascus")


def now_syria():
    return datetime.now(SYRIA_TIMEZONE).replace(tzinfo=None)