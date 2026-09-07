"""Final backtest: trade blotter, day-level portfolio, and honest inference."""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import backtest as bt
from features import IS_END
from strategy import signals, PARAMS

HERE = os.path.dirname(__file__)
D = lambda *a: os.path.join(HERE, "..", *a)
ANN = 252


def day_stats(daily, calendar_days, label):
    """daily: Series of per-day portfolio returns on ACTIVE days only."""
    full = pd.Series(0.0, index=calendar_days)
    full.loc[daily.index] = daily.values
    sh = full.mean() / full.std(ddof=1) * np.sqrt(ANN) if full.std(ddof=1) > 0 else np.nan
    eq = (1 + full).cumprod()
    dd = (eq / eq.cummax() - 1)
    yrs = len(full) / ANN
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 else np.nan
    return dict(period=label, active_days=len(daily), calendar_days=len(full),
                bps_per_active_day=daily.mean() * 1e4, ann_sharpe=sh, cagr=cagr,
                total_return=eq.iloc[-1] - 1, max_dd=dd.min(),
                pos_day_rate=(daily > 0).mean(), eq=eq)


def boot_days(daily, n=20000, seed=11):
    rng = np.random.default_rng(seed)
    v = daily.values
    idx = rng.integers(0, len(v), size=(n, len(v)))
    means = v[idx].mean(axis=1) * 1e4
    return means


def main():
    panel = pd.read_pickle(D("data", "panel_feat.pkl"))
    intr = pd.read_parquet(D("data", "intraday_clean.parquet"))
    susp = pd.read_csv(D("data", "suspect_sessions.csv"), parse_dates=["date"])
    susp = set(zip(susp["symbol"], susp["date"]))

    ev = signals(panel, set(intr["symbol"].unique()), susp)
    bars = bt.bars_index(intr)
    costs = bt.Costs(slip_bps=5.0, commission_bps=2.0)

    tr = bt.backtest(ev, bars, rule=PARAMS["rule"], stop_pct=PARAMS["stop_pct"],
                     target_pct=PARAMS["target_pct"], costs=costs)
    tr["period"] = np.where(pd.to_datetime(tr["date"]) <= IS_END, "IS", "OOS")
    tr.to_csv(D("out", "trades.csv"), index=False)

    cal = pd.Index(sorted(d for d in intr["date"].unique()
                          if d >= pd.Timestamp("2024-09-03")))
    print(f"signals={len(ev)}  trades taken={len(tr)}  "
          f"(no entry triggered on {len(ev)-len(tr)} signal days)\n")

    print("=" * 78)
    print("TRADE-LEVEL")
    print("=" * 78)
    rows = [bt.stats(tr[tr.period == p], p) for p in ("IS", "OOS")] + [bt.stats(tr, "ALL")]
    print(pd.DataFrame(rows)[["label", "n", "ev_bps", "med_bps", "win", "pf", "worst", "best"]]
          .round(3).to_string(index=False))
    print("\nexit mix:")
    print((tr.groupby(["period", "reason"]).size() /
           tr.groupby("period").size()).unstack().round(3).to_string())

    print("\n" + "=" * 78)
    print("DAY-LEVEL PORTFOLIO  (equal weight across that day's signals, 1 unit gross/day)")
    print("=" * 78)
    out, curves = [], {}
    for p in ("IS", "OOS", "ALL"):
        t = tr if p == "ALL" else tr[tr.period == p]
        c = cal[cal <= IS_END] if p == "IS" else (cal[cal > IS_END] if p == "OOS" else cal)
        daily = t.groupby("date").ret.mean()
        s = day_stats(daily, c, p)
        curves[p] = s.pop("eq")
        b = boot_days(daily)
        s["boot_p_positive"] = (b > 0).mean()
        s["boot_ci5"] = np.percentile(b, 5)
        s["boot_ci95"] = np.percentile(b, 95)
        out.append(s)
    df = pd.DataFrame(out)
    print(df.round(4).to_string(index=False))
    curves["ALL"].to_csv(D("out", "equity_curve.csv"))
    return tr, df


if __name__ == "__main__":
    main()
