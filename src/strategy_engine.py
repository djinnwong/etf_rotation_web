from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from config import ETF_LIST, INITIAL_NET_VALUE, MOMENTUM_WEEKS, ROTATION_RESULT_CSV, WEEKLY_PRICE_CSV
from data_sources import daily_cache_path, is_weekly_only_cache
from performance_metrics import build_drawdown_summary
from status_manager import DATA_READY, get_week_last_trading_day, is_trading_day


ETF_NAME_TO_CODE = {name: code for code, name in ETF_LIST.items()}


@dataclass
class StrategySummary:
    current_holding_name: str
    current_holding_code: str
    current_holding_start_date: str
    current_holding_return: float
    next_holding_name: str
    next_holding_code: str
    latest_signal_date: str
    latest_net_value: float
    latest_drawdown: float
    max_drawdown: float
    max_drawdown_peak_date: str
    max_drawdown_peak_value: float
    max_drawdown_trough_date: str
    max_drawdown_trough_value: float
    max_drawdown_recovery_date: str
    max_drawdown_recovery_value: float | None
    max_drawdown_decline_trading_days: int | None
    max_drawdown_recovery_trading_days: int | None
    max_drawdown_total_trading_days: int | None
    current_drawdown_peak_date: str
    current_drawdown_peak_value: float
    current_drawdown_date: str
    current_drawdown_value: float
    drawdown_validation_message: str


@dataclass
class PositionReturnSnapshot:
    return_rate: float | None
    base_date: str
    base_price: float | None
    current_date: str
    current_price: float | None
    message: str


def calculate_rotation(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.copy()
    df["日期"] = pd.to_datetime(df["日期"])
    df = df.sort_values("日期").reset_index(drop=True)

    etf_names = list(ETF_LIST.values())
    for name in etf_names:
        close_col = f"{name}_close"
        df[f"{name}_4周涨幅"] = df[close_col] / df[close_col].shift(MOMENTUM_WEEKS) - 1
        df[f"{name}_当周涨幅"] = df[close_col] / df[close_col].shift(1) - 1

    momentum_cols = [f"{name}_4周涨幅" for name in etf_names]
    complete_momentum = df[momentum_cols].notna().all(axis=1)
    df["本周收盘后冠军"] = None
    df.loc[complete_momentum, "本周收盘后冠军"] = (
        df.loc[complete_momentum, momentum_cols]
        .idxmax(axis=1)
        .str.replace("_4周涨幅", "", regex=False)
    )

    df["下周应持有"] = df["本周收盘后冠军"]
    df["本周实际持有"] = df["本周收盘后冠军"].shift(1)
    df["页面展示持仓"] = df["下周应持有"]

    def get_strategy_return(row: pd.Series) -> float | None:
        holding = row["本周实际持有"]
        if pd.isna(holding) or not holding:
            return None
        return row[f"{holding}_当周涨幅"]

    df["策略收益"] = df.apply(get_strategy_return, axis=1)
    df["策略净值"] = (1 + df["策略收益"].fillna(0)).cumprod() * INITIAL_NET_VALUE
    df["历史最高净值"] = df["策略净值"].cummax()
    df["最大回撤"] = df["策略净值"] / df["历史最高净值"] - 1
    df["信号出现日期"] = df["日期"].dt.date.apply(lambda value: get_week_last_trading_day(value).strftime("%Y-%m-%d"))
    df["实际买入日期"] = df["信号出现日期"]
    high_dates = []
    high_values = []
    high_date = None
    high_value = None
    for _, row in df.iterrows():
        net_value = float(row["策略净值"])
        if high_value is None or net_value >= high_value:
            high_value = net_value
            high_date = row["信号出现日期"]
        high_dates.append(high_date)
        high_values.append(high_value)
    df["回撤起点日期"] = high_dates
    df["回撤起点净值"] = high_values
    df["日期"] = df["日期"].dt.strftime("%Y-%m-%d")
    return df


def build_holding_records(rotation: pd.DataFrame) -> pd.DataFrame:
    df = rotation.copy()
    df = df[df["页面展示持仓"].notna()].copy()
    if df.empty:
        return pd.DataFrame(
            columns=["持仓开始日期", "持仓结束日期", "持仓ETF", "持仓代码", "单次收益率", "是否盈利", "持仓周数"]
        )

    df["日期"] = pd.to_datetime(df["日期"])
    df["分组"] = (df["页面展示持仓"] != df["页面展示持仓"].shift(1)).cumsum()

    records = []
    for _, group in df.groupby("分组", sort=True):
        holding_name = str(group["页面展示持仓"].iloc[0])
        group_indices = group.index.tolist()
        realized_returns = []
        for idx in group_indices:
            next_idx = idx + 1
            if next_idx in rotation.index:
                value = rotation.loc[next_idx, f"{holding_name}_当周涨幅"]
                if pd.notna(value):
                    realized_returns.append(float(value))
        single_return = (pd.Series(realized_returns).add(1).prod() - 1) if realized_returns else 0.0
        records.append(
            {
                "持仓开始日期": str(group["实际买入日期"].iloc[0]),
                "持仓结束日期": str(group["实际买入日期"].iloc[-1]),
                "持仓ETF": holding_name,
                "持仓代码": ETF_NAME_TO_CODE.get(holding_name, "-"),
                "单次收益率": single_return,
                "是否盈利": "盈利" if single_return > 0 else "亏损",
                "持仓周数": int(len(group)),
            }
        )

    result = pd.DataFrame(records)
    for idx in range(len(result) - 1):
        result.loc[idx, "持仓结束日期"] = result.loc[idx + 1, "持仓开始日期"]
    return result


def build_win_rate_stats(holding_records: pd.DataFrame) -> pd.DataFrame:
    if holding_records.empty:
        return pd.DataFrame(columns=["ETF名称", "胜率", "总持仓次数", "平均收益率"])

    rows = []
    for name, group in holding_records.groupby("持仓ETF", sort=False):
        returns = group["单次收益率"].astype(float)
        rows.append(
            {
                "ETF名称": name,
                "胜率": (returns > 0).mean(),
                "总持仓次数": int(len(group)),
                "平均收益率": returns.mean(),
            }
        )
    return pd.DataFrame(rows).sort_values("胜率", ascending=False).reset_index(drop=True)


def build_cumulative_rank(holding_records: pd.DataFrame) -> pd.DataFrame:
    if holding_records.empty:
        return pd.DataFrame(columns=["ETF名称", "累计收益率", "总持仓次数"])

    rows = []
    for name, group in holding_records.groupby("持仓ETF", sort=False):
        returns = group["单次收益率"].astype(float)
        rows.append(
            {
                "ETF名称": name,
                "累计收益率": (1 + returns).prod() - 1,
                "总持仓次数": int(len(group)),
            }
        )
    return pd.DataFrame(rows).sort_values("累计收益率", ascending=False).reset_index(drop=True)


def build_strategy_summary(rotation: pd.DataFrame, holding_records: pd.DataFrame) -> StrategySummary:
    valid = rotation.dropna(subset=["下周应持有"]).copy()
    if valid.empty:
        raise ValueError("策略结果为空，无法生成当前信号。")

    latest = valid.iloc[-1]
    drawdown = build_drawdown_summary(valid)
    next_name = str(latest["下周应持有"])
    next_code = ETF_NAME_TO_CODE.get(next_name, "-")

    if holding_records.empty:
        current_name = str(latest["页面展示持仓"]) if pd.notna(latest["页面展示持仓"]) else next_name
        current_code = ETF_NAME_TO_CODE.get(current_name, "-")
        current_start = str(latest["日期"])
        current_return = 0.0
    else:
        current_record = holding_records.iloc[-1]
        current_name = str(current_record["持仓ETF"])
        current_code = str(current_record["持仓代码"])
        current_start = str(current_record["持仓开始日期"])
        current_return = float(current_record["单次收益率"])

    return StrategySummary(
        current_holding_name=current_name,
        current_holding_code=current_code,
        current_holding_start_date=current_start,
        current_holding_return=current_return,
        next_holding_name=next_name,
        next_holding_code=next_code,
        latest_signal_date=str(latest["日期"]),
        latest_net_value=float(latest["策略净值"]),
        latest_drawdown=float(latest["最大回撤"]),
        max_drawdown=drawdown.max_drawdown,
        max_drawdown_peak_date=drawdown.peak_date,
        max_drawdown_peak_value=drawdown.peak_equity,
        max_drawdown_trough_date=drawdown.trough_date,
        max_drawdown_trough_value=drawdown.trough_equity,
        max_drawdown_recovery_date=drawdown.recovery_date,
        max_drawdown_recovery_value=drawdown.recovery_equity,
        max_drawdown_decline_trading_days=drawdown.decline_trading_days,
        max_drawdown_recovery_trading_days=drawdown.recovery_trading_days,
        max_drawdown_total_trading_days=drawdown.total_trading_days,
        current_drawdown_peak_date=drawdown.current_drawdown_peak_date,
        current_drawdown_peak_value=drawdown.current_drawdown_peak_value,
        current_drawdown_date=drawdown.current_drawdown_date,
        current_drawdown_value=drawdown.current_drawdown_value,
        drawdown_validation_message=drawdown.validation_message,
    )


def _previous_trading_day(day: datetime) -> datetime:
    probe = day.date() - timedelta(days=1)
    for _ in range(30):
        if is_trading_day(probe):
            return datetime.combine(probe, datetime.min.time())
        probe -= timedelta(days=1)
    return datetime.combine(day.date() - timedelta(days=1), datetime.min.time())


def _latest_completed_trading_day(day: datetime) -> datetime:
    if is_trading_day(day.date()) and day.time() >= DATA_READY:
        return datetime.combine(day.date(), datetime.min.time())
    return _previous_trading_day(day)


def _previous_week_last_trading_day(day: datetime) -> datetime:
    current_monday = day.date() - timedelta(days=day.weekday())
    previous_week_end = current_monday - timedelta(days=1)
    probe = previous_week_end
    for _ in range(14):
        if is_trading_day(probe):
            return datetime.combine(probe, datetime.min.time())
        probe -= timedelta(days=1)
    return datetime.combine(previous_week_end, datetime.min.time())


def _load_close_series(code: str, name: str) -> pd.DataFrame:
    cache_path = daily_cache_path(code)
    if cache_path.exists():
        daily = pd.read_csv(cache_path)
        if {"date", "close"}.issubset(daily.columns) and not is_weekly_only_cache(daily):
            result = daily[["date", "close"]].copy()
            result["date"] = pd.to_datetime(result["date"])
            result["close"] = pd.to_numeric(result["close"], errors="coerce")
            return result.dropna().sort_values("date").reset_index(drop=True)

    return pd.DataFrame(columns=["date", "close"])


def _close_on_date(close_series: pd.DataFrame, target: datetime) -> tuple[str, float] | None:
    if close_series.empty:
        return None
    available = close_series[close_series["date"].dt.date == target.date()]
    if available.empty:
        return None
    row = available.iloc[-1]
    return row["date"].strftime("%Y-%m-%d"), float(row["close"])


def build_position_return_snapshot(summary: StrategySummary, current_time: str) -> PositionReturnSnapshot:
    name = summary.current_holding_name
    code = summary.current_holding_code
    if code == "-" or name not in ETF_NAME_TO_CODE:
        return PositionReturnSnapshot(None, "-", None, "-", None, "当前持仓标的信息不完整")

    try:
        current_dt = datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S")
        start_dt = datetime.strptime(summary.current_holding_start_date, "%Y-%m-%d")
    except ValueError:
        return PositionReturnSnapshot(None, "-", None, "-", None, "时间格式无法解析")

    base_target = start_dt
    current_target = _latest_completed_trading_day(current_dt)
    close_series = _load_close_series(code, name)

    base_target_text = base_target.strftime("%Y-%m-%d")
    current_target_text = current_target.strftime("%Y-%m-%d")
    if close_series.empty:
        return PositionReturnSnapshot(
            None,
            base_target_text,
            None,
            current_target_text,
            None,
            "缺少真实日线缓存；当前收益率必须使用买入日和上一个交易日的每日收盘价",
        )

    base = _close_on_date(close_series, base_target)
    current = _close_on_date(close_series, current_target)
    if base is None or current is None:
        missing = []
        if base is None:
            missing.append(f"基准日 {base_target_text}")
        if current is None:
            missing.append(f"现值日 {current_target_text}")
        return PositionReturnSnapshot(
            None,
            base[0] if base else base_target_text,
            base[1] if base else None,
            current[0] if current else current_target_text,
            current[1] if current else None,
            f"缺少{'、'.join(missing)}的真实日线收盘价；现值不能使用周线缓存替代",
        )

    base_date, base_price = base
    current_date, current_price = current
    if base_price == 0:
        return PositionReturnSnapshot(None, base_date, base_price, current_date, current_price, "基准价为 0，无法计算")

    return_rate = current_price / base_price - 1
    return PositionReturnSnapshot(
        return_rate=return_rate,
        base_date=base_date,
        base_price=base_price,
        current_date=current_date,
        current_price=current_price,
        message="当前收益率=最新已完成交易日收盘价/实际买入日收盘价-1",
    )


def run_strategy(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, StrategySummary]:
    rotation = calculate_rotation(prices)
    rotation.to_csv(ROTATION_RESULT_CSV, index=False, encoding="utf-8-sig")
    holding_records = build_holding_records(rotation)
    win_stats = build_win_rate_stats(holding_records)
    cumulative_rank = build_cumulative_rank(holding_records)
    summary = build_strategy_summary(rotation, holding_records)
    return rotation, holding_records, win_stats, cumulative_rank, summary
