from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json

import pandas as pd

from config import DATA_DIR, DATA_SOURCE_STATUS_CSV, ETF_LIST, EXCEL_WEEKLY_PRICE_CSV, EXCLUDE_ESTIMATE_DATES, WEEKLY_PRICE_CSV
from data_sources import (
    SourceResult,
    fetch_akshare_etf_daily,
    fetch_eastmoney_etf_daily,
    fetch_fallback_from_weekly,
    fetch_sina_daily,
    load_local_daily_cache,
    save_daily_cache,
)


CACHE_META_JSON = DATA_DIR / "data_status.json"
DATA_SOURCE_ERROR_LOG = DATA_DIR / "data_source_errors.log"


@dataclass
class FetchResult:
    data: pd.DataFrame
    source: str
    message: str
    updated_at: str
    source_status: pd.DataFrame
    error: str | None = None

    @property
    def is_realtime(self) -> bool:
        return self.source == "realtime"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_cache_metadata() -> dict:
    if not CACHE_META_JSON.exists():
        return {}
    try:
        return json.loads(CACHE_META_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_cache_metadata(source: str, message: str, latest_week: str | None, error: str | None = None) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source,
        "message": message,
        "updated_at": _now_text(),
        "latest_week": latest_week,
        "error": error,
    }
    CACHE_META_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_source_error_log(code: str, name: str, error_message: str) -> None:
    if not error_message:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with DATA_SOURCE_ERROR_LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{_now_text()}] {code} {name}\n{error_message}\n\n")


def friendly_error_message(error_message: str, selected_source: str = "本地缓存") -> str:
    if not error_message:
        return ""
    lowered = error_message.lower()
    if "nameresolutionerror" in lowered or "failed to resolve" in lowered or "nodename nor servname" in lowered:
        reason = "网络/DNS不可用"
    elif "proxyerror" in lowered or "proxy" in lowered:
        reason = "代理连接失败"
    elif "timeout" in lowered or "timed out" in lowered:
        reason = "数据源请求超时"
    elif "connection" in lowered:
        reason = "网络连接失败"
    else:
        reason = "实时数据源不可用"

    if selected_source.startswith("本地") or selected_source in {"Excel导入缓存", "fallback_from_weekly"}:
        return f"{reason}，已使用本地缓存。"
    return reason


def _empty_status() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["code", "name", "selected_source", "latest_date", "update_status", "error_message"]
    )


def load_data_source_status() -> pd.DataFrame:
    if DATA_SOURCE_STATUS_CSV.exists():
        status = pd.read_csv(DATA_SOURCE_STATUS_CSV)
        if "error_message" in status.columns:
            status["error_message"] = status.apply(
                lambda row: friendly_error_message(
                    str(row.get("error_message", "")),
                    str(row.get("selected_source", "本地缓存")),
                ),
                axis=1,
            )
        return status
    return _empty_status()


def _save_data_source_status(rows: list[dict]) -> pd.DataFrame:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    status = pd.DataFrame(rows)
    status = status[["code", "name", "selected_source", "latest_date", "update_status", "error_message"]]
    status.to_csv(DATA_SOURCE_STATUS_CSV, index=False, encoding="utf-8-sig")
    return status


def _daily_to_weekly(daily: pd.DataFrame, name: str) -> pd.DataFrame:
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["week_period"] = df["date"].dt.to_period("W-SUN")
    weekly = (
        df.groupby("week_period", as_index=False)
        .agg(
            日期=("date", "first"),
            **{
                f"{name}_open": ("open", "first"),
                f"{name}_high": ("high", "max"),
                f"{name}_low": ("low", "min"),
                f"{name}_close": ("close", "last"),
                f"{name}_volume": ("volume", "sum"),
                f"{name}_amount": ("amount", "sum"),
                f"{name}_source": ("source", "last"),
            },
        )
        .drop(columns=["week_period"])
    )
    return weekly


def _select_one_etf_daily(code: str, name: str) -> tuple[pd.DataFrame, dict]:
    errors = []
    source_attempts = [
        fetch_akshare_etf_daily,
        fetch_eastmoney_etf_daily,
        fetch_sina_daily,
        lambda symbol: load_local_daily_cache(symbol, name),
        lambda symbol: fetch_fallback_from_weekly(symbol, name),
    ]

    selected: SourceResult | None = None
    for fetcher in source_attempts:
        result = fetcher(code)
        if result.success and not result.data.empty:
            selected = result
            break
        errors.append(f"{result.source}: {result.error_message}")

    if selected is None:
        error_message = "；".join(errors)
        _append_source_error_log(code, name, error_message)
        status = {
            "code": code,
            "name": name,
            "selected_source": "-",
            "latest_date": "-",
            "update_status": "失败",
            "error_message": friendly_error_message(error_message, "-"),
        }
        return pd.DataFrame(), status

    latest_date = str(selected.data["date"].iloc[-1])
    if not selected.source.startswith("本地") and selected.source != "fallback_from_weekly":
        save_daily_cache(code, selected.data)
    error_message = "" if not errors else "；".join(errors)
    _append_source_error_log(code, name, error_message)
    status = {
        "code": code,
        "name": name,
        "selected_source": selected.source,
        "latest_date": latest_date,
        "update_status": "缓存" if selected.source.startswith("本地") or selected.source == "fallback_from_weekly" else "成功",
        "error_message": friendly_error_message(error_message, selected.source),
    }
    return selected.data, status


def diagnose_etf_sources(code: str) -> tuple[pd.DataFrame, str]:
    name = ETF_LIST.get(code)
    if name is None:
        raise ValueError(f"未知 ETF 代码: {code}")

    attempts = [
        ("AkShare ETF 历史行情接口", fetch_akshare_etf_daily),
        ("东方财富场内 ETF 历史接口", fetch_eastmoney_etf_daily),
        ("新浪行情", fetch_sina_daily),
        ("本地缓存", lambda symbol: load_local_daily_cache(symbol, name)),
        ("fallback_from_weekly", lambda symbol: fetch_fallback_from_weekly(symbol, name)),
    ]
    rows = []
    selected_source = "-"
    for display_name, fetcher in attempts:
        result = fetcher(code)
        row_count = int(len(result.data)) if result.data is not None else 0
        latest_date = "-"
        has_close = False
        if result.success and row_count > 0:
            has_close = "close" in result.data.columns
            if "date" in result.data.columns:
                latest_date = str(result.data["date"].iloc[-1])
            if selected_source == "-":
                selected_source = result.source
        rows.append(
            {
                "数据源": display_name,
                "内部名称": result.source,
                "是否成功": "成功" if result.success else "失败",
                "返回行数": row_count,
                "最新日期": latest_date,
                "是否含close字段": "是" if has_close else "否",
                "失败原因": friendly_error_message(result.error_message, result.source) if not result.success else "",
            }
        )
    return pd.DataFrame(rows), selected_source


def _build_weekly_from_sources() -> tuple[pd.DataFrame, pd.DataFrame]:
    merged: pd.DataFrame | None = None
    status_rows = []

    for code, name in ETF_LIST.items():
        daily, status = _select_one_etf_daily(code, name)
        status_rows.append(status)
        if daily.empty:
            continue

        weekly = _daily_to_weekly(daily, name=name)
        if merged is None:
            merged = weekly
        else:
            merged = pd.merge(merged, weekly, on="日期", how="outer")

    status_df = _save_data_source_status(status_rows)
    if merged is None:
        raise RuntimeError("所有数据源均失败，且没有可用本地缓存。")

    merged = merged.sort_values("日期").reset_index(drop=True)
    merged["日期"] = pd.to_datetime(merged["日期"]).dt.strftime("%Y-%m-%d")
    merged = merged[~merged["日期"].isin(EXCLUDE_ESTIMATE_DATES)]
    required_close_cols = [f"{name}_close" for name in ETF_LIST.values()]
    merged = merged.dropna(subset=required_close_cols).reset_index(drop=True)
    if merged.empty:
        raise RuntimeError("周线数据为空，无法继续计算策略。")
    return merged, status_df


def _preserve_cached_history(new_weekly: pd.DataFrame) -> pd.DataFrame:
    history_path = EXCEL_WEEKLY_PRICE_CSV if EXCEL_WEEKLY_PRICE_CSV.exists() else WEEKLY_PRICE_CSV
    if not history_path.exists():
        return new_weekly

    cached = pd.read_csv(history_path)
    if cached.empty or "日期" not in cached.columns:
        return new_weekly

    cached = cached.copy()
    new_weekly = new_weekly.copy()
    cached["日期"] = pd.to_datetime(cached["日期"]).dt.strftime("%Y-%m-%d")
    new_weekly["日期"] = pd.to_datetime(new_weekly["日期"]).dt.strftime("%Y-%m-%d")
    cached_latest = str(cached["日期"].max())
    additions = new_weekly[new_weekly["日期"] > cached_latest]
    merged = pd.concat([cached, additions], ignore_index=True)
    return merged.sort_values("日期").reset_index(drop=True)


def load_cached_weekly_prices() -> FetchResult:
    if not WEEKLY_PRICE_CSV.exists():
        raise FileNotFoundError(f"找不到本地缓存文件: {WEEKLY_PRICE_CSV}")

    df = pd.read_csv(WEEKLY_PRICE_CSV)
    metadata = _read_cache_metadata()
    latest_week = str(df["日期"].iloc[-1]) if not df.empty else ""
    return FetchResult(
        data=df,
        source="cache",
        message=f"当前使用本地缓存数据，最新策略周日期：{latest_week}",
        updated_at=metadata.get("updated_at", _now_text()),
        source_status=load_data_source_status(),
        error=None,
    )


def fetch_weekly_prices_with_cache(force_refresh: bool = True) -> FetchResult:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not force_refresh and WEEKLY_PRICE_CSV.exists():
        return load_cached_weekly_prices()

    try:
        weekly, status_df = _build_weekly_from_sources()
        weekly = _preserve_cached_history(weekly)
        weekly.to_csv(WEEKLY_PRICE_CSV, index=False, encoding="utf-8-sig")
        latest_week = str(weekly["日期"].iloc[-1])
        sources = status_df["selected_source"].astype(str)
        realtime_count = (~sources.str.startswith("本地") & (sources != "fallback_from_weekly")).sum()
        if realtime_count == len(status_df):
            source = "realtime"
            message = f"当前使用实时数据，最新策略周日期：{latest_week}"
            error = None
        else:
            source = "cache"
            message = f"实时数据源失败，当前使用本地缓存。最新策略周日期：{latest_week}"
            error = "部分或全部 ETF 使用本地缓存。"
        _write_cache_metadata(source=source, message=message, latest_week=latest_week, error=error)
        return FetchResult(
            data=weekly,
            source=source,
            message=message,
            updated_at=_now_text(),
            source_status=status_df,
            error=error,
        )
    except Exception as exc:
        if WEEKLY_PRICE_CSV.exists():
            cached = load_cached_weekly_prices()
            latest_week = str(cached.data["日期"].iloc[-1]) if not cached.data.empty else ""
            message = f"实时数据源失败，当前使用本地缓存。最新策略周日期：{latest_week}"
            friendly_error = friendly_error_message(str(exc), "本地缓存")
            _write_cache_metadata(source="cache", message=message, latest_week=latest_week, error=friendly_error)
            cached.message = message
            cached.error = friendly_error
            return cached
        raise RuntimeError(f"实时数据获取失败，且本地没有缓存 CSV。请先用 Excel 导入数据。错误: {exc}") from exc


def fetch_all_weekly_prices() -> pd.DataFrame:
    return fetch_weekly_prices_with_cache(force_refresh=True).data


if __name__ == "__main__":
    result = fetch_weekly_prices_with_cache(force_refresh=True)
    print(result.message)
    print(f"数据来源: {result.source}")
    print(f"数据行数: {len(result.data)}")
    print(f"已保存: {WEEKLY_PRICE_CSV}")
    print(result.source_status.to_string(index=False))
