# ETF 三轮动量轮动系统：本地网页端展示版

这个项目适合零基础用户在 Windows 电脑上本地运行。网页使用 Streamlit 打开，不需要 Docker、不需要数据库、不需要复杂前端框架。

## 第一部分：项目目录结构

把整个文件夹放到一个固定位置，例如：

```text
C:\etf_rotation_web
├─ requirements.txt
├─ README.md
├─ data
│  ├─ weekly_prices.csv
│  └─ rotation_result.csv
└─ src
   ├─ app.py
   ├─ config.py
   ├─ data_fetcher.py
   ├─ strategy.py
   ├─ update_data.py
   └─ validate_against_excel.py
```

文件作用：

- `requirements.txt`：需要安装的 Python 第三方库。
- `src/config.py`：ETF 代码、策略参数、CSV 路径配置。
- `src/data_fetcher.py`：用 AkShare 下载 ETF 日线数据，并转换成周线开盘价、收盘价。
- `src/strategy.py`：计算 4 周动量、冠军 ETF、每周轮动结果、策略净值、最大回撤。
- `src/update_data.py`：一键更新数据并重新计算策略。
- `src/app.py`：网页端展示系统。
- `src/validate_against_excel.py`：读取你提供的 Excel 第一张表，验证策略口径是否正确。
- `data/weekly_prices.csv`：本地保存的周线价格数据。
- `data/rotation_result.csv`：本地保存的策略结果数据。

## 第二部分：安装全部依赖

### 1. 打开 Windows 命令行

按键盘：

```text
Win + R
```

输入：

```text
cmd
```

回车。

### 2. 进入项目目录

如果项目放在 `C:\etf_rotation_web`，命令是：

```bat
cd /d C:\etf_rotation_web
```

### 3. 建议创建虚拟环境

```bat
python -m venv .venv
```

启用虚拟环境：

```bat
.venv\Scripts\activate
```

如果成功，命令行最前面会出现：

```text
(.venv)
```

### 4. 升级 pip

```bat
python -m pip install --upgrade pip
```

### 5. 安装依赖

```bat
pip install -r requirements.txt
```

如果你想逐个安装，也可以执行：

```bat
pip install pandas==2.2.3 akshare==1.16.38 streamlit==1.40.2 plotly==5.24.1 openpyxl==3.1.5
```

`requirements.txt` 内容：

```text
pandas==2.2.3
akshare==1.16.38
streamlit==1.40.2
plotly==5.24.1
openpyxl==3.1.5
```

## 第三部分：每一个 Python 文件完整代码

### `src/config.py`

```python
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

WEEKLY_PRICE_CSV = DATA_DIR / "weekly_prices.csv"
ROTATION_RESULT_CSV = DATA_DIR / "rotation_result.csv"

ETF_LIST = {
    "518880": "黄金ETF",
    "513100": "纳指ETF",
    "159915": "创业板ETF",
}

START_DATE = "20130701"

# 用户说明里写的是 2025-05-11，但当前 Excel 第一张表实际出现的是 2026-05-11 预估行。
# 为避免误纳入，两个日期都排除。
EXCLUDE_ESTIMATE_DATES = {"2025-05-11", "2026-05-11"}

MOMENTUM_WEEKS = 4
INITIAL_NET_VALUE = 1.0
```

### `src/data_fetcher.py`

```python
from __future__ import annotations

from datetime import date

import akshare as ak
import pandas as pd

from config import DATA_DIR, ETF_LIST, EXCLUDE_ESTIMATE_DATES, START_DATE, WEEKLY_PRICE_CSV


def _normalize_daily_columns(df: pd.DataFrame, symbol: str, name: str) -> pd.DataFrame:
    required_columns = {"日期", "开盘", "收盘"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"{symbol} 缺少必要字段: {missing}; 当前字段: {list(df.columns)}")

    result = df[["日期", "开盘", "收盘"]].copy()
    result["日期"] = pd.to_datetime(result["日期"])
    result = result.sort_values("日期")
    result = result.rename(
        columns={
            "开盘": f"{name}_open",
            "收盘": f"{name}_close",
        }
    )
    return result


def _daily_to_weekly(daily: pd.DataFrame, name: str) -> pd.DataFrame:
    df = daily.copy()
    df["week_period"] = df["日期"].dt.to_period("W-SUN")

    weekly = (
        df.groupby("week_period", as_index=False)
        .agg(
            日期=("日期", "first"),
            **{
                f"{name}_open": (f"{name}_open", "first"),
                f"{name}_close": (f"{name}_close", "last"),
            },
        )
        .drop(columns=["week_period"])
    )
    return weekly


def fetch_one_etf_weekly(symbol: str, name: str, end_date: str | None = None) -> pd.DataFrame:
    if end_date is None:
        end_date = date.today().strftime("%Y%m%d")

    daily = ak.fund_etf_hist_em(
        symbol=symbol,
        period="daily",
        start_date=START_DATE,
        end_date=end_date,
        adjust="",
    )
    daily = _normalize_daily_columns(daily, symbol=symbol, name=name)
    weekly = _daily_to_weekly(daily, name=name)
    return weekly


def fetch_all_weekly_prices() -> pd.DataFrame:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    merged: pd.DataFrame | None = None
    for symbol, name in ETF_LIST.items():
        weekly = fetch_one_etf_weekly(symbol=symbol, name=name)
        if merged is None:
            merged = weekly
        else:
            merged = pd.merge(merged, weekly, on="日期", how="outer")

    if merged is None:
        raise RuntimeError("没有获取到任何 ETF 数据")

    merged = merged.sort_values("日期").reset_index(drop=True)
    merged["日期"] = pd.to_datetime(merged["日期"]).dt.strftime("%Y-%m-%d")
    merged = merged[~merged["日期"].isin(EXCLUDE_ESTIMATE_DATES)]

    price_columns = [col for col in merged.columns if col != "日期"]
    merged = merged.dropna(subset=price_columns)
    merged.to_csv(WEEKLY_PRICE_CSV, index=False, encoding="utf-8-sig")
    return merged


if __name__ == "__main__":
    df = fetch_all_weekly_prices()
    print(f"已保存: {WEEKLY_PRICE_CSV}")
    print(f"数据行数: {len(df)}")
    print(f"最新一周: {df['日期'].iloc[-1]}")
```

### `src/strategy.py`

```python
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
```

### `src/update_data.py`

```python
from data_fetcher import fetch_all_weekly_prices
from strategy import update_rotation_result


def main() -> None:
    print("开始下载 ETF 日线数据，并转换为周线数据...")
    prices = fetch_all_weekly_prices()
    print(f"周线数据已更新，共 {len(prices)} 行。")

    print("开始计算三轮动量轮动策略...")
    result = update_rotation_result()
    latest = result.dropna(subset=["下周应持有"]).iloc[-1]
    print("策略计算完成。")
    print(f"最新周日期: {latest['日期']}")
    print(f"当前应该持有: {latest['下周应持有']}")


if __name__ == "__main__":
    main()
```

### `src/app.py`

```python
from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from config import ETF_LIST, ROTATION_RESULT_CSV, WEEKLY_PRICE_CSV
from data_fetcher import fetch_all_weekly_prices
from strategy import update_rotation_result


st.set_page_config(page_title="ETF 三轮动量轮动系统", layout="wide")


def percent_text(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{value * 100:.2f}%"


@st.cache_data(show_spinner=False)
def load_result() -> pd.DataFrame:
    if not ROTATION_RESULT_CSV.exists():
        fetch_all_weekly_prices()
        result = update_rotation_result()
        return result
    return pd.read_csv(ROTATION_RESULT_CSV)


def refresh_data() -> pd.DataFrame:
    fetch_all_weekly_prices()
    result = update_rotation_result()
    st.cache_data.clear()
    return result


st.title("ETF 三轮动量轮动系统")

with st.sidebar:
    st.header("操作")
    st.write("点击按钮会从 AkShare 下载最新 ETF 数据，并保存到本地 CSV。")
    if st.button("更新数据并重新计算", type="primary"):
        with st.spinner("正在更新数据，请稍等..."):
            df = refresh_data()
        st.success("更新完成")
    else:
        df = load_result()

if df.empty:
    st.error("没有可展示的数据。请先点击左侧按钮更新数据。")
    st.stop()

latest = df.dropna(subset=["下周应持有"]).iloc[-1]
latest_date = latest["日期"]
current_holding = latest["下周应持有"]

st.caption(f"最新更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；最新策略周日期：{latest_date}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("当前应该持有", current_holding)
col2.metric("策略最新净值", f"{latest['策略净值']:.4f}")
col3.metric("当前最大回撤", percent_text(latest["最大回撤"]))
col4.metric("本周实际持有", latest["本周实际持有"] if pd.notna(latest["本周实际持有"]) else "-")

st.subheader("三个 ETF 最近 4 周涨幅")
momentum_rows = []
for name in ETF_LIST.values():
    momentum_rows.append(
        {
            "ETF": name,
            "4周涨幅": latest[f"{name}_4周涨幅"],
            "4周涨幅显示": percent_text(latest[f"{name}_4周涨幅"]),
        }
    )

momentum_df = pd.DataFrame(momentum_rows).sort_values("4周涨幅", ascending=False)
st.dataframe(
    momentum_df[["ETF", "4周涨幅显示"]].rename(columns={"4周涨幅显示": "4周涨幅"}),
    use_container_width=True,
    hide_index=True,
)

fig_bar = px.bar(
    momentum_df,
    x="ETF",
    y="4周涨幅",
    text=momentum_df["4周涨幅"].map(lambda x: f"{x * 100:.2f}%"),
    title="最近 4 周涨幅对比",
)
fig_bar.update_layout(yaxis_tickformat=".2%", height=360)
st.plotly_chart(fig_bar, use_container_width=True)

st.subheader("历史收益曲线")
curve_df = df[["日期", "策略净值"]].copy()
curve_df["日期"] = pd.to_datetime(curve_df["日期"])
fig_line = px.line(curve_df, x="日期", y="策略净值", title="策略净值曲线")
fig_line.update_layout(height=420)
st.plotly_chart(fig_line, use_container_width=True)

st.subheader("每周轮动结果")
display_cols = [
    "日期",
    "本周收盘后冠军",
    "下周应持有",
    "本周实际持有",
    "策略收益",
    "策略净值",
    "最大回撤",
]
display_df = df[display_cols].copy().tail(80).sort_values("日期", ascending=False)
for col in ["策略收益", "最大回撤"]:
    display_df[col] = display_df[col].map(percent_text)
display_df["策略净值"] = display_df["策略净值"].map(lambda x: f"{x:.4f}" if pd.notna(x) else "-")
st.dataframe(display_df, use_container_width=True, hide_index=True)

st.subheader("本地 CSV 文件")
st.write(f"周线价格数据：{WEEKLY_PRICE_CSV}")
st.write(f"策略结果数据：{ROTATION_RESULT_CSV}")
```

### `src/validate_against_excel.py`

```python
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from config import EXCLUDE_ESTIMATE_DATES
from strategy import calculate_rotation


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

    print("Excel 第一张表读取成功。")
    print(f"有效周线行数: {len(prices)}")
    print(f"最新有效周日期: {latest['日期']}")
    print(f"当前应该持有: {latest['下周应持有']}")
    print("最近 5 周结果:")
    cols = ["日期", "本周收盘后冠军", "下周应持有", "本周实际持有", "策略收益", "策略净值"]
    print(result[cols].tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
```

## 第四部分：如何启动项目

### 1. 更新数据并计算策略

在项目目录执行：

```bat
python src\update_data.py
```

正常情况下会看到类似输出：

```text
开始下载 ETF 日线数据，并转换为周线数据...
周线数据已更新，共 xxx 行。
开始计算三轮动量轮动策略...
策略计算完成。
最新周日期: yyyy-mm-dd
当前应该持有: 某某ETF
```

### 2. 启动网页

继续在项目目录执行：

```bat
streamlit run src\app.py
```

命令行会显示一个网址，通常是：

```text
http://localhost:8501
```

### 3. 打开网页

打开 Edge 或 Chrome，在地址栏输入：

```text
http://localhost:8501
```

网页会展示：

- 当前应该持有哪个 ETF
- 三个 ETF 最近 4 周涨幅
- 每周轮动结果
- 历史收益曲线
- 最新更新时间

## 第五部分：如何验证策略是否正确

### 1. 用你提供的 Excel 验证

假设 Excel 在桌面，路径类似：

```text
C:\Users\你的名字\Desktop\三轮轮动策略.xlsx
```

执行：

```bat
python src\validate_against_excel.py C:\Users\你的名字\Desktop\三轮轮动策略.xlsx
```

注意：如果路径里有空格，要加英文双引号：

```bat
python src\validate_against_excel.py "C:\Users\你的名字\Desktop\三轮轮动策略.xlsx"
```

### 2. 本项目已按 Excel 口径校验

你的 Excel 第一张表里，策略口径是：

- 4 周涨幅 = 本周收盘价 / 4 周前收盘价 - 1
- 当周涨幅 = 本周收盘价 / 上周收盘价 - 1
- 本周收盘后选出 4 周涨幅最高 ETF
- 下一周持有这个 ETF
- 策略收益使用“本周实际持有 ETF”的当周涨幅

本地校验结果显示，排除预估行后，最近 5 周可复现 Excel 尾部结果：

```text
2026-04-07  创业板ETF  策略净值 18.467133
2026-04-13  创业板ETF  策略净值 19.610641
2026-04-20  纳指ETF    策略净值 19.632015
2026-04-27  创业板ETF  策略净值 20.167341
2026-05-06  纳指ETF    策略净值 20.806966
```

### 3. 检查本地 CSV

运行后打开：

```text
data\weekly_prices.csv
data\rotation_result.csv
```

重点看：

- `weekly_prices.csv` 是否有三个 ETF 的周开盘价和周收盘价。
- `rotation_result.csv` 是否有 `本周收盘后冠军`、`下周应持有`、`策略净值`。
- 预估日期 `2025-05-11` 和 `2026-05-11` 是否没有进入正式结果。

## 第六部分：后续扩展方向

### 1. 14:55 自动计算

用途：在收盘前做预估提醒。

实现方式：

- Windows 使用“任务计划程序”。
- 每个交易日 14:55 执行：

```bat
cd /d C:\etf_rotation_web
.venv\Scripts\python.exe src\update_data.py
```

注意：14:55 数据不是正式收盘数据，只能标记为“盘中预估”。

### 2. 15:03 正式收盘更新

用途：A 股 15:00 收盘后，稍等几分钟让数据源更新。

任务计划程序设置为 15:03 执行：

```bat
cd /d C:\etf_rotation_web
.venv\Scripts\python.exe src\update_data.py
```

后续可以把结果写入：

```text
data\official_signal.csv
```

并在网页上区分：

- 14:55：盘中预估
- 15:03：正式收盘信号

### 3. Telegram 推送

需要新增：

- Telegram Bot Token
- Chat ID
- 一个 `src\notify_telegram.py`

推送内容建议：

```text
ETF 三轮动量轮动系统
最新策略周日期：yyyy-mm-dd
当前应该持有：纳指ETF
黄金ETF 4周涨幅：xx%
纳指ETF 4周涨幅：xx%
创业板ETF 4周涨幅：xx%
```

### 4. 自动判断节假日和周四收盘情况

中国市场有节假日，周线不能简单假设每周五都有交易。

当前代码已经按“自然周内实际交易日”聚合：

- 周开盘价 = 这一周第一个交易日开盘价
- 周收盘价 = 这一周最后一个交易日收盘价

后续进一步增强：

- 用 `akshare.tool_trade_date_hist_sina()` 获取 A 股交易日历。
- 判断今天是不是交易日。
- 判断本周最后一个交易日是否已经结束。
- 遇到周四是本周最后交易日时，自动把周四收盘作为本周正式收盘。
- 遇到长假前最后交易日，提前生成正式信号。

## 重要说明

这个版本是第一阶段：本地网页端展示版。

它不会自动下单，不会连接券商账户，也不会保证收益。它只负责：

- 获取 ETF 数据
- 计算三轮动量轮动信号
- 本地保存 CSV
- 在浏览器展示结果

