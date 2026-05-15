from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from config import DATA_DIR, DATA_SOURCE_STATUS_CSV, ETF_LIST, EXCEL_WEEKLY_PRICE_CSV, EXCLUDE_ESTIMATE_DATES, WEEKLY_PRICE_CSV
from data_sources import daily_cache_path, is_weekly_only_cache
from strategy_engine import run_strategy


def read_excel_first_sheet(path: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0, header=None)
    header = raw.iloc[1].tolist()
    df = raw.iloc[2:].copy()
    df.columns = header

    rename_map = {
        "日期": "日期",
        "黄金ETF开盘": "黄金ETF_open",
        "黄金ETF收盘": "黄金ETF_close",
        "纳指ETF: Open": "纳指ETF_open",
        "纳指ETF: close": "纳指ETF_close",
        "创业板ETF：open": "创业板ETF_open",
        "创业板ETF：close": "创业板ETF_close",
    }
    missing = [column for column in rename_map if column not in df.columns]
    if missing:
        raise ValueError(f"Excel 第一张表缺少字段: {missing}")

    df = df[list(rename_map.keys())].rename(columns=rename_map)
    df["日期"] = pd.to_datetime(df["日期"], utc=True).dt.strftime("%Y-%m-%d")
    df = df[~df["日期"].isin(EXCLUDE_ESTIMATE_DATES)]

    price_cols = [col for col in df.columns if col != "日期"]
    for col in price_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=price_cols).reset_index(drop=True)

    for _, name in ETF_LIST.items():
        open_col = f"{name}_open"
        close_col = f"{name}_close"
        df[f"{name}_high"] = df[[open_col, close_col]].max(axis=1)
        df[f"{name}_low"] = df[[open_col, close_col]].min(axis=1)
        df[f"{name}_volume"] = 0
        df[f"{name}_amount"] = 0
        df[f"{name}_source"] = "Excel导入缓存"

    return df


def remove_excel_generated_daily_cache() -> None:
    for code in ETF_LIST:
        cache_path = daily_cache_path(code)
        if not cache_path.exists():
            continue
        try:
            daily = pd.read_csv(cache_path)
        except Exception:
            continue
        if is_weekly_only_cache(daily):
            cache_path.unlink()


def write_excel_weekly_status(prices: pd.DataFrame) -> None:
    status_rows = []
    for code, name in ETF_LIST.items():
        status_rows.append(
            {
                "code": code,
                "name": name,
                "selected_source": "Excel周线缓存",
                "latest_date": str(prices["日期"].iloc[-1]),
                "update_status": "缓存",
                "error_message": "仅用于周频策略信号，不用于当前收益率日线现值",
            }
        )
    pd.DataFrame(status_rows).to_csv(DATA_SOURCE_STATUS_CSV, index=False, encoding="utf-8-sig")


def main() -> None:
    if len(sys.argv) != 2:
        print("用法: python src/import_excel.py Excel文件完整路径")
        print("例子: python src/import_excel.py \"/Users/你的名字/Desktop/三轮轮动策略.xlsx\"")
        raise SystemExit(1)

    excel_path = Path(sys.argv[1])
    if not excel_path.exists():
        raise FileNotFoundError(f"找不到 Excel 文件: {excel_path}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    prices = read_excel_first_sheet(str(excel_path))
    prices.to_csv(WEEKLY_PRICE_CSV, index=False, encoding="utf-8-sig")
    prices.to_csv(EXCEL_WEEKLY_PRICE_CSV, index=False, encoding="utf-8-sig")
    remove_excel_generated_daily_cache()
    write_excel_weekly_status(prices)
    result, _, _, _, summary = run_strategy(prices)
    latest = result.dropna(subset=["下周应持有"]).iloc[-1]

    print(f"已从 Excel 导入周线数据: {WEEKLY_PRICE_CSV}")
    print(f"有效周线行数: {len(prices)}")
    print(f"最新有效周日期: {latest['日期']}")
    print(f"当前应该持有: {summary.current_holding_name}({summary.current_holding_code})")
    print(
        "最大回撤区间: "
        f"{summary.max_drawdown_peak_date} -> {summary.max_drawdown_trough_date} -> {summary.max_drawdown_recovery_date}"
    )


if __name__ == "__main__":
    main()
