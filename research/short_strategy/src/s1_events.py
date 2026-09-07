"""EXHAUST-S1 universe screen: borrowable, in-play names on a point-in-time basis."""
import os
import pandas as pd

HERE = os.path.dirname(__file__)
D = lambda *a: os.path.join(HERE, "..", *a)

# frozen universe parameters
PRICE_MIN, PRICE_MAX = 1.0, 20.0
GAP_MIN = 0.20          # gap OR intraday run vs prior close
RVOL_MIN = 3.0
DOLLAR_VOL_MIN = 5e6


def build(price_max=PRICE_MAX, gap_min=GAP_MIN):
    inst = pd.read_csv(D("data", "instruments.csv"))
    shortable = set(inst.loc[inst["shortable"], "symbol"])

    df = pd.read_csv(D("data", "daily_panel.csv"), parse_dates=["date"])
    df = df.sort_values(["symbol", "date"])
    g = df.groupby("symbol")
    df["prev_close"] = g["close"].shift(1)
    df["gap"] = df["open"] / df["prev_close"] - 1
    df["run"] = df["high"] / df["prev_close"] - 1        # intraday extension vs prior close
    df["dollar_vol"] = df["close"] * df["volume"]
    df["advol20"] = g["volume"].transform(lambda s: s.shift(1).rolling(20, min_periods=20).mean())
    df["rvol"] = df["volume"] / df["advol20"]

    m = (
        df["symbol"].isin(shortable)
        & df["prev_close"].between(PRICE_MIN, price_max)
        & ((df["gap"] >= gap_min) | (df["run"] >= gap_min))
        & (df["rvol"] >= RVOL_MIN)
        & (df["dollar_vol"] >= DOLLAR_VOL_MIN)
        & (df["date"] >= pd.Timestamp("2024-09-09"))
    )
    return df[m].copy()


if __name__ == "__main__":
    for pmax, gmin, tag in [(20.0, 0.20, "spec $1-20 / 20%"),
                            (1e9, 0.20, "any price / 20%"),
                            (1e9, 0.15, "any price / 15%")]:
        e = build(pmax, gmin)
        print(f"{tag:22s} events={len(e):4d} names={e.symbol.nunique():3d} dates={e.date.nunique():3d}")
    build(1e9, 0.15).to_csv(D("data", "s1_events.csv"), index=False)
