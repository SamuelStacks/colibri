"""Intraday RTH short backtester.

Position lifecycle, all inside one session — nothing is ever held overnight:
  entry   one of several 09:30-10:00 rules
  stop    hard stop above entry, checked against every subsequent bar's high
  target  optional profit target below entry
  exit    otherwise cover on the 15:45 bar's close

Conservatism, applied deliberately so results lean pessimistic:
  * when a single bar touches BOTH the stop and the target, the stop is taken;
  * stop fills are assumed at the stop level, but a bar that GAPS through the
    stop (its open is already above it) fills at that open, which is worse;
  * costs are charged on both legs.
"""
import numpy as np
import pandas as pd

MKT_CLOSE_MIN = 15 * 60 + 45      # 15:45 M15 bar == the closing bar
OPEN_MIN = 9 * 60 + 30


class Costs:
    def __init__(self, slip_bps=5.0, commission_bps=2.0, borrow_bps=0.0):
        self.slip_bps = slip_bps            # per leg
        self.commission_bps = commission_bps  # per leg
        self.borrow_bps = borrow_bps        # per trade, intraday locate

    @property
    def round_trip_bps(self):
        return 2 * (self.slip_bps + self.commission_bps) + self.borrow_bps


def _session_bars(g):
    """(minute, open, high, low, close) arrays for one session, in time order."""
    return (g["minute"].to_numpy(), g["open"].to_numpy(), g["high"].to_numpy(),
            g["low"].to_numpy(), g["close"].to_numpy())


def find_entry(minute, o, h, l, c, rule):
    """Return (entry_index, entry_price) or (None, None) if no entry triggers.

    Index is the bar the position is opened on; stops are only checked from the
    NEXT bar onward for rules that enter at a bar's close, which avoids using
    the entry bar's own range against the trade.
    """
    if rule == "open":                      # short the opening print
        return 0, o[0]

    if rule == "b1_close":                  # short the close of the 09:30 bar
        return 0, c[0]

    if rule == "b1_close_red":              # only if that first bar closed red
        if c[0] < o[0]:
            return 0, c[0]
        return None, None

    if rule == "b2_close":                  # short the close of the 09:45 bar
        if len(c) < 2:
            return None, None
        return 1, c[1]

    if rule == "orb_down_red":
        # opening flush, but only after the first bar has already failed (closed red)
        if len(l) < 2 or c[0] >= o[0]:
            return None, None
        or_low = l[0]
        for k in range(1, len(l)):
            if l[k] < or_low:
                return k, min(or_low, o[k])
        return None, None

    if rule == "orb_down":
        # opening-flush: short the break of the first 15-minute bar's low
        if len(l) < 2:
            return None, None
        or_low = l[0]
        for k in range(1, len(l)):
            if l[k] < or_low:
                # fill at the break level, or worse if the bar gapped below it
                return k, min(or_low, o[k])
        return None, None

    raise ValueError(rule)


def run_trade(minute, o, h, l, c, rule, stop_pct, target_pct):
    ei, entry = find_entry(minute, o, h, l, c, rule)
    if ei is None or not np.isfinite(entry) or entry <= 0:
        return None

    stop = entry * (1 + stop_pct)
    target = entry * (1 - target_pct) if target_pct else None

    # for close-based entries the position exists only from the next bar
    start = ei if rule in ("open", "orb_down") else ei + 1
    if rule in ("open", "orb_down"):
        start = ei + 1 if rule == "open" else ei + 1

    for k in range(start, len(c)):
        if o[k] >= stop:                    # gapped through the stop
            return entry, o[k], "stop_gap", minute[k]
        if h[k] >= stop:                    # stop before target, always
            return entry, stop, "stop", minute[k]
        if target is not None and l[k] <= target:
            return entry, target, "target", minute[k]
    return entry, c[-1], "eod", minute[-1]


def backtest(events, bars_by_key, rule="b1_close", stop_pct=0.03, target_pct=None,
             costs=Costs()):
    """events: DataFrame with symbol/date and signal columns. Returns trade blotter."""
    out = []
    for r in events.itertuples():
        g = bars_by_key.get((r.symbol, r.date))
        if g is None:
            continue
        minute, o, h, l, c = g
        res = run_trade(minute, o, h, l, c, rule, stop_pct, target_pct)
        if res is None:
            continue
        entry, exit_px, reason, exit_min = res
        gross = entry / exit_px - 1.0                     # short P&L
        net = gross - costs.round_trip_bps / 1e4
        out.append(dict(symbol=r.symbol, date=r.date, gap=r.gap, atr_pct=r.atr_pct,
                        entry=entry, exit=exit_px, reason=reason, exit_min=exit_min,
                        gross=gross, ret=net))
    return pd.DataFrame(out)


def stats(tr, label=""):
    if len(tr) == 0:
        return dict(label=label, n=0)
    r = tr["ret"]
    wins, losses = r[r > 0], r[r <= 0]
    pf = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else np.inf
    # t-stat of mean return, clustered nothing fancy — just the naive one
    t = r.mean() / (r.std(ddof=1) / np.sqrt(len(r))) if r.std(ddof=1) > 0 else np.nan
    return dict(label=label, n=len(r), ev_bps=r.mean() * 1e4, med_bps=r.median() * 1e4,
                win=(r > 0).mean(), pf=pf, t=t, std_bps=r.std(ddof=1) * 1e4,
                worst=r.min(), best=r.max(), total_R=r.sum())


def bars_index(intraday):
    """Pre-slice the intraday panel into per-session numpy arrays."""
    d = {}
    for key, g in intraday.groupby(["symbol", "date"], sort=False):
        g = g.sort_values("minute")
        d[key] = _session_bars(g)
    return d
