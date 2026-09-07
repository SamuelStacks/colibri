"""Point-in-time feature construction for the daily panel.

Every feature used by the strategy is computable BEFORE the 09:30 entry:
prior-session data is lagged by one bar; only `open` comes from the entry day.
"""
import os
import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "daily_panel.csv")

# Sample split: design on IS, confirm on OOS. OOS is never inspected during design.
IS_END = pd.Timestamp("2025-09-30")


def load_panel(path=DATA):
    # the committed copy is gzipped; the ingest step writes the plain CSV
    if not os.path.exists(path) and os.path.exists(path + ".gz"):
        path = path + ".gz"
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    return df


def build(df):
    g = df.groupby("symbol", sort=False)

    # ---- strictly prior-session quantities (shifted) ----
    df["prev_close"] = g["close"].shift(1)
    df["prev_high"] = g["high"].shift(1)
    df["prev_low"] = g["low"].shift(1)
    df["prev_open"] = g["open"].shift(1)

    # True range / ATR14 on prior sessions only
    pc = df["prev_close"]
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - pc).abs(),
        (df["low"] - pc).abs(),
    ], axis=1).max(axis=1)
    df["tr"] = tr
    df["atr14"] = g["tr"].transform(lambda s: s.shift(1).rolling(14, min_periods=14).mean())
    df["atr_pct"] = df["atr14"] / df["prev_close"]

    # Trend / extension, prior sessions only
    df["sma20"] = g["close"].transform(lambda s: s.shift(1).rolling(20, min_periods=20).mean())
    df["sma50"] = g["close"].transform(lambda s: s.shift(1).rolling(50, min_periods=50).mean())
    df["ext_sma20"] = df["prev_close"] / df["sma20"] - 1

    # Prior run-up: how much the name has already moved into the gap
    df["run5"] = df["prev_close"] / g["close"].transform(lambda s: s.shift(6)) - 1
    df["run10"] = df["prev_close"] / g["close"].transform(lambda s: s.shift(11)) - 1

    # Liquidity, prior sessions only
    df["dollar_vol"] = df["close"] * df["volume"]
    df["adv20"] = g["dollar_vol"].transform(lambda s: s.shift(1).rolling(20, min_periods=20).median())

    # 52-week-ish high proximity (prior sessions)
    df["hh250"] = g["high"].transform(lambda s: s.shift(1).rolling(250, min_periods=60).max())
    df["near_high"] = df["prev_close"] / df["hh250"] - 1

    # ---- entry-day quantities ----
    df["gap"] = df["open"] / df["prev_close"] - 1
    df["gap_atr"] = (df["open"] - df["prev_close"]) / df["atr14"]

    # Outcomes, all intraday RTH (open -> close, never held overnight)
    df["o2c"] = df["close"] / df["open"] - 1          # long convention
    df["hi_from_open"] = df["high"] / df["open"] - 1   # adverse excursion for a short
    df["lo_from_open"] = df["low"] / df["open"] - 1    # favourable excursion for a short
    return df


def universe_mask(df, min_price=5.0, min_adv=25e6):
    """Point-in-time tradability: priced and liquid enough to borrow and short with size."""
    return (df["prev_close"] >= min_price) & (df["adv20"] >= min_adv) & df["atr14"].notna()
