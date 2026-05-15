import argparse

from data_fetcher import diagnose_etf_sources, fetch_weekly_prices_with_cache
from strategy_engine import run_strategy


def main() -> None:
    parser = argparse.ArgumentParser(description="更新 ETF 轮动数据")
    parser.add_argument("--diagnose", help="诊断单只 ETF 数据源，例如：--diagnose 518880")
    args = parser.parse_args()

    if args.diagnose:
        print(f"开始诊断 ETF 数据源: {args.diagnose}")
        diagnosis, selected_source = diagnose_etf_sources(args.diagnose)
        print(diagnosis.to_string(index=False))
        print(f"最终采用数据源: {selected_source}")
        return

    print("开始更新 ETF 数据。网络失败时会自动使用本地缓存 CSV。")
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


if __name__ == "__main__":
    main()
