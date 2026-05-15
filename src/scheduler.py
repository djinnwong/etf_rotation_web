from __future__ import annotations

from data_fetcher import fetch_weekly_prices_with_cache
from status_manager import get_market_status
from strategy_engine import run_strategy


def run_1455_preview() -> dict:
    data_result = fetch_weekly_prices_with_cache(force_refresh=True)
    rotation, _, _, _, summary = run_strategy(data_result.data)
    status = get_market_status()
    return {
        "task": "14:55 preview",
        "data_source": data_result.source,
        "status": status.status_text,
        "signal_date": summary.latest_signal_date,
        "next_holding_name": summary.next_holding_name,
        "next_holding_code": summary.next_holding_code,
        "rows": len(rotation),
    }


def run_1503_official_update() -> dict:
    data_result = fetch_weekly_prices_with_cache(force_refresh=True)
    rotation, _, _, _, summary = run_strategy(data_result.data)
    status = get_market_status()
    return {
        "task": "15:03 official update",
        "data_source": data_result.source,
        "status": status.status_text,
        "signal_date": summary.latest_signal_date,
        "next_holding_name": summary.next_holding_name,
        "next_holding_code": summary.next_holding_code,
        "rows": len(rotation),
    }


if __name__ == "__main__":
    print(run_1503_official_update())
