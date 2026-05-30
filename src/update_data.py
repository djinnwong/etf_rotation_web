import argparse

from data_fetcher import diagnose_etf_sources, fetch_weekly_prices_with_cache
from strategy_engine import run_strategy
from telegram_push import push_signal


def main() -> None:
    parser = argparse.ArgumentParser(description="更新 ETF 轮动数据")
    parser.add_argument("--diagnose", help="诊断单只 ETF 数据源，例如：--diagnose 518880")
    parser.add_argument(
        "--mode",
        choices=["preclose", "final"],
        default="final",
        help="preclose=14:55盘中预估更新；final=15:03正式收盘更新",
    )
    parser.add_argument("--telegram", action="store_true", help="更新完成后推送 Telegram 提醒")
    args = parser.parse_args()

    if args.diagnose:
        print(f"开始诊断 ETF 数据源: {args.diagnose}")
        diagnosis, selected_source = diagnose_etf_sources(args.diagnose)
        print(diagnosis.to_string(index=False))
        print(f"最终采用数据源: {selected_source}")
        return

    if args.mode == "preclose":
        print("开始 14:55 盘中预估更新：尝试获取各 ETF 最新可用价格。")
    else:
        print("开始 15:03 正式收盘更新：尝试获取各 ETF 周收盘价格。")
    print("网络失败时会自动使用本地缓存 CSV。")
    data_result = fetch_weekly_prices_with_cache(force_refresh=True)
    print(data_result.message)

    print("开始计算三轮动量轮动策略...")
    _, holding_records, win_stats, cumulative_rank, summary = run_strategy(data_result.data)
    print("策略计算完成。")
    print(f"数据来源: {data_result.source}")
    print(f"最新周日期: {summary.latest_signal_date}")
    print(f"目前持仓: {summary.current_holding_name}({summary.current_holding_code})")
    print(f"下周建议持仓: {summary.next_holding_name}({summary.next_holding_code})")
    print("数据源状态:")
    print(data_result.source_status.to_string(index=False))
    print(f"持仓记录数: {len(holding_records)}")
    print("胜率统计:")
    print(win_stats.to_string(index=False))
    print("累计收益率排行榜:")
    print(cumulative_rank.to_string(index=False))

    if args.telegram:
        pushed = push_signal(
            signal_date=summary.latest_signal_date,
            next_holding_name=summary.next_holding_name,
            next_holding_code=summary.next_holding_code,
            data_source=data_result.source,
            mode=args.mode,
        )
        print("Telegram 推送完成。" if pushed else "Telegram 推送未发送。")


if __name__ == "__main__":
    main()
