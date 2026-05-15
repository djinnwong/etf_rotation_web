from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from config import EXCLUDE_ESTIMATE_DATES
from strategy_engine import calculate_rotation, build_holding_records, build_strategy_summary


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
    df = df[list(rename_map.keys())].rename(columns=rename_map)
    df["日期"] = pd.to_datetime(df["日期"], utc=True).dt.strftime("%Y-%m-%d")
    df = df[~df["日期"].isin(EXCLUDE_ESTIMATE_DATES)]
    df = df.dropna()

    price_cols = [col for col in df.columns if col != "日期"]
    for col in price_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna().reset_index(drop=True)


def main() -> None:
    if len(sys.argv) != 2:
        print("用法: python src\\validate_against_excel.py Excel文件完整路径")
        print("例子: python src\\validate_against_excel.py C:\\\\Users\\\\你的名字\\\\Desktop\\\\三轮轮动策略.xlsx")
        raise SystemExit(1)

    excel_path = Path(sys.argv[1])
    if not excel_path.exists():
        raise FileNotFoundError(f"找不到 Excel 文件: {excel_path}")

    prices = read_excel_first_sheet(str(excel_path))
    result = calculate_rotation(prices)
    latest = result.dropna(subset=["下周应持有"]).iloc[-1]
    holding_records = build_holding_records(result)
    summary = build_strategy_summary(result, holding_records)

    print("Excel 第一张表读取成功。")
    print(f"有效周线行数: {len(prices)}")
    print(f"最新有效周日期: {latest['日期']}")
    print(f"当前应该持有: {summary.current_holding_name}({summary.current_holding_code})")
    print(
        "最大回撤区间: "
        f"{summary.max_drawdown_peak_date}({summary.max_drawdown_peak_value:.4f}) -> "
        f"{summary.max_drawdown_trough_date}({summary.max_drawdown_trough_value:.4f}) -> "
        f"{summary.max_drawdown_recovery_date}"
    )
    print(summary.drawdown_validation_message)
    print("最近 5 周结果:")
    cols = ["日期", "本周收盘后冠军", "下周应持有", "页面展示持仓", "本周实际持有", "策略收益", "策略净值"]
    print(result[cols].tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
