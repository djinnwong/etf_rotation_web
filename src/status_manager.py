from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


try:
    import chinese_calendar as calendar
except ImportError:
    calendar = None


CHINA_TZ = ZoneInfo("Asia/Shanghai")
PRE_CLOSE_START = time(14, 55)
MARKET_CLOSE = time(15, 0)
DATA_READY = time(15, 3)
NEXT_OPEN_TIME = time(9, 0)
# 超过 15:00 后已经无法按 14:55 预估信号进行尾盘操作，因此 Telegram 不做延迟容错。
TELEGRAM_PRE_CLOSE_END = MARKET_CLOSE

MANUAL_MARKET_HOLIDAYS = {
    # 2025 年 A 股休市日。
    date(2025, 1, 1),
    date(2025, 1, 28),
    date(2025, 1, 29),
    date(2025, 1, 30),
    date(2025, 1, 31),
    date(2025, 2, 3),
    date(2025, 2, 4),
    date(2025, 4, 4),
    date(2025, 5, 1),
    date(2025, 5, 2),
    date(2025, 5, 5),
    date(2025, 6, 2),
    date(2025, 10, 1),
    date(2025, 10, 2),
    date(2025, 10, 3),
    date(2025, 10, 6),
    date(2025, 10, 7),
    date(2025, 10, 8),
    # 2026 年节假日安排来源：中国政府网，国务院办公厅国办发明电〔2025〕7号。
    # A 股市场周末不交易，因此只列工作日休市日期。
    date(2026, 1, 1),
    date(2026, 1, 2),
    date(2026, 2, 16),
    date(2026, 2, 17),
    date(2026, 2, 18),
    date(2026, 2, 19),
    date(2026, 2, 20),
    date(2026, 2, 23),
    date(2026, 4, 6),
    date(2026, 5, 1),
    date(2026, 5, 4),
    date(2026, 5, 5),
    date(2026, 6, 19),
    date(2026, 9, 25),
    date(2026, 10, 1),
    date(2026, 10, 2),
    date(2026, 10, 5),
    date(2026, 10, 6),
    date(2026, 10, 7),
}


@dataclass
class MarketStatus:
    status_text: str
    can_show_next_holding: bool
    is_processing: bool
    current_time: str
    current_trading_week_close_date: str
    next_open_date: str
    explanation: str
    calendar_source: str


def now_china() -> datetime:
    return datetime.now(tz=CHINA_TZ)


def is_trading_day(day: date) -> bool:
    if day.weekday() >= 5:
        return False
    if day in MANUAL_MARKET_HOLIDAYS:
        return False
    if calendar is None:
        return True
    try:
        return not calendar.is_holiday(day)
    except Exception:
        return True


def get_calendar_source(day: date) -> str:
    if day.year == 2026:
        return "manual_2026_holiday_table"
    if calendar is None:
        return "weekday_fallback"
    try:
        calendar.is_holiday(day)
        return "chinese_calendar"
    except Exception:
        return "weekday_fallback"


def trading_days_between(start_day: date, end_day: date) -> list[date]:
    days = []
    current = start_day
    while current <= end_day:
        if is_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def week_bounds(day: date) -> tuple[date, date]:
    monday = day - timedelta(days=day.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def get_week_last_trading_day(day: date) -> date:
    monday, sunday = week_bounds(day)
    days = trading_days_between(monday, sunday)
    if days:
        return days[-1]

    probe = monday - timedelta(days=1)
    for _ in range(14):
        if is_trading_day(probe):
            return probe
        probe -= timedelta(days=1)
    return day


def get_next_open_day(after_day: date) -> date:
    probe = after_day + timedelta(days=1)
    for _ in range(21):
        if is_trading_day(probe):
            return probe
        probe += timedelta(days=1)
    return probe


def parse_test_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    parsed = datetime.strptime(cleaned, "%Y-%m-%d %H:%M")
    return parsed.replace(tzinfo=CHINA_TZ)


def get_market_status(current_dt: datetime | None = None) -> MarketStatus:
    now = current_dt.astimezone(CHINA_TZ) if current_dt else now_china()
    today = now.date()
    calendar_source = get_calendar_source(today)
    reference_day = today
    if is_trading_day(today) and now.time() < NEXT_OPEN_TIME:
        reference_day = today - timedelta(days=1)

    close_day = get_week_last_trading_day(reference_day)
    next_open_day = get_next_open_day(close_day)
    next_open_dt = datetime.combine(next_open_day, NEXT_OPEN_TIME, tzinfo=CHINA_TZ)

    status_text = "尚未至收盘阶段"
    can_show_next_holding = False
    is_processing = False
    explanation = "本周最后一个交易日 14:55 前，不展示下周建议持仓。"

    if today < close_day:
        status_text = "尚未至收盘阶段"
    elif today == close_day:
        current_time = now.time()
        if current_time < PRE_CLOSE_START:
            status_text = "尚未至收盘阶段"
        elif PRE_CLOSE_START <= current_time < MARKET_CLOSE:
            status_text = "下周建议持仓"
            can_show_next_holding = True
            explanation = "已进入 14:55 至 15:00 的收盘前提示阶段。"
        elif MARKET_CLOSE <= current_time < DATA_READY:
            status_text = "数据处理中"
            is_processing = True
            explanation = "15:00 至 15:03 等待正式收盘数据更新。"
        else:
            status_text = "下周建议持仓"
            can_show_next_holding = True
            explanation = "15:03 后进入正式收盘信号阶段。"
    elif now < next_open_dt:
        status_text = "下周建议持仓"
        can_show_next_holding = True
        explanation = "本周收盘后至下一交易日 9:00 前，持续展示下周建议持仓。"
    else:
        close_day = get_week_last_trading_day(today)
        status_text = "尚未至收盘阶段"

    return MarketStatus(
        status_text=status_text,
        can_show_next_holding=can_show_next_holding,
        is_processing=is_processing,
        current_time=now.strftime("%Y-%m-%d %H:%M:%S"),
        current_trading_week_close_date=close_day.strftime("%Y-%m-%d"),
        next_open_date=next_open_day.strftime("%Y-%m-%d"),
        explanation=explanation,
        calendar_source=calendar_source,
    )


def should_send_weekly_preclose_alert(current_dt: datetime | None = None) -> tuple[bool, str]:
    now = current_dt.astimezone(CHINA_TZ) if current_dt else now_china()
    today = now.date()

    if not is_trading_day(today):
        return False, f"{today:%Y-%m-%d} 不是交易日，跳过 Telegram。"

    week_last_trading_day = get_week_last_trading_day(today)
    if today != week_last_trading_day:
        return (
            False,
            f"{today:%Y-%m-%d} 不是本周最后一个交易日，本周最后交易日是 {week_last_trading_day:%Y-%m-%d}，跳过 Telegram。",
        )

    current_time = now.time()
    if not (PRE_CLOSE_START <= current_time < TELEGRAM_PRE_CLOSE_END):
        return (
            False,
            f"当前时间 {now:%H:%M:%S} 不在 14:55 至 15:00 前的 Telegram 预估提醒窗口内，跳过 Telegram。",
        )

    return True, f"{today:%Y-%m-%d} 是本周最后一个交易日，当前处于 14:55 至 15:00 前的预估提醒窗口，允许发送 Telegram。"
