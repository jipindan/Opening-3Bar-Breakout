"""回测统计指标计算。

输入为 engine.run 产出的交易明细 DataFrame，输出各项绩效指标。
「无信号时段」不计入胜率统计（单独由 no_signal_count 传入）。
"""

import numpy as np
import pandas as pd

import config


def compute_stats(trades_df, no_signal_count=0):
    """计算绩效指标，返回 dict。"""
    n = len(trades_df)
    if n == 0:
        return {
            "总交易次数": 0,
            "无信号时段数": no_signal_count,
            "胜率(%)": 0.0,
            "盈亏比(实际)": 0.0,
            "总收益率(%)": 0.0,
            "最大回撤(%)": 0.0,
            "夏普比率": 0.0,
            "总盈亏(元)": 0.0,
        }

    pnl = trades_df["pnl"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    win_rate = len(wins) / n * 100

    # 实际盈亏比 = 平均盈利 / 平均亏损绝对值。
    avg_win = wins.mean() if len(wins) else 0.0
    avg_loss = abs(losses.mean()) if len(losses) else 0.0
    profit_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else float("inf")

    total_pnl = pnl.sum()
    total_return = total_pnl / config.INIT_CAPITAL * 100

    # 资金曲线与最大回撤（按交易顺序）。
    equity = config.INIT_CAPITAL + pnl.cumsum()
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_drawdown = abs(drawdown.min()) * 100

    # 夏普比率：按交易日聚合日盈亏 -> 日收益率 -> 年化（252 交易日）。
    daily = trades_df.groupby("trading_date")["pnl"].sum()
    daily_ret = daily / config.INIT_CAPITAL
    if daily_ret.std(ddof=1) > 0 and len(daily_ret) > 1:
        sharpe = daily_ret.mean() / daily_ret.std(ddof=1) * np.sqrt(252)
    else:
        sharpe = 0.0

    return {
        "总交易次数": n,
        "无信号时段数": no_signal_count,
        "胜率(%)": round(win_rate, 2),
        "盈亏比(实际)": round(profit_loss_ratio, 2),
        "总收益率(%)": round(total_return, 2),
        "最大回撤(%)": round(max_drawdown, 2),
        "夏普比率": round(sharpe, 2),
        "总盈亏(元)": round(total_pnl, 2),
    }


def monthly_pnl(trades_df):
    """按月汇总盈亏，返回 Series（index 为 'YYYY-MM'）。"""
    if len(trades_df) == 0:
        return pd.Series(dtype=float)
    dates = pd.to_datetime(trades_df["trading_date"])
    months = dates.dt.to_period("M").astype(str)
    return trades_df.groupby(months)["pnl"].sum()
