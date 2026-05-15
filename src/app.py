from __future__ import annotations

import pandas as pd
import streamlit as st

from config import THEME_LIGHT, THEME_OPTIONS
from data_fetcher import (
    fetch_weekly_prices_with_cache,
    friendly_error_message,
    load_cached_weekly_prices,
    load_data_source_status,
)
from status_manager import get_market_status, parse_test_datetime
from strategy_engine import build_position_return_snapshot, run_strategy
from ui_components import (
    apply_private_fund_theme,
    render_cumulative_rank,
    render_data_source_status,
    render_equity_curve,
    render_header,
    render_holding_records,
    render_kpi_row,
    render_position_cards,
    render_win_rate_stats,
)


st.set_page_config(page_title="CY-ETF轮动V1", layout="wide")
DASHBOARD_CACHE_VERSION = "2026-05-15-v8-excel-weekly-history"


@st.cache_data(show_spinner=False)
def load_dashboard_data(force_refresh: bool, cache_version: str) -> dict:
    data_result = fetch_weekly_prices_with_cache(force_refresh=force_refresh)
    rotation, holding_records, win_stats, cumulative_rank, summary = run_strategy(data_result.data)
    return {
        "data_result": data_result,
        "rotation": rotation,
        "holding_records": holding_records,
        "win_stats": win_stats,
        "cumulative_rank": cumulative_rank,
        "summary": summary,
    }


def load_cache_only_dashboard_data() -> dict | None:
    try:
        data_result = load_cached_weekly_prices()
        rotation, holding_records, win_stats, cumulative_rank, summary = run_strategy(data_result.data)
        return {
            "data_result": data_result,
            "rotation": rotation,
            "holding_records": holding_records,
            "win_stats": win_stats,
            "cumulative_rank": cumulative_rank,
            "summary": summary,
        }
    except Exception:
        return None


with st.sidebar:
    st.header("系统控制")
    theme_mode = st.radio("外观模式", THEME_OPTIONS, index=THEME_OPTIONS.index(THEME_LIGHT), key="theme_mode_v2")
    force_refresh = st.button("更新实时数据", type="primary")
    use_cache_only = st.checkbox("只使用本地缓存", value=False)
    st.divider()
    st.caption("收盘状态测试")
    test_time_text = st.text_input("测试时间", placeholder="例如：2026-05-15 14:56")
    st.button("应用测试时间")
    st.caption("留空时使用当前北京时间。格式必须是 YYYY-MM-DD HH:MM。")

apply_private_fund_theme(theme_mode)

try:
    status = get_market_status(parse_test_datetime(test_time_text))
except ValueError:
    st.sidebar.warning("测试时间格式错误，请使用 YYYY-MM-DD HH:MM。当前已改用北京时间。")
    status = get_market_status()

try:
    if use_cache_only:
        dashboard = load_cache_only_dashboard_data()
        if dashboard is None:
            st.error("本地缓存不存在。请先从 Excel 导入，或取消“只使用本地缓存”后联网更新。")
            st.stop()
    else:
        dashboard = load_dashboard_data(
            force_refresh=force_refresh,
            cache_version=DASHBOARD_CACHE_VERSION,
        )
except Exception as exc:
    dashboard = load_cache_only_dashboard_data()
    if dashboard is None:
        st.error("实时数据获取失败，并且本地没有可用缓存。")
        st.info("请先运行：python src/import_excel.py /Users/chaoyuwang/Desktop/李二二/三轮轮动策略.xlsx")
        st.stop()
    dashboard["data_result"].message = "当前使用本地缓存数据，实时数据更新失败。"
    dashboard["data_result"].error = friendly_error_message(str(exc), "本地缓存")

data_result = dashboard["data_result"]
rotation = dashboard["rotation"]
holding_records = dashboard["holding_records"]
win_stats = dashboard["win_stats"]
cumulative_rank = dashboard["cumulative_rank"]
summary = dashboard["summary"]
source_status = getattr(data_result, "source_status", load_data_source_status())
position_return = build_position_return_snapshot(summary=summary, current_time=status.current_time)

if data_result.error:
    st.sidebar.warning("实时数据更新失败，已自动切换本地缓存。")
    st.sidebar.caption(friendly_error_message(str(data_result.error), "本地缓存"))

render_header(
    data_message="当前使用实时数据" if data_result.is_realtime else "当前使用本地缓存数据",
    data_updated_at=data_result.updated_at,
    status=status,
)
render_position_cards(summary=summary, status=status, position_return=position_return)
render_kpi_row(summary=summary)

st.divider()
render_data_source_status(source_status)
render_equity_curve(rotation, theme_mode=theme_mode)

left, right = st.columns([1, 1])
with left:
    render_win_rate_stats(win_stats)
with right:
    render_cumulative_rank(cumulative_rank, theme_mode=theme_mode)

render_holding_records(holding_records)

with st.expander("数据说明"):
    st.write(data_result.message)
    st.write(f"策略结果行数：{len(rotation)}")
    st.write(f"持仓记录数：{len(holding_records)}")
    preview = rotation.tail(5).copy()
    for col in ["策略收益", "策略净值", "最大回撤"]:
        if col in preview.columns:
            preview[col] = pd.to_numeric(preview[col], errors="coerce")
    st.dataframe(preview, use_container_width=True, hide_index=True)
