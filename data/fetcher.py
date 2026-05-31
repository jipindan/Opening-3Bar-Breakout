"""数据获取与预处理。

职责：用 tqsdk 一次性下载 5 分钟历史 K 线到本地 CSV 缓存，并完成预处理：
  1. tqsdk 返回的 datetime 是纳秒 UTC 时间戳，转换为北京时间；
  2. 标注每根 K 线归属的「交易日」（夜盘归到下一交易日）；
  3. 按时间间隔自动切分「交易时段」（session），用于识别每个开盘。

注意：tqsdk 仅在这里用于下载数据，回测过程完全离线、不连接任何账户。
"""

import os
import datetime as dt

import pandas as pd

import config


# 期货「交易日」的切换点：北京时间 20:00。
# 20:00 之后开始的夜盘，归属到下一个自然日的交易日（与交易所惯例一致）。
NIGHT_SESSION_START_HOUR = 20


def _cache_path(symbol_key):
    return os.path.join(config.CACHE_DIR, f"{symbol_key}_5min.csv")


def _download_from_tqsdk(symbol_key):
    """通过 tqsdk 下载原始 5 分钟 K 线，返回包含北京时间的 DataFrame。"""
    # 延迟导入，避免离线复用缓存时也强制依赖 tqsdk。
    from tqsdk import TqApi, TqAuth

    user, pwd = config.get_credentials()
    symbol = config.SYMBOLS[symbol_key]

    api = TqApi(auth=TqAuth(user, pwd))
    try:
        kl = api.get_kline_serial(
            symbol, config.KLINE_PERIOD_SEC, data_length=config.DATA_LENGTH
        )
        # 拷贝出需要的列，去掉尚未生成的空 K 线。
        df = kl[["datetime", "open", "high", "low", "close", "volume"]].copy()
        df = df.dropna(subset=["close"]).reset_index(drop=True)
    finally:
        api.close()

    # 纳秒 UTC -> 北京时间（去掉时区信息，保留 naive 的北京本地时间，便于后续比较）。
    ts = pd.to_datetime(df["datetime"], unit="ns", utc=True)
    df["datetime"] = ts.dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)
    return df


def _annotate_trading_day_and_session(df):
    """添加 trading_date（交易日）与 session_id（交易时段）两列。"""
    df = df.sort_values("datetime").reset_index(drop=True)

    # 交易日：北京时间 20:00 之后的 K 线归到下一自然日。
    def to_trading_date(t):
        d = t.date()
        if t.hour >= NIGHT_SESSION_START_HOUR:
            d = d + dt.timedelta(days=1)
        return d

    df["trading_date"] = df["datetime"].apply(to_trading_date)

    # 时段切分：相邻 K 线时间差超过阈值即视为新时段开始。
    # 这样无需硬编码 09:00 / 21:00，自动适配「有无夜盘」。
    gap = df["datetime"].diff()
    threshold = pd.Timedelta(minutes=config.SESSION_GAP_MINUTES)
    new_session = gap.isna() | (gap > threshold)
    df["session_id"] = new_session.cumsum()
    return df


def fetch_klines(symbol_key, use_cache=True):
    """获取某品种预处理后的 5 分钟 K 线。

    优先读本地缓存；缓存不存在时联网下载并写入缓存。
    返回列：datetime, open, high, low, close, volume, trading_date, session_id
    """
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = _cache_path(symbol_key)

    if use_cache and os.path.exists(path):
        df = pd.read_csv(path, parse_dates=["datetime"])
        df["trading_date"] = pd.to_datetime(df["trading_date"]).dt.date
    else:
        raw = _download_from_tqsdk(symbol_key)
        df = _annotate_trading_day_and_session(raw)
        df.to_csv(path, index=False)

    # 可选区间裁剪。
    if config.START_DATE is not None:
        start = pd.to_datetime(config.START_DATE).date()
        df = df[df["trading_date"] >= start]
    if config.END_DATE is not None:
        end = pd.to_datetime(config.END_DATE).date()
        df = df[df["trading_date"] <= end]

    return df.reset_index(drop=True)


def refresh_cache(symbol_key):
    """强制重新联网下载并覆盖缓存。"""
    return fetch_klines(symbol_key, use_cache=False)
