"""回测引擎（pandas 手写循环，完全离线）。

按「交易时段」遍历：每个时段取开盘前 3 根 K 线判定信号，从第 4 根起逐根
撮合止盈/止损，时段结束仍未触发则按最后一根收盘价强平。

撮合约定（与用户确认）：
  - 固定 1 手；
  - 入场价在第3根收盘价基础上按不利方向加 1 个 tick 滑点；
  - 同一根 K 线内止盈、止损都可能触及时，假设「止损先成交」（保守）；
  - 时段收盘前未触发则强平（纯日内，不留隔夜）。
"""

import pandas as pd

import config
from strategy.three_bar import generate_signal
from strategy import trend as trendmod


def _session_kind(first_bar_time):
    """根据时段第一根 K 线时间判断是夜盘还是日盘。"""
    h = first_bar_time.hour
    return "夜盘" if (h >= 19 or h < 5) else "日盘"


def _simulate_session(bars, symbol_key, multiplier, tick, trend_mode=None, td_map=None):
    """对单个交易时段执行一次开仓尝试。

    返回 (trade_dict_or_None, status)，status ∈ {'traded','no_signal','filtered'}。
    """
    if len(bars) < 4:
        # 不足 3 根判定 + 至少 1 根用于离场，无法交易。
        return None, "no_signal"

    b1, b2, b3 = bars.iloc[0], bars.iloc[1], bars.iloc[2]
    sig = generate_signal(b1, b2, b3, tick)
    if sig is None:
        return None, "no_signal"

    direction = sig["direction"]

    # 趋势过滤：原信号方向必须与「大趋势」一致才开仓。
    if trend_mode is not None:
        if trend_mode == "daily":
            trend_dir = td_map.get(b3["trading_date"]) if td_map else None
        elif trend_mode == "intraday":
            sma = b3.get("sma")
            trend_dir = None if pd.isna(sma) else ("up" if b3["close"] > sma else "down")
        else:
            trend_dir = None
        if not trendmod.aligned(direction, trend_dir):
            return None, "filtered"

    sign = 1 if direction == "long" else -1

    # 滑点：按不利方向施加。做多买价偏高，做空卖价偏低。
    slip = config.SLIPPAGE_TICKS * tick
    entry = sig["entry"] + sign * slip
    stop = sig["stop"]
    # 止盈距离从实际入场价（含滑点）算起，保证 RR 比是实际风险回报比。
    target = entry + sign * abs(entry - stop) * config.RR_RATIO

    entry_time = b3["datetime"]
    exit_price = None
    exit_time = None
    exit_reason = None

    # 从第 4 根开始逐根检查触发。
    follow = bars.iloc[3:]
    for _, bar in follow.iterrows():
        if direction == "long":
            hit_stop = bar["low"] <= stop
            hit_target = bar["high"] >= target
        else:
            hit_stop = bar["high"] >= stop
            hit_target = bar["low"] <= target

        if hit_stop:  # 止损优先（同根都触及时按止损成交）
            exit_price, exit_reason = stop, "stop_loss"
        elif hit_target:
            exit_price, exit_reason = target, "take_profit"

        if exit_price is not None:
            exit_time = bar["datetime"]
            break

    # 时段结束仍未触发 -> 按最后一根收盘价强平。
    if exit_price is None:
        last = bars.iloc[-1]
        exit_price = last["close"]
        exit_time = last["datetime"]
        exit_reason = "forced_close"

    # 盈亏：方向 * 价差 * 乘数 * 手数，再扣开平两次手续费。
    gross = sign * (exit_price - entry) * multiplier * config.LOTS
    commission = (
        (entry + exit_price) * multiplier * config.LOTS * config.COMMISSION_RATE
    )
    pnl = gross - commission

    # 每手风险（按实际滑点后入场价到止损的距离折算，单手口径），供模拟账户定手数。
    per_lot_risk = abs(entry - stop) * multiplier

    trade = {
        "symbol": symbol_key,
        "trading_date": b3["trading_date"],
        "session_kind": _session_kind(b1["datetime"]),
        "direction": direction,
        "entry_time": entry_time,
        "entry_price": round(entry, 4),
        "stop_price": round(stop, 4),
        "exit_time": exit_time,
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "multiplier": multiplier,
        "per_lot_risk": round(per_lot_risk, 2),
        "pnl": round(pnl, 2),
        "return_pct": round(pnl / config.INIT_CAPITAL * 100, 4),
    }
    return trade, "traded"


def run(df, symbol_key, trend_mode=None, trend_n=None):
    """对一个品种的完整 K 线数据回测。

    trend_mode ∈ {None, 'daily', 'intraday'}；None 表示不做趋势过滤（基线）。
    返回 (trades_df, counts)，counts = {'no_signal':, 'filtered':}。
    """
    multiplier = config.CONTRACT_MULTIPLIER[symbol_key]
    tick = config.PRICE_TICK[symbol_key]

    # 预备趋势数据。
    td_map = None
    if trend_mode == "daily":
        td_map = trendmod.daily_trend_map(df, trend_n)
    elif trend_mode == "intraday":
        df = trendmod.add_intraday_sma(df, trend_n)

    trades = []
    counts = {"no_signal": 0, "filtered": 0}

    for _, bars in df.groupby("session_id"):
        bars = bars.reset_index(drop=True)
        trade, status = _simulate_session(
            bars, symbol_key, multiplier, tick, trend_mode, td_map
        )
        if status == "traded":
            trades.append(trade)
        else:
            counts[status] += 1

    trades_df = pd.DataFrame(trades)
    return trades_df, counts
