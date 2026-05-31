"""可视化：资金曲线、每笔盈亏直方图、月度收益柱状图。"""

import os

import matplotlib
matplotlib.use("Agg")  # 无界面后端，直接存图
import matplotlib.pyplot as plt

import config
from report.stats import monthly_pnl

# macOS 中文字体，避免标题/标签显示为方框。
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "Heiti TC"]
plt.rcParams["axes.unicode_minus"] = False


def _save(fig, name):
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    path = os.path.join(config.OUTPUT_DIR, name)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_equity_curve(trades_df, title_suffix=""):
    """资金曲线（初始资金 + 累计盈亏，按交易顺序）。"""
    fig, ax = plt.subplots(figsize=(10, 5))
    equity = config.INIT_CAPITAL + trades_df["pnl"].cumsum()
    ax.plot(range(1, len(equity) + 1), equity.values, color="#1f77b4")
    ax.axhline(config.INIT_CAPITAL, color="gray", ls="--", lw=1, label="初始资金")
    ax.set_title(f"资金曲线 {title_suffix}")
    ax.set_xlabel("交易笔数")
    ax.set_ylabel("账户权益(元)")
    ax.legend()
    ax.grid(alpha=0.3)
    return _save(fig, f"equity_curve{title_suffix}.png")


def plot_pnl_hist(trades_df, title_suffix=""):
    """每笔交易盈亏分布直方图。"""
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(trades_df["pnl"], bins=30, color="#ff7f0e", edgecolor="black", alpha=0.8)
    ax.axvline(0, color="gray", ls="--", lw=1)
    ax.set_title(f"每笔交易盈亏分布 {title_suffix}")
    ax.set_xlabel("单笔盈亏(元)")
    ax.set_ylabel("频次")
    ax.grid(alpha=0.3)
    return _save(fig, f"pnl_hist{title_suffix}.png")


def plot_monthly_bar(trades_df, title_suffix=""):
    """月度收益柱状图。"""
    m = monthly_pnl(trades_df)
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["#2ca02c" if v >= 0 else "#d62728" for v in m.values]
    ax.bar(m.index.astype(str), m.values, color=colors)
    ax.axhline(0, color="gray", lw=1)
    ax.set_title(f"月度盈亏 {title_suffix}")
    ax.set_xlabel("月份")
    ax.set_ylabel("盈亏(元)")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(alpha=0.3, axis="y")
    return _save(fig, f"monthly_pnl{title_suffix}.png")


def plot_account_equity(sized_df, name="account"):
    """模拟账户权益曲线（按平仓时间，缩放后盈亏累加）。"""
    taken = sized_df[~sized_df["skipped"]].sort_values("exit_time")
    if len(taken) == 0:
        return None
    equity = config.INIT_CAPITAL + taken["scaled_pnl"].cumsum()
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(taken["exit_time"].values, equity.values, color="#1f77b4")
    ax.axhline(config.INIT_CAPITAL, color="gray", ls="--", lw=1, label="初始资金")
    ax.set_title("模拟账户权益曲线（每笔1%风险，保证金≤50%）")
    ax.set_xlabel("时间")
    ax.set_ylabel("账户权益(元)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    return _save(fig, f"{name}_equity.png")


def plot_equity_compare(curves, name="equity_compare"):
    """把多套配置的模拟账户权益曲线叠在一张图，直观比回撤。

    curves: dict[配置名 -> sized_df]
    """
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for label, sized_df in curves.items():
        taken = sized_df[~sized_df["skipped"]].sort_values("exit_time")
        if len(taken) == 0:
            continue
        equity = config.INIT_CAPITAL + taken["scaled_pnl"].cumsum()
        ax.plot(taken["exit_time"].values, equity.values, label=label, lw=1.5)
    ax.axhline(config.INIT_CAPITAL, color="gray", ls="--", lw=1)
    ax.set_title("趋势过滤对比：模拟账户权益曲线")
    ax.set_xlabel("时间")
    ax.set_ylabel("账户权益(元)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    return _save(fig, f"{name}.png")


def plot_all(trades_df, title_suffix=""):
    """一次生成三张图，返回路径列表。"""
    if len(trades_df) == 0:
        return []
    return [
        plot_equity_curve(trades_df, title_suffix),
        plot_pnl_hist(trades_df, title_suffix),
        plot_monthly_bar(trades_df, title_suffix),
    ]
