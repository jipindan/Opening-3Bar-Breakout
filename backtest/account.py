"""模拟账户：在 1 手回测明细基础上做真实的资金/仓位管理。

与普通回测的区别：
  - 跟踪真实滚动权益（已实现盈亏累加，决定后续每笔的下注规模）；
  - 每笔按「账户净值 × RISK_PCT ÷ 单手止损金额」反推手数，向下取整，不足 1 手则跳过；
  - 同时持仓占用保证金 ≤ 账户净值 × MARGIN_CAP，超限则削减手数、削到 0 就跳过。

事件驱动：候选交易按入场时间排序逐笔处理；处理每笔前先把此刻之前
应平仓的持仓结算入权益、释放保证金，确保定手数时用的是当时的真实净值。
"""

import math

import pandas as pd

import config


def _per_lot_margin(entry_price, multiplier):
    """单手保证金估算 = 合约价值 × 保证金率。"""
    return entry_price * multiplier * config.MARGIN_RATE


def simulate_account(trades_df, risk_pct=None, margin_cap=None, init_capital=None):
    """对所有品种的 1 手候选交易做账户级模拟。

    入参 trades_df 需含：symbol, entry_time, exit_time, entry_price, multiplier,
    per_lot_risk, pnl(单手净盈亏)。

    返回 (sized_df, summary)：
      sized_df —— 每笔的下注手数、缩放后盈亏、下注后权益；含被跳过的笔（lots=0）。
      summary  —— 账户级绩效字典。
    """
    risk_pct = config.RISK_PCT if risk_pct is None else risk_pct
    margin_cap = config.MARGIN_CAP if margin_cap is None else margin_cap
    init_capital = config.INIT_CAPITAL if init_capital is None else init_capital

    df = trades_df.copy()
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df = df.sort_values("entry_time").reset_index(drop=True)

    equity = init_capital             # 已实现权益（现金口径）
    used_margin = 0.0                 # 当前占用保证金
    open_positions = []               # [{exit_time, scaled_pnl, margin}]
    equity_points = []                # [(time, equity)] 用于回撤/曲线
    records = []

    def settle_before(t):
        """结算所有 exit_time <= t 的持仓（按平仓时间顺序）。"""
        nonlocal equity, used_margin, open_positions
        due = [p for p in open_positions if p["exit_time"] <= t]
        for p in sorted(due, key=lambda x: x["exit_time"]):
            equity += p["scaled_pnl"]
            used_margin -= p["margin"]
            equity_points.append((p["exit_time"], equity))
        open_positions = [p for p in open_positions if p["exit_time"] > t]

    for _, tr in df.iterrows():
        # 1) 先结算此刻之前已平仓的持仓。
        settle_before(tr["entry_time"])

        per_lot_risk = tr["per_lot_risk"]
        per_lot_margin = _per_lot_margin(tr["entry_price"], tr["multiplier"])

        # 2) 按风险预算定手数。
        risk_budget = equity * risk_pct
        lots_by_risk = int(math.floor(risk_budget / per_lot_risk)) if per_lot_risk > 0 else 0

        # 3) 按保证金余额封顶。
        margin_room = equity * margin_cap - used_margin
        lots_by_margin = int(math.floor(margin_room / per_lot_margin)) if per_lot_margin > 0 else 0

        lots = max(0, min(lots_by_risk, lots_by_margin))

        scaled_pnl = tr["pnl"] * lots  # 单手 pnl 含手续费，按手数线性缩放
        if lots >= 1:
            margin = lots * per_lot_margin
            used_margin += margin
            open_positions.append({
                "exit_time": tr["exit_time"],
                "scaled_pnl": scaled_pnl,
                "margin": margin,
            })

        records.append({
            "symbol": tr["symbol"],
            "entry_time": tr["entry_time"],
            "exit_time": tr["exit_time"],
            "direction": tr["direction"],
            "lots": lots,
            "per_lot_risk": round(per_lot_risk, 2),
            "risk_pct_used": round(lots * per_lot_risk / equity * 100, 3) if lots else 0.0,
            "scaled_pnl": round(scaled_pnl, 2),
            "equity_after_entry": round(equity, 2),  # 下注时的权益（参考）
            "exit_reason": tr["exit_reason"],
            "skipped": lots == 0,
        })

    # 收尾：结算所有剩余持仓。
    settle_before(pd.Timestamp.max)

    sized_df = pd.DataFrame(records)
    summary = _summarize(sized_df, equity_points, equity, init_capital)
    return sized_df, summary


def _summarize(sized_df, equity_points, final_equity, init_capital=None):
    taken = sized_df[~sized_df["skipped"]]
    n_taken = len(taken)
    n_skipped = int(sized_df["skipped"].sum())

    # 权益曲线（按平仓时间）→ 最大回撤。
    cap = init_capital if init_capital is not None else config.INIT_CAPITAL

    if equity_points:
        eq = pd.Series(
            [cap] + [v for _, v in sorted(equity_points, key=lambda x: x[0])]
        )
        running_max = eq.cummax()
        max_dd = abs(((eq - running_max) / running_max).min()) * 100
    else:
        max_dd = 0.0

    total_return = (final_equity - cap) / cap * 100

    wins = (taken["scaled_pnl"] > 0).sum()
    win_rate = wins / n_taken * 100 if n_taken else 0.0

    return {
        "初始资金(元)": cap,
        "期末权益(元)": round(final_equity, 2),
        "总收益率(%)": round(total_return, 2),
        "最大回撤(%)": round(max_dd, 2),
        "成交笔数": n_taken,
        "跳过笔数(手数不足)": n_skipped,
        "胜率(%)": round(win_rate, 2),
        "平均下注手数": round(taken["lots"].mean(), 2) if n_taken else 0.0,
        "最大下注手数": int(taken["lots"].max()) if n_taken else 0,
        "平均每笔风险占比(%)": round(taken["risk_pct_used"].mean(), 3) if n_taken else 0.0,
        "最差单笔(元)": round(taken["scaled_pnl"].min(), 2) if n_taken else 0.0,
    }
