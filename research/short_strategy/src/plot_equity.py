"""Equity and drawdown for the Bounce-Fade short, at 1 unit gross exposure per signal day."""
import os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

sys.path.insert(0, os.path.dirname(__file__))
import backtest as bt
from features import IS_END
from strategy import signals, PARAMS

HERE = os.path.dirname(__file__)
D = lambda *a: os.path.join(HERE, "..", *a)

SURFACE, INK, INK2, SERIES = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6"
GRID, LOSS = "#e4e3df", "#e34948"


def main():
    panel = pd.read_pickle(D("data", "panel_feat.pkl"))
    intr = pd.read_parquet(D("data", "intraday_clean.parquet"))
    susp = pd.read_csv(D("data", "suspect_sessions.csv"), parse_dates=["date"])
    ev = signals(panel, set(intr["symbol"].unique()), set(zip(susp["symbol"], susp["date"])))
    tr = bt.backtest(ev, bt.bars_index(intr), rule=PARAMS["rule"],
                     stop_pct=PARAMS["stop_pct"], costs=bt.Costs(5.0, 2.0))

    cal = pd.Index(sorted(d for d in intr["date"].unique()
                          if d >= pd.Timestamp("2024-09-03")))
    daily = pd.Series(0.0, index=cal)
    daily.loc[tr.groupby("date").ret.mean().index] = tr.groupby("date").ret.mean().values
    eq = (1 + daily).cumprod()
    dd = eq / eq.cummax() - 1

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(10, 6.2), sharex=True,
                                  gridspec_kw={"height_ratios": [3, 1], "hspace": 0.12})
    fig.patch.set_facecolor(SURFACE)
    for a in (ax, ax2):
        a.set_facecolor(SURFACE)
        a.grid(True, color=GRID, lw=0.8)
        a.set_axisbelow(True)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            a.spines[s].set_color(GRID)
        a.tick_params(colors=INK2, labelsize=9)

    ax.plot(eq.index, (eq - 1) * 100, color=SERIES, lw=2)
    ax.axhline(0, color=INK2, lw=1)
    ax.axvline(IS_END, color=INK2, lw=1.2, ls="--")
    ax.annotate("in-sample  |  out-of-sample", xy=(IS_END, ax.get_ylim()[1]),
                xytext=(6, -12), textcoords="offset points", color=INK2, fontsize=9)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:.0f}%"))
    ax.set_title("Bounce-Fade short — cumulative return at 1 unit gross per signal day",
                 color=INK, fontsize=12, loc="left", pad=10)
    ax.text(0.0, 1.0, "", transform=ax.transAxes)
    fin = (eq.iloc[-1] - 1) * 100
    ax.annotate(f"{fin:+.0f}%", xy=(eq.index[-1], fin), xytext=(8, -4),
                textcoords="offset points", color=SERIES, fontsize=11, fontweight="bold")

    ax2.fill_between(dd.index, dd * 100, 0, color=LOSS, alpha=0.25, lw=0)
    ax2.plot(dd.index, dd * 100, color=LOSS, lw=1.2)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:.0f}%"))
    ax2.set_ylabel("drawdown", color=INK2, fontsize=9)
    ax2.annotate(f"max {dd.min()*100:.0f}%", xy=(dd.idxmin(), dd.min() * 100),
                 xytext=(6, 6), textcoords="offset points", color=LOSS, fontsize=9)

    fig.text(0.5, 0.015, "738 trades / 192 signal days over 2024-09 to 2026-09. "
             "Costs 14 bps round trip. Equal weight across each day's signals.",
             ha="center", color=INK2, fontsize=8.5)
    fig.savefig(D("out", "equity_curve.png"), dpi=160, bbox_inches="tight",
                facecolor=SURFACE)
    print("wrote out/equity_curve.png  final", f"{fin:+.1f}%", "maxDD", f"{dd.min():.1%}")

if __name__ == "__main__":
    main()
