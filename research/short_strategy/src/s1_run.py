"""Run EXHAUST-S1 over the borrowable in-play universe, dev vs untouched holdout."""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import exhaust_s1 as S1

HERE = os.path.dirname(__file__)
D = lambda *a: os.path.join(HERE, "..", *a)

DEV_END = pd.Timestamp("2025-12-31")     # chronological split, frozen before running


def load(price_max=20.0, gap_min=0.20):
    ev = pd.read_csv(D("data", "s1_events.csv"), parse_dates=["date"])
    ev = ev[(ev["prev_close"] <= price_max) &
            ((ev["gap"] >= gap_min) | (ev["run"] >= gap_min))]
    m5 = pd.read_parquet(D("data", "s1_m5.parquet"))

    # drop sessions where intraday and daily disagree on the extremes
    d = pd.read_csv(D("data", "daily_panel.csv"), parse_dates=["date"])
    a = m5.groupby(["symbol", "date"]).agg(ih=("high", "max"), il=("low", "min")).reset_index()
    a = a.merge(d[["symbol", "date", "high", "low"]], on=["symbol", "date"])
    bad = set(zip(*a.loc[((a.high / a.ih - 1).abs() > 0.005) |
                         ((a.il / a.low - 1).abs() > 0.005), ["symbol", "date"]].values.T))

    bars = {}
    for key, g in m5.groupby(["symbol", "date"], sort=False):
        if key in bad:
            continue
        g = g.sort_values("minute")
        bars[key] = tuple(g[x].to_numpy() for x in
                          ("minute", "open", "high", "low", "close", "volume"))
    return ev, bars


def backtest(ev, bars, params=S1.PARAMS):
    out = []
    for r in ev.itertuples():
        b = bars.get((r.symbol, r.date))
        if b is None:
            continue
        minute, o, h, l, c, v = b
        s = S1.find_setup(minute, o, h, l, c, v, params)
        if s is None:
            continue
        exit_px, reason, exit_min = S1.run_trade(minute, o, h, l, c, s, params)
        pnl = S1.size_and_pnl(s["entry"], exit_px, s["stop"], params)
        if pnl is None:
            continue
        out.append(dict(symbol=r.symbol, date=r.date, gap=r.gap, run=r.run,
                        prev_close=r.prev_close, entry=s["entry"], stop=s["stop"],
                        exit=exit_px, reason=reason, entry_min=s["entry_min"],
                        exit_min=exit_min, stop_pct=(s["stop"] - s["entry"]) / s["entry"],
                        **pnl))
    return pd.DataFrame(out)


def stats(tr, label):
    if len(tr) == 0:
        return dict(period=label, n=0)
    R = tr["R_multiple"]
    w, losses = R[R > 0], R[R <= 0]
    pf = w.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else np.inf
    # day-clustered t on expectancy
    g = tr.groupby("date").R_multiple.mean()
    t_cl = g.mean() / (g.std(ddof=1) / np.sqrt(len(g))) if len(g) > 1 and g.std(ddof=1) > 0 else np.nan
    return dict(period=label, n=len(tr), days=tr.date.nunique(), names=tr.symbol.nunique(),
                win_rate=(R > 0).mean(), expectancy_R=R.mean(), pf=pf,
                net_pnl=tr["net"].sum(), t_clustered=t_cl)


def main():
    ev, bars = load()
    tr = backtest(ev, bars)
    tr["period"] = np.where(tr["date"] <= DEV_END, "DEV", "HOLDOUT")
    tr.to_csv(D("out", "s1_trades.csv"), index=False)

    print(f"universe events (spec $1-20, >=20%): {len(ev)}   trades taken: {len(tr)}")
    rows = [stats(tr[tr.period == p], p) for p in ("DEV", "HOLDOUT")] + [stats(tr, "ALL")]
    print(pd.DataFrame(rows).round(3).to_string(index=False))
    if len(tr):
        print("\nexit mix:")
        print((tr.groupby(["period", "reason"]).size() /
               tr.groupby("period").size()).unstack().round(3).to_string())
    return tr


if __name__ == "__main__":
    main()
