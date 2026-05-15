from __future__ import annotations

from datetime import datetime, time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import ETF_LIST, THEME_DARK, THEME_FOLLOW_SYSTEM, THEME_LIGHT
from status_manager import MarketStatus
from strategy_engine import PositionReturnSnapshot, StrategySummary


THEMES = {
    THEME_LIGHT: {
        "app_bg": "#f4f7fb",
        "sidebar_bg": "#e8eef8",
        "panel": "#ffffff",
        "panel_alt": "#eef4ff",
        "text": "#132033",
        "muted": "#5e6b7d",
        "accent": "#0f62fe",
        "accent_2": "#ff7a00",
        "border": "#cbd8ea",
        "shadow": "0 18px 42px rgba(38, 73, 122, 0.14)",
        "metric_bg": "#ffffff",
        "plot_template": "plotly_white",
        "plot_bg": "#ffffff",
        "grid": "#d9e3f2",
        "model": "#1b1f3b",
    },
    THEME_DARK: {
        "app_bg": "#070b14",
        "sidebar_bg": "#0b1020",
        "panel": "#101827",
        "panel_alt": "#0d2235",
        "text": "#f6f7fb",
        "muted": "#a8b3c7",
        "accent": "#00d4ff",
        "accent_2": "#ffcf5a",
        "border": "#22324a",
        "shadow": "0 18px 52px rgba(0, 212, 255, 0.10)",
        "metric_bg": "#0d1422",
        "plot_template": "plotly_dark",
        "plot_bg": "#0d1422",
        "grid": "#26354d",
        "model": "#f6f7fb",
    },
}

ETF_LINE_COLORS = {
    "518880": "#f4c542",
    "159915": "#ff4d5e",
    "513100": "#20d982",
}
ETF_CHART_ORDER = ["518880", "159915", "513100"]


def get_theme(theme_mode: str) -> dict:
    # Streamlit 的 Python 进程不能稳定读取浏览器 prefers-color-scheme。
    # “跟随电脑 / 系统”用 CSS media query 尽量跟随页面外观；Plotly 图表默认按白天主题渲染。
    if theme_mode == THEME_FOLLOW_SYSTEM:
        return THEMES[THEME_LIGHT]
    return THEMES.get(theme_mode, THEMES[THEME_LIGHT])


def percent_text(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{value * 100:.2f}%"


def price_text(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{value:.4f}"


def apply_private_fund_theme(theme_mode: str) -> None:
    theme = get_theme(theme_mode)
    system_theme_css = ""
    if theme_mode == THEME_FOLLOW_SYSTEM:
        dark = THEMES[THEME_DARK]
        system_theme_css = f"""
        @media (prefers-color-scheme: dark) {{
            .stApp {{
                background:
                    radial-gradient(circle at 12% 8%, {dark["panel_alt"]} 0, transparent 26%),
                    radial-gradient(circle at 85% 5%, rgba(255, 122, 0, 0.16) 0, transparent 22%),
                    {dark["app_bg"]};
                color: {dark["text"]};
            }}
            [data-testid="stSidebar"] {{
                background: {dark["sidebar_bg"]};
                border-right: 1px solid {dark["border"]};
            }}
            h1, h2, h3 {{ color: {dark["text"]}; }}
            .metric-card {{
                background:
                    linear-gradient(135deg, rgba(255,255,255,0.08), transparent 42%),
                    linear-gradient(180deg, {dark["panel"]} 0%, {dark["metric_bg"]} 100%);
                border-color: {dark["border"]};
                box-shadow: {dark["shadow"]};
            }}
            .card-main {{ color: {dark["text"]}; }}
            .card-line, .small-muted {{ color: {dark["muted"]}; }}
            .card-title {{ color: {dark["accent"]}; }}
            .status-strip {{
                border-color: {dark["border"]};
                background: linear-gradient(90deg, {dark["panel"]}, {dark["panel_alt"]});
                color: {dark["text"]};
                box-shadow: {dark["shadow"]};
            }}
            div[data-testid="stMetric"] {{
                background: {dark["metric_bg"]};
                border-color: {dark["border"]};
                box-shadow: {dark["shadow"]};
            }}
        }}
        """
    st.markdown(
        f"""
        <style>
        .stApp {{
            background:
                radial-gradient(circle at 12% 8%, {theme["panel_alt"]} 0, transparent 26%),
                radial-gradient(circle at 85% 5%, rgba(255, 122, 0, 0.16) 0, transparent 22%),
                {theme["app_bg"]};
            color: {theme["text"]};
        }}
        [data-testid="stSidebar"] {{
            background: {theme["sidebar_bg"]};
            border-right: 1px solid {theme["border"]};
        }}
        h1, h2, h3 {{
            color: {theme["text"]};
            letter-spacing: 0;
        }}
        h1 {{
            font-size: 42px;
            font-weight: 900;
            background: linear-gradient(90deg, {theme["accent"]}, {theme["accent_2"]});
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .block-container {{
            padding-top: 2rem;
            padding-bottom: 3rem;
        }}
        .metric-card {{
            background:
                linear-gradient(135deg, rgba(255,255,255,0.08), transparent 42%),
                linear-gradient(180deg, {theme["panel"]} 0%, {theme["metric_bg"]} 100%);
            border: 1px solid {theme["border"]};
            border-radius: 14px;
            padding: 22px 24px;
            min-height: 222px;
            box-shadow: {theme["shadow"]};
        }}
        .card-title {{
            color: {theme["accent"]};
            font-size: 15px;
            font-weight: 700;
            margin-bottom: 16px;
        }}
        .card-main {{
            color: {theme["text"]};
            font-size: 34px;
            font-weight: 800;
            line-height: 1.15;
            margin-bottom: 12px;
        }}
        .card-line {{
            color: {theme["muted"]};
            font-size: 14px;
            line-height: 1.7;
        }}
        .status-strip {{
            border: 1px solid {theme["border"]};
            background: linear-gradient(90deg, {theme["panel"]}, {theme["panel_alt"]});
            border-radius: 14px;
            padding: 12px 16px;
            color: {theme["text"]};
            margin: 8px 0 18px 0;
            box-shadow: {theme["shadow"]};
        }}
        .status-ok {{
            color: {theme["accent_2"]};
            font-weight: 700;
        }}
        .small-muted {{
            color: {theme["muted"]};
            font-size: 13px;
        }}
        div[data-testid="stMetric"] {{
            background: {theme["metric_bg"]};
            border: 1px solid {theme["border"]};
            padding: 14px 16px;
            border-radius: 14px;
            box-shadow: {theme["shadow"]};
        }}
        div[data-testid="stDataFrame"] {{
            border: 1px solid {theme["border"]};
            border-radius: 14px;
            overflow: hidden;
            box-shadow: {theme["shadow"]};
        }}
        .stButton button {{
            border-radius: 999px;
            border: 1px solid {theme["border"]};
            background: linear-gradient(90deg, {theme["accent"]}, {theme["accent_2"]});
            color: #ffffff;
            font-weight: 700;
        }}
        {system_theme_css}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(data_message: str, data_updated_at: str, status: MarketStatus) -> None:
    st.title("CY-ETF轮动V1")
    st.markdown(
        f"""
        <div class="status-strip">
            <span class="status-ok">{data_message}</span>
            <span class="small-muted">　|　页面时间：{status.current_time}　|　数据更新时间：{data_updated_at}　|　运行状态：{status.status_text}　|　交易日历：{status.calendar_source}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_position_cards(
    summary: StrategySummary,
    status: MarketStatus,
    position_return: PositionReturnSnapshot,
) -> None:
    signal_ready_by_date = False
    try:
        current_dt = datetime.strptime(status.current_time, "%Y-%m-%d %H:%M:%S")
        signal_dt = datetime.combine(
            datetime.strptime(summary.latest_signal_date, "%Y-%m-%d").date(),
            time(15, 3),
        )
        signal_ready_by_date = current_dt >= signal_dt and not status.is_processing
    except ValueError:
        signal_ready_by_date = False

    show_next_holding = status.can_show_next_holding or signal_ready_by_date
    next_holding_line = summary.next_holding_name if show_next_holding else "-"
    next_code_line = summary.next_holding_code if show_next_holding else "-"
    next_card_main = summary.next_holding_name if show_next_holding else status.status_text

    left, right = st.columns(2)
    with left:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="card-title">目前持仓</div>
                <div class="card-main">{summary.current_holding_name}</div>
                <div class="card-line">代码：{summary.current_holding_code}</div>
                <div class="card-line">持仓开始日期：{summary.current_holding_start_date}</div>
                <div class="card-line">当前收益率：{percent_text(position_return.return_rate)}</div>
                <div class="card-line">基准：{position_return.base_date} 收盘 {price_text(position_return.base_price)}</div>
                <div class="card-line">现值：{position_return.current_date} 收盘 {price_text(position_return.current_price)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="card-title">下周持仓建议</div>
                <div class="card-main">{next_card_main}</div>
                <div class="card-line">预估下周持仓建议（数据取自当周收盘价格）：{next_holding_line}</div>
                <div class="card-line">代码：{next_code_line}</div>
                <div class="card-line">本周最后交易日：{status.current_trading_week_close_date}</div>
                <div class="card-line">下一交易日：{status.next_open_date} 09:00</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.caption(f"{status.explanation}；{position_return.message}")


def render_kpi_row(summary: StrategySummary, current_time: str | None = None) -> None:
    recovery_equity = "-" if summary.max_drawdown_recovery_value is None else f"{summary.max_drawdown_recovery_value:.4f}"
    current_drawdown = min(float(summary.latest_drawdown), 0.0)
    current_drawdown_end_date = summary.current_drawdown_date
    if current_time:
        current_drawdown_end_date = current_time.split(" ")[0]
    col1, col2, col3 = st.columns(3)
    col1.metric("策略最新净值", f"{summary.latest_net_value:.4f}")
    col2.metric("当前回撤", percent_text(current_drawdown))
    col3.metric("最新策略周日期", summary.latest_signal_date)
    st.markdown(
        f"""
        <div class="status-strip">
            <div><span class="status-ok">当前回撤区间</span>
            <span class="small-muted">　{summary.current_drawdown_peak_date} 净值 {summary.current_drawdown_peak_value:.4f}
            → {current_drawdown_end_date} 净值 {summary.current_drawdown_value:.4f}</span></div>
            <div style="margin-top:8px;"><span class="status-ok">模型最大回撤</span>
            <span class="small-muted">　{percent_text(summary.max_drawdown)}
            ｜开始：{summary.max_drawdown_peak_date} 净值 {summary.max_drawdown_peak_value:.4f}
            ｜最低点：{summary.max_drawdown_trough_date} 净值 {summary.max_drawdown_trough_value:.4f}
            ｜修复：{summary.max_drawdown_recovery_date} 净值 {recovery_equity}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if summary.drawdown_validation_message:
        st.caption(summary.drawdown_validation_message)


def render_equity_curve(rotation: pd.DataFrame, theme_mode: str) -> None:
    theme = get_theme(theme_mode)
    curve, asset_curves, missing_assets = build_equity_curve_data(rotation)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=curve["日期"],
            y=curve["策略净值"],
            mode="lines",
            name="CY-ETF轮动V1",
            line=dict(color=theme["model"], width=3.0),
            customdata=pd.DataFrame(
                {
                    "名称": ["CY-ETF轮动V1"] * len(curve),
                    "代码": ["MODEL"] * len(curve),
                    "收盘价": [None] * len(curve),
                }
            ),
            hovertemplate="日期：%{x|%Y-%m-%d}<br>名称：%{customdata[0]}<br>代码：%{customdata[1]}<br>累计收益：%{y:.4f}<extra></extra>",
        )
    )

    for code in ETF_CHART_ORDER:
        name = ETF_LIST[code]
        close_col = f"{name}_close"
        asset = asset_curves.get(code)
        if asset is None or asset.empty:
            continue

        fig.add_trace(
            go.Scatter(
                x=asset["日期"],
                y=asset["累计收益"],
                mode="lines",
                name=name,
                line=dict(color=ETF_LINE_COLORS.get(code, theme["accent_2"]), width=1.8),
                customdata=pd.DataFrame(
                    {
                        "名称": [name] * len(asset),
                        "代码": [code] * len(asset),
                        "收盘价": asset[close_col],
                    }
                ),
                hovertemplate=(
                    "日期：%{x|%Y-%m-%d}<br>"
                    "名称：%{customdata[0]}<br>"
                    "代码：%{customdata[1]}<br>"
                    "累计收益：%{y:.4f}<br>"
                    "当日收盘价：%{customdata[2]:.4f}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title="历史收益曲线",
        height=460,
        template=theme["plot_template"],
        paper_bgcolor=theme["app_bg"],
        plot_bgcolor=theme["plot_bg"],
        font=dict(color=theme["text"]),
        margin=dict(l=20, r=20, t=55, b=20),
        xaxis=dict(gridcolor=theme["grid"]),
        yaxis=dict(gridcolor=theme["grid"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig, use_container_width=True)
    if missing_assets:
        st.warning("以下标的缺少收盘价数据，收益曲线已自动跳过：" + "、".join(missing_assets))


def build_equity_curve_data(rotation: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[str]]:
    curve = rotation[["日期", "策略净值"]].copy()
    curve["日期"] = pd.to_datetime(curve["日期"])
    curve["策略净值"] = pd.to_numeric(curve["策略净值"], errors="coerce")
    curve = curve.dropna(subset=["日期", "策略净值"])

    missing_assets = []
    asset_curves = {}
    for code in ETF_CHART_ORDER:
        name = ETF_LIST[code]
        close_col = f"{name}_close"
        if close_col not in rotation.columns or rotation[close_col].dropna().empty:
            missing_assets.append(f"{name}({code})")
            continue

        asset = rotation[["日期", close_col]].copy()
        asset["日期"] = pd.to_datetime(asset["日期"])
        asset[close_col] = pd.to_numeric(asset[close_col], errors="coerce")
        asset = asset.dropna(subset=["日期", close_col]).sort_values("日期").reset_index(drop=True)
        first_close = asset[close_col].iloc[0]
        if pd.isna(first_close) or first_close == 0:
            missing_assets.append(f"{name}({code})")
            continue

        asset["累计收益"] = asset[close_col] / first_close
        asset["收盘价"] = asset[close_col]
        asset_curves[code] = asset
    return curve, asset_curves, missing_assets


def render_monthly_rolling_returns(rotation: pd.DataFrame, theme_mode: str) -> None:
    theme = get_theme(theme_mode)
    curve, asset_curves, missing_assets = build_equity_curve_data(rotation)
    fig = go.Figure()

    model = curve.copy().sort_values("日期")
    model["月度滚动收益率"] = model["策略净值"] / model["策略净值"].shift(4) - 1
    model = model.dropna(subset=["月度滚动收益率"])
    fig.add_trace(
        go.Scatter(
            x=model["日期"],
            y=model["月度滚动收益率"],
            mode="lines",
            name="CY-ETF轮动V1",
            line=dict(color=theme["model"], width=2.8),
            hovertemplate="日期：%{x|%Y-%m-%d}<br>名称：CY-ETF轮动V1<br>月度滚动收益率：%{y:.2%}<extra></extra>",
        )
    )

    for code in ETF_CHART_ORDER:
        name = ETF_LIST[code]
        asset = asset_curves.get(code)
        if asset is None or asset.empty:
            continue
        close_col = f"{name}_close"
        monthly = asset[["日期", close_col]].copy().sort_values("日期")
        monthly["月度滚动收益率"] = monthly[close_col] / monthly[close_col].shift(4) - 1
        monthly = monthly.dropna(subset=["月度滚动收益率"])
        fig.add_trace(
            go.Scatter(
                x=monthly["日期"],
                y=monthly["月度滚动收益率"],
                mode="lines",
                name=name,
                line=dict(color=ETF_LINE_COLORS.get(code, theme["accent_2"]), width=1.8),
                hovertemplate=(
                    "日期：%{x|%Y-%m-%d}<br>"
                    f"名称：{name}<br>"
                    f"代码：{code}<br>"
                    "月度滚动收益率：%{y:.2%}<extra></extra>"
                ),
            )
        )

    fig.add_hline(y=0, line_width=1, line_dash="dot", line_color=theme["muted"])
    fig.update_layout(
        title="月度滚动收益率",
        height=360,
        template=theme["plot_template"],
        paper_bgcolor=theme["app_bg"],
        plot_bgcolor=theme["plot_bg"],
        font=dict(color=theme["text"]),
        margin=dict(l=20, r=20, t=55, b=20),
        xaxis=dict(gridcolor=theme["grid"]),
        yaxis=dict(gridcolor=theme["grid"], tickformat=".0%"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig, use_container_width=True)
    if missing_assets:
        st.warning("以下标的缺少收盘价数据，月度滚动收益率已自动跳过：" + "、".join(missing_assets))


def render_data_source_status(source_status: pd.DataFrame) -> None:
    st.subheader("数据源状态")
    if source_status.empty:
        st.info("暂无数据源状态。")
        return

    def short_error(value: object, selected_source: object) -> str:
        text = "" if pd.isna(value) else str(value)
        source = "" if pd.isna(selected_source) else str(selected_source)
        if not text:
            return ""
        lowered = text.lower()
        if (
            "httpsconnectionpool" in lowered
            or "nameresolutionerror" in lowered
            or "failed to resolve" in lowered
            or "push2his.eastmoney.com" in lowered
            or "finance.sina.com.cn" in lowered
            or "nodename nor servname" in lowered
        ):
            return "网络/DNS不可用，已使用本地缓存。" if source.startswith("本地") or source == "fallback_from_weekly" else "网络/DNS不可用。"
        if "proxy" in lowered:
            return "代理连接失败，已使用本地缓存。" if source.startswith("本地") or source == "fallback_from_weekly" else "代理连接失败。"
        if "timeout" in lowered:
            return "数据源请求超时，已使用本地缓存。" if source.startswith("本地") or source == "fallback_from_weekly" else "数据源请求超时。"
        return text if len(text) <= 60 else "实时数据源不可用，已使用本地缓存。"

    source_status = source_status.copy()
    if "error_message" in source_status.columns:
        source_status["error_message"] = source_status.apply(
            lambda row: short_error(row.get("error_message", ""), row.get("selected_source", "")),
            axis=1,
        )

    display = source_status.rename(
        columns={
            "code": "ETF代码",
            "name": "中文名称",
            "selected_source": "使用数据源",
            "latest_date": "最新日期",
            "update_status": "状态",
            "error_message": "错误原因",
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)


def render_win_rate_stats(win_stats: pd.DataFrame) -> None:
    st.subheader("各标的物胜率统计")
    display = win_stats.copy()
    if display.empty:
        st.info("暂无胜率统计。")
        return
    display["胜率"] = display["胜率"].map(percent_text)
    display["平均收益率"] = display["平均收益率"].map(percent_text)
    st.dataframe(display, use_container_width=True, hide_index=True)


def render_cumulative_rank(cumulative_rank: pd.DataFrame, theme_mode: str) -> None:
    theme = get_theme(theme_mode)
    st.subheader("累计收益率排行榜")
    if cumulative_rank.empty:
        st.info("暂无累计收益率排行。")
        return

    fig = px.bar(
        cumulative_rank,
        x="累计收益率",
        y="ETF名称",
        orientation="h",
        text=cumulative_rank["累计收益率"].map(percent_text),
        color="累计收益率",
        color_continuous_scale=["#ff4d5e", theme["accent"], theme["accent_2"]],
    )
    fig.update_layout(
        height=320,
        template=theme["plot_template"],
        paper_bgcolor=theme["app_bg"],
        plot_bgcolor=theme["plot_bg"],
        font=dict(color=theme["text"]),
        margin=dict(l=20, r=20, t=20, b=20),
        xaxis_tickformat=".0%",
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_holding_records(holding_records: pd.DataFrame) -> None:
    st.subheader("持仓记录表")
    if holding_records.empty:
        st.info("暂无持仓记录。")
        return

    display = holding_records.copy()
    display["持仓开始日期"] = pd.to_datetime(display["持仓开始日期"])
    display["持仓结束日期"] = pd.to_datetime(display["持仓结束日期"])
    display = display.sort_values("持仓开始日期", ascending=True).reset_index(drop=True)
    for idx in range(len(display) - 1):
        display.loc[idx, "持仓结束日期"] = display.loc[idx + 1, "持仓开始日期"]

    invalid = display["持仓结束日期"] < display["持仓开始日期"]
    if invalid.any():
        st.warning("发现持仓结束日期早于开始日期的异常记录，已在页面显示前自动按开始日期修正。")
        display.loc[invalid, "持仓结束日期"] = display.loc[invalid, "持仓开始日期"]

    display = display.sort_values("持仓开始日期", ascending=False)
    display["持仓开始日期"] = display["持仓开始日期"].dt.strftime("%Y-%m-%d")
    display["持仓结束日期"] = display["持仓结束日期"].dt.strftime("%Y-%m-%d")
    display["单次收益率"] = display["单次收益率"].map(percent_text)
    st.dataframe(display, use_container_width=True, hide_index=True)
