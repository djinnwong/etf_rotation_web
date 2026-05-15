from __future__ import annotations

import pandas as pd

from config import (
    DATA_DIR,
    ETF_LIST,
    INITIAL_NET_VALUE,
    MOMENTUM_WEEKS,
    ROTATION_RESULT_CSV,
    WEEKLY_PRICE_CSV,
)


def _format_signal_name(name: str | None) -> str:
    return "" if name is None or pd.isna(name) else str(name)


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
    weekly_return_cols = [f"{name}_当周涨幅" for name in etf_names]

    complete_momentum = df[momentum_cols].notna().all(axis=1)
    df["本周收盘后冠军"] = None
    df.loc[complete_momentum, "本周收盘后冠军"] = (
        df.loc[complete_momentum, momentum_cols]
        .idxmax(axis=1)
        .str.replace("_4周涨幅", "", regex=False)
    )

    df["下周应持有"] = df["本周收盘后冠军"]
    df["本周实际持有"] = df["本周收盘后冠军"].shift(1)

    def get_strategy_return(row: pd.Series) -> float | None:
        holding = _format_signal_name(row["本周实际持有"])
        if not holding:
            return None
        return row[f"{holding}_当周涨幅"]

    df["策略收益"] = df.apply(get_strategy_return, axis=1)
    df["策略净值"] = (1 + df["策略收益"].fillna(0)).cumprod() * INITIAL_NET_VALUE
    df["历史最高净值"] = df["策略净值"].cummax()
    df["最大回撤"] = df["策略净值"] / df["历史最高净值"] - 1

    df["日期"] = df["日期"].dt.strftime("%Y-%m-%d")
    return df


def load_prices() -> pd.DataFrame:
    if not WEEKLY_PRICE_CSV.exists():
        raise FileNotFoundError(f"找不到数据文件: {WEEKLY_PRICE_CSV}; 请先运行 update_data.py")
    return pd.read_csv(WEEKLY_PRICE_CSV)


def update_rotation_result() -> pd.DataFrame:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_prices()
    result = calculate_rotation(prices)
    result.to_csv(ROTATION_RESULT_CSV, index=False, encoding="utf-8-sig")
    return result


if __name__ == "__main__":
    df = update_rotation_result()
    latest_signal = df.dropna(subset=["下周应持有"]).iloc[-1]
    print(f"已保存: {ROTATION_RESULT_CSV}")
    print(f"最新更新时间: {latest_signal['日期']}")
    print(f"当前应该持有: {latest_signal['下周应持有']}")
