"""趋势过滤——判断「大趋势」方向，用于过滤逆势的开盘突破信号。

纯函数、无 IO。提供两种趋势基准：
  - 日线版 daily_trend_map：把5分钟聚成日线，按 N 日均线定涨跌（慢、看几周大方向）。
  - 日内版 add_intraday_sma：在5分钟序列挂一根长均线，按 close 与均线位置定涨跌（快）。

防未来函数：
  - 日线版用 shift(1)，交易日 D 只用 ≤ D-1 的日线（夜盘/日盘开盘都在 D-1 日盘收盘后）。
  - 日内版用截至当前 bar（含）的 rolling SMA，均为信号触发时已知的值。
"""

import pandas as pd


def daily_trend_map(df, n):
    """返回 {trading_date -> 'up' | 'down' | None}。

    'up'：前一交易日收盘 > 前一交易日 N 日均线（涨势，只允许做多）。
    'down'：前一交易日收盘 < 均线（跌势，只允许做空）。
    None：历史不足 N 日，无趋势判断（保守起见不开仓）。
    """
    # 聚日线：每个交易日的 close = 当日最后一根 5 分钟 close。
    daily_close = df.groupby("trading_date")["close"].last().sort_index()
    sma = daily_close.rolling(n).mean()

    # shift(1)：交易日 D 用 D-1 的 close 与 sma，杜绝未来函数。
    prev_close = daily_close.shift(1)
    prev_sma = sma.shift(1)

    trend = {}
    for d in daily_close.index:
        c, m = prev_close.get(d), prev_sma.get(d)
        if pd.isna(c) or pd.isna(m):
            trend[d] = None
        else:
            trend[d] = "up" if c > m else "down"
    return trend


def add_intraday_sma(df, n):
    """在 5 分钟 close 上加一列 N 根 SMA（rolling），返回副本。

    信号在第 3 根收盘时触发，届时该 bar 的 sma 已可计算（不含未来）。
    """
    out = df.copy()
    out["sma"] = out["close"].rolling(n).mean()
    return out


def aligned(direction, trend_dir):
    """信号方向与趋势方向是否一致。

    做多需趋势 'up'，做空需趋势 'down'；趋势为 None 一律不通过。
    """
    if trend_dir is None:
        return False
    if direction == "long":
        return trend_dir == "up"
    if direction == "short":
        return trend_dir == "down"
    return False
