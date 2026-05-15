from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

WEEKLY_PRICE_CSV = DATA_DIR / "weekly_prices.csv"
EXCEL_WEEKLY_PRICE_CSV = DATA_DIR / "excel_weekly_prices.csv"
ROTATION_RESULT_CSV = DATA_DIR / "rotation_result.csv"
DATA_SOURCE_STATUS_CSV = DATA_DIR / "data_source_status.csv"

ETF_LIST = {
    "518880": "黄金ETF",
    "513100": "纳指ETF",
    "159915": "创业板ETF",
}

START_DATE = "20130701"

# 用户确认最新策略周应包含 2026-05-11。
# 仅保留原始说明中的 2025-05-11 预估日期排除项。
EXCLUDE_ESTIMATE_DATES = {"2025-05-11"}

MOMENTUM_WEEKS = 4
INITIAL_NET_VALUE = 1.0

THEME_OPTIONS = ["跟随电脑 / 系统", "白天", "黑夜"]
THEME_FOLLOW_SYSTEM = "跟随电脑 / 系统"
THEME_LIGHT = "白天"
THEME_DARK = "黑夜"
