from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import os
import time

import pandas as pd
import requests

from config import DATA_DIR, START_DATE, WEEKLY_PRICE_CSV


MAX_RETRY_TIMES = 2
RETRY_SLEEP_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 6
WEEKLY_ONLY_SOURCES = {"Excel导入缓存", "本地周线缓存"}


@dataclass
class SourceResult:
    data: pd.DataFrame
    source: str
    success: bool
    error_message: str = ""


def clear_proxy_env() -> None:
    for key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"


def daily_cache_path(code: str) -> Path:
    return DATA_DIR / f"{code}_daily.csv"


def is_weekly_only_cache(df: pd.DataFrame) -> bool:
    if "source" not in df.columns:
        return False
    sources = set(df["source"].dropna().astype(str).unique())
    return bool(sources) and sources.issubset(WEEKLY_ONLY_SOURCES)


def normalize_daily_frame(df: pd.DataFrame, source: str) -> pd.DataFrame:
    result = df.copy()
    result["date"] = pd.to_datetime(result["date"]).dt.strftime("%Y-%m-%d")
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        result[col] = pd.to_numeric(result[col], errors="coerce")
    result = result[["date", "open", "high", "low", "close", "volume", "amount"]].dropna(
        subset=["date", "open", "close"]
    )
    result["source"] = source
    return result.sort_values("date").reset_index(drop=True)


def retry_source(fetcher: Callable[[], pd.DataFrame], source: str) -> SourceResult:
    clear_proxy_env()
    last_error = ""
    for attempt in range(1, MAX_RETRY_TIMES + 1):
        try:
            df = fetcher()
            df = normalize_daily_frame(df, source=source)
            if df.empty:
                raise ValueError("数据为空")
            return SourceResult(data=df, source=source, success=True)
        except Exception as exc:
            last_error = str(exc)
            if isinstance(exc, ModuleNotFoundError):
                break
            if attempt < MAX_RETRY_TIMES:
                time.sleep(RETRY_SLEEP_SECONDS)
    return SourceResult(data=pd.DataFrame(), source=source, success=False, error_message=last_error)


def fetch_akshare_etf_daily(code: str) -> SourceResult:
    def _fetch() -> pd.DataFrame:
        import akshare as ak

        raw = ak.fund_etf_hist_em(
            symbol=code,
            period="daily",
            start_date=START_DATE,
            end_date=pd.Timestamp.today().strftime("%Y%m%d"),
            adjust="",
        )
        return pd.DataFrame(
            {
                "date": raw["日期"],
                "open": raw["开盘"],
                "high": raw["最高"] if "最高" in raw.columns else raw["开盘"],
                "low": raw["最低"] if "最低" in raw.columns else raw["收盘"],
                "close": raw["收盘"],
                "volume": raw["成交量"] if "成交量" in raw.columns else 0,
                "amount": raw["成交额"] if "成交额" in raw.columns else 0,
            }
        )

    return retry_source(_fetch, source="AkShare场内ETF")


def _eastmoney_secid(code: str) -> str:
    if code.startswith(("5", "6")):
        return f"1.{code}"
    return f"0.{code}"


def fetch_eastmoney_etf_daily(code: str) -> SourceResult:
    def _fetch() -> pd.DataFrame:
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "klt": "101",
            "fqt": "0",
            "beg": START_DATE,
            "end": pd.Timestamp.today().strftime("%Y%m%d"),
            "secid": _eastmoney_secid(code),
        }
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
        klines = payload.get("data", {}).get("klines") or []
        rows = []
        for item in klines:
            parts = item.split(",")
            if len(parts) < 7:
                continue
            rows.append(
                {
                    "date": parts[0],
                    "open": parts[1],
                    "close": parts[2],
                    "high": parts[3],
                    "low": parts[4],
                    "volume": parts[5],
                    "amount": parts[6],
                }
            )
        return pd.DataFrame(rows)

    return retry_source(_fetch, source="东方财富接口")


def _tencent_symbol(code: str) -> str:
    return f"sh{code}" if code.startswith(("5", "6")) else f"sz{code}"


def fetch_tencent_etf_daily(code: str) -> SourceResult:
    def _fetch() -> pd.DataFrame:
        symbol = _tencent_symbol(code)
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        params = {
            "param": f"{symbol},day,{START_DATE},,4000",
        }
        response = requests.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        payload = response.json()
        symbol_data = payload.get("data", {}).get(symbol, {})
        rows = symbol_data.get("day") or []
        parsed_rows = []
        for item in rows:
            if len(item) < 5:
                continue
            parsed_rows.append(
                {
                    "date": item[0],
                    "open": item[1],
                    "close": item[2],
                    "high": item[3],
                    "low": item[4],
                    "volume": item[5] if len(item) > 5 else 0,
                    "amount": item[6] if len(item) > 6 else 0,
                }
            )
        return pd.DataFrame(parsed_rows)

    return retry_source(_fetch, source="腾讯行情接口")


def _sina_symbol(code: str) -> str:
    return f"sh{code}" if code.startswith(("5", "6")) else f"sz{code}"


def fetch_sina_daily(code: str) -> SourceResult:
    def _fetch() -> pd.DataFrame:
        import akshare as ak

        raw = ak.stock_zh_a_daily(symbol=_sina_symbol(code), start_date=START_DATE, adjust="")
        return pd.DataFrame(
            {
                "date": raw["date"],
                "open": raw["open"],
                "high": raw["high"],
                "low": raw["low"],
                "close": raw["close"],
                "volume": raw["volume"] if "volume" in raw.columns else 0,
                "amount": raw["amount"] if "amount" in raw.columns else 0,
            }
        )

    return retry_source(_fetch, source="新浪行情接口")


def _weekly_fallback_rows(code: str, name: str) -> SourceResult:
    if not WEEKLY_PRICE_CSV.exists():
        return SourceResult(data=pd.DataFrame(), source="fallback_from_weekly", success=False, error_message="无周线缓存文件")

    weekly = pd.read_csv(WEEKLY_PRICE_CSV)
    open_col = f"{name}_open"
    close_col = f"{name}_close"
    if open_col not in weekly.columns or close_col not in weekly.columns:
        return SourceResult(data=pd.DataFrame(), source="fallback_from_weekly", success=False, error_message="周线缓存缺少字段")

    rows = []
    for _, row in weekly.iterrows():
        open_price = row[open_col]
        close_price = row[close_col]
        rows.append(
            {
                "date": row["日期"],
                "open": open_price,
                "high": row.get(f"{name}_high", max(open_price, close_price)),
                "low": row.get(f"{name}_low", min(open_price, close_price)),
                "close": close_price,
                "volume": row.get(f"{name}_volume", 0),
                "amount": row.get(f"{name}_amount", 0),
            }
        )
    return SourceResult(
        data=normalize_daily_frame(pd.DataFrame(rows), source="fallback_from_weekly"),
        source="fallback_from_weekly",
        success=True,
    )


def load_local_daily_cache(code: str, name: str) -> SourceResult:
    cache_path = daily_cache_path(code)
    if cache_path.exists():
        df = pd.read_csv(cache_path)
        if not is_weekly_only_cache(df):
            return SourceResult(data=normalize_daily_frame(df, source="本地日线缓存"), source="本地日线缓存", success=True)

    return SourceResult(data=pd.DataFrame(), source="本地日线缓存", success=False, error_message="无可用本地日线缓存")


def fetch_fallback_from_weekly(code: str, name: str) -> SourceResult:
    return _weekly_fallback_rows(code, name)


def save_daily_cache(code: str, df: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(daily_cache_path(code), index=False, encoding="utf-8-sig")
