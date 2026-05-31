"""入口：逐品种回测 -> 汇总 -> 出图 -> 打印报告。

用法：
    export TQ_USER=... TQ_PWD=...   # 首次下载数据时需要（之后走本地缓存）
    python main.py
"""

import os

import pandas as pd

import config
from data import fetcher
from backtest import engine, account, compare
from report import stats, plot


def _print_stats(title, s):
    print(f"\n===== {title} =====")
    for k, v in s.items():
        print(f"  {k:<14}: {v}")


def run_symbol(symbol_key):
    """回测单个品种，返回 (trades_df, no_signal_count)。"""
    print(f"\n[{symbol_key}] 加载数据 ...")
    df = fetcher.fetch_klines(symbol_key)
    print(f"[{symbol_key}] K线 {len(df)} 根，时段 {df['session_id'].nunique()} 个，"
          f"区间 {df['datetime'].min()} ~ {df['datetime'].max()}")

    trades_df, counts = engine.run(df, symbol_key)
    s = stats.compute_stats(trades_df, counts["no_signal"])
    _print_stats(f"{symbol_key} 回测结果（基线·无趋势过滤）", s)

    if len(trades_df) > 0:
        plot.plot_all(trades_df, title_suffix=f"_{symbol_key}")
    return trades_df, counts["no_signal"]


def main():
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    all_trades = []
    total_no_signal = 0
    for symbol_key in config.SYMBOLS:
        trades_df, no_signal = run_symbol(symbol_key)
        total_no_signal += no_signal
        if len(trades_df) > 0:
            all_trades.append(trades_df)

    if not all_trades:
        print("\n没有产生任何交易，结束。")
        return

    combined = pd.concat(all_trades, ignore_index=True)
    combined = combined.sort_values(["trading_date", "entry_time"]).reset_index(drop=True)

    # 交易明细落盘。
    trades_path = os.path.join(config.OUTPUT_DIR, "trades.csv")
    combined.to_csv(trades_path, index=False, encoding="utf-8-sig")
    print(f"\n交易明细已保存：{trades_path}")

    # 汇总统计与图（固定 1 手口径）。
    s = stats.compute_stats(combined, total_no_signal)
    _print_stats("全品种汇总（固定1手）", s)
    plot.plot_all(combined, title_suffix="_ALL")

    # ---- 模拟账户：动态仓位管理 ----
    sized_df, acc_summary = account.simulate_account(combined)
    _print_stats(
        f"模拟账户（{config.INIT_CAPITAL/1e4:.0f}万 | 每笔{config.RISK_PCT*100:.0f}%风险 | "
        f"保证金≤{config.MARGIN_CAP*100:.0f}%）",
        acc_summary,
    )
    sized_path = os.path.join(config.OUTPUT_DIR, "account_trades.csv")
    sized_df.to_csv(sized_path, index=False, encoding="utf-8-sig")
    plot.plot_account_equity(sized_df)
    print(f"\n账户明细已保存：{sized_path}")

    # ---- 趋势过滤对比（无过滤 / 日线 / 日内）----
    print("\n" + "=" * 60)
    print("趋势过滤对比（方案C：日线版 vs 日内版）")
    print("=" * 60)
    comp_df, curves = compare.run_all_configs()
    print("\n【三套配置对比】[1手]=固定1手口径  [账户]=模拟账户口径")
    print(comp_df.to_string(index=False))
    plot.plot_equity_compare(curves)

    print("\n【N值稳健性扫描】（模拟账户口径；看回撤是否在一段N内都稳定下降）")
    rob_df = compare.robustness()
    print(rob_df.to_string(index=False))

    comp_df.to_csv(os.path.join(config.OUTPUT_DIR, "trend_compare.csv"),
                   index=False, encoding="utf-8-sig")
    print(f"\n图表与对比表已保存至：{config.OUTPUT_DIR}")


if __name__ == "__main__":
    main()
