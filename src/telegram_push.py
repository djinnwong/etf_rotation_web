from __future__ import annotations

import os

import requests


TELEGRAM_API_BASE = "https://api.telegram.org"


def build_signal_message(
    signal_date: str,
    next_holding_name: str,
    next_holding_code: str,
    data_source: str,
    mode: str = "preclose",
) -> str:
    return f"SB1:{next_holding_name}"


def send_telegram_message(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("未配置 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，跳过 Telegram 推送。")
        return False

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    response.raise_for_status()
    return True


def push_signal(
    signal_date: str,
    next_holding_name: str,
    next_holding_code: str,
    data_source: str,
    mode: str = "preclose",
) -> bool:
    message = build_signal_message(
        signal_date=signal_date,
        next_holding_name=next_holding_name,
        next_holding_code=next_holding_code,
        data_source=data_source,
        mode=mode,
    )
    return send_telegram_message(message)


def push_1455_signal(signal_date: str, next_holding_name: str, next_holding_code: str, data_source: str) -> bool:
    return push_signal(
        signal_date=signal_date,
        next_holding_name=next_holding_name,
        next_holding_code=next_holding_code,
        data_source=data_source,
        mode="preclose",
    )
