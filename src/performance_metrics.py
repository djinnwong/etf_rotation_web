from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from status_manager import trading_days_between


@dataclass
class DrawdownSummary:
    max_drawdown: float
    peak_date: str
    peak_equity: float
    trough_date: str
    trough_equity: float
    recovery_date: str
    recovery_equity: float | None
    decline_trading_days: int | None
    recovery_trading_days: int | None
    total_trading_days: int | None
    current_drawdown_peak_date: str
    current_drawdown_peak_value: float
    current_drawdown_date: str
    current_drawdown_value: float
    validation_message: str


def count_trading_days(start_date: str, end_date: str) -> int:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end < start:
        return 0
    return len(trading_days_between(start, end))


def _empty_summary(message: str) -> DrawdownSummary:
    return DrawdownSummary(
        max_drawdown=0.0,
        peak_date="-",
        peak_equity=0.0,
        trough_date="-",
        trough_equity=0.0,
        recovery_date="尚未收复",
        recovery_equity=None,
        decline_trading_days=None,
        recovery_trading_days=None,
        total_trading_days=None,
        current_drawdown_peak_date="-",
        current_drawdown_peak_value=0.0,
        current_drawdown_date="-",
        current_drawdown_value=0.0,
        validation_message=message,
    )


def build_drawdown_summary(rotation: pd.DataFrame) -> DrawdownSummary:
    required = {"日期", "策略净值"}
    if not required.issubset(rotation.columns):
        return _empty_summary("当前策略结果缺少净值或策略周日期，无法计算最大回撤。")

    df = rotation.dropna(subset=["日期", "策略净值"]).copy()
    if df.empty:
        return _empty_summary("当前策略结果为空，无法计算最大回撤。")

    df["策略净值"] = pd.to_numeric(df["策略净值"], errors="coerce")
    df = df.dropna(subset=["策略净值"]).reset_index(drop=True)
    if df.empty:
        return _empty_summary("当前策略净值为空，无法计算最大回撤。")

    high_equity = float("-inf")
    high_date = "-"
    high_values = []
    high_dates = []
    drawdowns = []

    for _, row in df.iterrows():
        equity = float(row["策略净值"])
        signal_date = str(row["日期"])
        if equity >= high_equity:
            high_equity = equity
            high_date = signal_date
        high_values.append(high_equity)
        high_dates.append(high_date)
        drawdowns.append(equity / high_equity - 1 if high_equity else 0.0)

    df["历史最高净值_指标"] = high_values
    df["历史最高日期_指标"] = high_dates
    df["回撤_指标"] = drawdowns

    completed_candidates = []
    for idx, row in df.iterrows():
        peak_equity_for_row = float(row["历史最高净值_指标"])
        drawdown_for_row = float(row["回撤_指标"])
        if drawdown_for_row >= 0:
            continue
        future = df.loc[idx + 1 :]
        recovered = future[future["策略净值"] >= peak_equity_for_row]
        if recovered.empty:
            continue
        completed_candidates.append((drawdown_for_row, idx, recovered.index[0]))

    if completed_candidates:
        _, trough_idx, recovery_idx = min(completed_candidates, key=lambda item: item[0])
    else:
        trough_idx = df["回撤_指标"].idxmin()
        recovery_idx = None

    trough = df.loc[trough_idx]
    peak_date = str(trough["历史最高日期_指标"])
    peak_equity = float(trough["历史最高净值_指标"])
    trough_date = str(trough["日期"])
    trough_equity = float(trough["策略净值"])
    max_drawdown = trough_equity / peak_equity - 1 if peak_equity else 0.0

    if recovery_idx is None:
        after_trough = df.loc[trough_idx + 1 :].copy()
        recovered = after_trough[after_trough["策略净值"] >= peak_equity]
        recovery_idx = None if recovered.empty else recovered.index[0]

    if recovery_idx is None:
        recovery_date = "尚未收复"
        recovery_equity = None
        recovery_days = None
        total_days = None
    else:
        recovery = df.loc[recovery_idx]
        recovery_date = str(recovery["日期"])
        recovery_equity = float(recovery["策略净值"])
        recovery_days = count_trading_days(trough_date, recovery_date)
        total_days = count_trading_days(peak_date, recovery_date)

    decline_days = count_trading_days(peak_date, trough_date)
    latest = df.iloc[-1]
    validation_message = validate_user_drawdown_interval(df)

    return DrawdownSummary(
        max_drawdown=max_drawdown,
        peak_date=peak_date,
        peak_equity=peak_equity,
        trough_date=trough_date,
        trough_equity=trough_equity,
        recovery_date=recovery_date,
        recovery_equity=recovery_equity,
        decline_trading_days=decline_days,
        recovery_trading_days=recovery_days,
        total_trading_days=total_days,
        current_drawdown_peak_date=str(latest["历史最高日期_指标"]),
        current_drawdown_peak_value=float(latest["历史最高净值_指标"]),
        current_drawdown_date=str(latest["日期"]),
        current_drawdown_value=float(latest["策略净值"]),
        validation_message=validation_message,
    )


def validate_user_drawdown_interval(df: pd.DataFrame) -> str:
    expected_dates = {"2016-04-11", "2018-03-19", "2018-08-27"}
    available_dates = set(df["日期"].astype(str))
    if expected_dates.issubset(available_dates):
        rows = df.set_index(df["日期"].astype(str))
        peak = float(rows.loc["2016-04-11", "策略净值"])
        trough = float(rows.loc["2018-03-19", "策略净值"])
        recovery = float(rows.loc["2018-08-27", "策略净值"])
        if abs(peak - 2.4418) <= 0.02 and abs(trough - 1.8416) <= 0.02 and abs(recovery - 2.4518) <= 0.02:
            return "用户指定的 2016-04-11 至 2018-08-27 最大回撤区间已通过净值曲线复核。"
        return (
            "数据中存在用户指定日期，但净值不完全匹配："
            f"2016-04-11={peak:.4f}，2018-03-19={trough:.4f}，2018-08-27={recovery:.4f}。"
        )

    first_date = str(df["日期"].iloc[0])
    if first_date > "2016-04-11":
        return "当前数据文件缺少 2016-04-11 至 2017-08-01 的净值历史，无法复核用户指定最大回撤区间。"

    missing = sorted(expected_dates - available_dates)
    return "当前净值曲线缺少以下用户指定日期，无法完整复核最大回撤区间：" + "、".join(missing)
