"""开盘三K线趋势突破——核心信号逻辑。

纯函数、无 IO，便于单元测试与复用。

规则：
  - 看某交易时段开盘后前 3 根 5 分钟 K 线的收盘价。
  - 连续递增 (close1 < close2 < close3) -> 做多；
    连续递减 (close1 > close2 > close3) -> 做空；
    否则 -> 无信号。
  - 入场价 = 第 3 根 K 线收盘价（滑点在撮合阶段施加）。
  - 止损：做多 = 第3根最低点 - 1个tick；做空 = 第3根最高点 + 1个tick。
  - 止盈：止盈距离 = 止损距离 × RR_RATIO（盈亏比 1:RR_RATIO，默认2.5）。
"""

import config


def generate_signal(bar1, bar2, bar3, price_tick, rr_ratio=None):
    """根据开盘前 3 根 K 线生成信号。

    参数 bar1/bar2/bar3 为可按字段访问的对象（pandas Series 或 dict-like），
    需包含 high / low / close 字段。
    rr_ratio：止盈/止损距离比，默认读 config.RR_RATIO。

    返回 dict(direction, entry, stop, target)；无信号时返回 None。
    """
    if rr_ratio is None:
        rr_ratio = config.RR_RATIO

    c1, c2, c3 = bar1["close"], bar2["close"], bar3["close"]

    if c1 < c2 < c3:
        direction = "long"
    elif c1 > c2 > c3:
        direction = "short"
    else:
        return None  # 方向不一致，当前时段不开仓

    entry = c3  # 第 3 根收盘价入场

    if direction == "long":
        stop = bar3["low"] - price_tick
        target = entry + (entry - stop) * rr_ratio
    else:  # short
        stop = bar3["high"] + price_tick
        target = entry - (stop - entry) * rr_ratio

    return {
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
    }
