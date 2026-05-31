"""趋势过滤对比：无过滤 / 日线 / 日内 三套并排，外加 N 值稳健性扫描。

复用 engine.run、account.simulate_account、stats.compute_stats，
对每套配置同时给出「固定1手」与「模拟账户」两个口径的绩效。
"""

import pandas as pd

import config
from data import fetcher
from backtest import engine, account
from report import stats


def _run_config(klines_by_symbol, trend_mode, trend_n):
    """跑一套配置，返回 (固定1手指标, 账户指标, sized_df, 总filtered)。"""
    all_trades = []
    total_filtered = 0
    total_no_signal = 0
    for sym, df in klines_by_symbol.items():
        trades_df, counts = engine.run(df, sym, trend_mode=trend_mode, trend_n=trend_n)
        total_filtered += counts["filtered"]
        total_no_signal += counts["no_signal"]
        if len(trades_df) > 0:
            all_trades.append(trades_df)

    if not all_trades:
        return None, None, None, total_filtered

    combined = pd.concat(all_trades, ignore_index=True)
    combined = combined.sort_values(["trading_date", "entry_time"]).reset_index(drop=True)

    fixed_stats = stats.compute_stats(combined, total_no_signal)
    sized_df, acc_summary = account.simulate_account(combined)
    return fixed_stats, acc_summary, sized_df, total_filtered


def run_all_configs(symbols=None):
    """无过滤 / 日线(默认N) / 日内(默认N) 三套对比。

    返回 (对比表 DataFrame, {配置名 -> sized_df} 供画图)。
    """
    symbols = symbols or list(config.SYMBOLS)
    klines = {s: fetcher.fetch_klines(s) for s in symbols}

    configs = [
        ("无过滤", None, None),
        (f"日线N{config.DAILY_TREND_N}", "daily", config.DAILY_TREND_N),
        (f"日内N{config.INTRADAY_TREND_N}", "intraday", config.INTRADAY_TREND_N),
    ]

    rows = []
    curves = {}
    for name, mode, n in configs:
        fixed_s, acc_s, sized_df, filtered = _run_config(klines, mode, n)
        if fixed_s is None:
            continue
        curves[name] = sized_df
        rows.append({
            "配置": name,
            "[1手]收益%": fixed_s["总收益率(%)"],
            "[1手]回撤%": fixed_s["最大回撤(%)"],
            "[1手]胜率%": fixed_s["胜率(%)"],
            "[1手]笔数": fixed_s["总交易次数"],
            "[账户]收益%": acc_s["总收益率(%)"],
            "[账户]回撤%": acc_s["最大回撤(%)"],
            "[账户]成交": acc_s["成交笔数"],
            "趋势过滤掉": filtered,
        })
    return pd.DataFrame(rows), curves


def robustness(symbols=None):
    """N 值稳健性扫描：日线扫 SWEEP_DAILY、日内扫 SWEEP_INTRADAY。

    只看模拟账户口径的 收益/回撤/成交数，用于判断是否过拟合。
    """
    symbols = symbols or list(config.SYMBOLS)
    klines = {s: fetcher.fetch_klines(s) for s in symbols}

    rows = []
    for mode, sweep in [("daily", config.SWEEP_DAILY), ("intraday", config.SWEEP_INTRADAY)]:
        for n in sweep:
            _, acc_s, _, filtered = _run_config(klines, mode, n)
            if acc_s is None:
                continue
            rows.append({
                "趋势基准": "日线" if mode == "daily" else "日内",
                "N": n,
                "[账户]收益%": acc_s["总收益率(%)"],
                "[账户]回撤%": acc_s["最大回撤(%)"],
                "[账户]成交": acc_s["成交笔数"],
                "过滤掉": filtered,
            })
    return pd.DataFrame(rows)
