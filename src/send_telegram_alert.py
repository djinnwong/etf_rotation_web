from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime
from pathlib import Path
from time import sleep
from urllib import request
import json

from config import ROTATION_RESULT_CSV
from status_manager import CHINA_TZ, MARKET_CLOSE, PRE_CLOSE_START, should_send_weekly_preclose_alert, now_china


def wait_until_preclose_window() -> None:
    now = now_china()
    target_dt = datetime.combine(now.date(), PRE_CLOSE_START, tzinfo=CHINA_TZ)
    close_dt = datetime.combine(now.date(), MARKET_CLOSE, tzinfo=CHINA_TZ)

    if now < target_dt:
        wait_seconds = int((target_dt - now).total_seconds())
        print(f"当前北京时间 {now:%Y-%m-%d %H:%M:%S}，等待到 14:55 后发送 Telegram，等待 {wait_seconds} 秒。")
        sleep(wait_seconds)
        return

    if now >= close_dt:
        print(f"当前北京时间 {now:%Y-%m-%d %H:%M:%S} 已到 15:00 或之后，本次不会发送 Telegram。")


def read_latest_signal(path: Path = ROTATION_RESULT_CSV) -> tuple[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"找不到策略结果文件: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise RuntimeError("策略结果文件为空，无法发送 Telegram。")

    latest = rows[-1]
    signal_date = latest.get("信号出现日期") or latest.get("日期") or "-"
    holding = latest.get("下周应持有") or latest.get("页面展示持仓") or latest.get("本周收盘后冠军") or ""
    holding = holding.strip()
    if not holding:
        raise RuntimeError("策略结果文件缺少下周持仓信号，无法发送 Telegram。")

    return signal_date, holding


def send_telegram_message(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("未配置 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID。")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    req = request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=20) as response:
        body = response.read().decode("utf-8")
        print(f"Telegram API response: {body}")


def main() -> None:
    parser = argparse.ArgumentParser(description="发送每周最后交易日 14:55 Telegram 持仓提醒")
    parser.add_argument("--wait-until-preclose", action="store_true", help="14:55 前启动时等待到 14:55 再发送")
    parser.add_argument("--force", action="store_true", help="仅用于人工测试：忽略交易日和时间窗口")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要发送的内容，不实际调用 Telegram")
    args = parser.parse_args()

    signal_date, holding = read_latest_signal()
    print(f"读取到最新信号: {signal_date} {holding}")

    if args.wait_until_preclose and not args.force:
        wait_until_preclose_window()

    can_send, reason = should_send_weekly_preclose_alert()
    print(f"Telegram 发送判断: {reason}")
    if not can_send and not args.force:
        print("Telegram 推送跳过。")
        return

    if args.force:
        print("已启用 --force，仅用于人工测试。")

    message = f"SB1:{holding}"
    if args.dry_run:
        print(f"Dry run，不实际发送。消息内容: {message}")
        return

    send_telegram_message(message)
    print(f"Telegram 推送完成: {message}")


if __name__ == "__main__":
    main()
