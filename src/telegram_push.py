from __future__ import annotations


def build_signal_message(
    signal_date: str,
    next_holding_name: str,
    next_holding_code: str,
    data_source: str,
) -> str:
    return (
        "CY-ETF轮动V1\n"
        f"策略周日期：{signal_date}\n"
        f"下周建议持仓：{next_holding_name}（{next_holding_code}）\n"
        f"数据来源：{data_source}"
    )


def send_telegram_message(message: str) -> bool:
    raise NotImplementedError("Telegram 推送将在下一阶段接入 Bot Token 和 Chat ID。")


def push_1455_signal(signal_date: str, next_holding_name: str, next_holding_code: str, data_source: str) -> bool:
    message = build_signal_message(
        signal_date=signal_date,
        next_holding_name=next_holding_name,
        next_holding_code=next_holding_code,
        data_source=data_source,
    )
    return send_telegram_message(message)
