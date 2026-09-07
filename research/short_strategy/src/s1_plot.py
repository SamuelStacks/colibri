"""Why EXHAUST-S1 loses: no directional edge, and stop slippage scales with illiquidity."""
import os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

HERE = os.path.dirname(__file__); D = lambda *a: os.path.join(HERE, "..", *a)
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
LOSS, NEUTRAL, SERIES = "#e34948", "#8a8984", "#2a78d6"


def main():
    tr = pd.read_csv(D("out", "s1_allsessions_trades.csv"), parse_dates=["date"])
    d = pd.read_csv(D("data", "daily_panel.csv"), parse_dates=["date"])
    d["dv"] = d["close"] * d["volume"]
    tr = tr.merge(d[["symbol", "date", "dv"]], on=["symbol", "date"], how="left")
    labels = ["<$20M", "$20-50M", "$50-200M", "$200M-1B", ">$1B"]
    tr["b"] = pd.cut(tr["dv"], [0, 2e7, 5e7, 2e8, 1e9, 1e13], labels=labels)
    g = tr.groupby("b", observed=True).agg(exp=("R_multiple", "mean"), n=("R_multiple", "size"))

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.4))
    fig.patch.set_facecolor(SURFACE)
    for a in (ax, ax2):
        a.set_facecolor(SURFACE); a.set_axisbelow(True)
        a.grid(True, color=GRID, lw=0.8)
        for s in ("top", "right"): a.spines[s].set_visible(False)
        for s in ("left", "bottom"): a.spines[s].set_color(GRID)
        a.tick_params(colors=INK2, labelsize=9)

    y = np.arange(len(g))
    ax.barh(y, g["exp"], color=LOSS, height=0.62)
    ax.set_yticks(y); ax.set_yticklabels(g.index, fontsize=9.5)
    ax.axvline(0, color=INK, lw=1.2)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:.1f}R"))
    # labels sit in the empty space right of zero, clear of the category axis
    for i, (e, n) in enumerate(zip(g["exp"], g["n"])):
        ax.annotate(f"{e:+.2f}R  (n={n:,})", xy=(0, i), xytext=(8, 0),
                    textcoords="offset points", ha="left", va="center",
                    color=INK, fontsize=9)
    ax.set_xlim(g["exp"].min() * 1.08, abs(g["exp"].min()) * 0.42)
    ax.set_title("Expectancy by liquidity — negative in every bucket",
                 color=INK, fontsize=11.5, loc="left", pad=8)
    ax.set_xlabel("expectancy per trade", color=INK2, fontsize=9)

    bins = np.linspace(0, 6, 40)
    ax2.hist(tr["mfe_R"].clip(0, 6), bins=bins, color=SERIES, alpha=0.55, label="favourable (MFE)")
    ax2.hist(tr["mae_R"].clip(0, 6), bins=bins, color=LOSS, alpha=0.55, label="adverse (MAE)")
    ax2.axvline(tr["mfe_R"].median(), color=SERIES, lw=2)
    ax2.axvline(tr["mae_R"].median(), color=LOSS, lw=2, ls="--")
    ax2.set_title("Excursions after entry are symmetric — no directional edge",
                  color=INK, fontsize=11.5, loc="left", pad=8)
    ax2.set_xlabel("R from entry", color=INK2, fontsize=9)
    ax2.legend(frameon=False, fontsize=9, labelcolor=INK2)
    ax2.annotate(f"median {tr['mfe_R'].median():.2f}R vs {tr['mae_R'].median():.2f}R",
                 xy=(0.97, 0.72), xycoords="axes fraction", ha="right",
                 color=INK, fontsize=9.5)

    fig.text(0.5, -0.02, "EXHAUST-S1, frozen parameters, 2,770 trades / 475 sessions / 200 borrowable names, "
             "Sep 2024 \u2013 Sep 2026. Costs: \\$0.01 slippage per fill + \\$0.005/share/side.",
             ha="center", color=INK2, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(D("out", "s1_diagnosis.png"), dpi=160, bbox_inches="tight", facecolor=SURFACE)
    print("wrote out/s1_diagnosis.png")


if __name__ == "__main__":
    main()
