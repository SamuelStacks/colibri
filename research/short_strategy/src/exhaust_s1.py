"""EXHAUST-S1 — VWAP Backside Continuation Short.

The pattern, in order (all on M5 RTH bars):
  1. price below session VWAP
  2. EMA9 < EMA20
  3. price bounces back toward/touches VWAP
  4. the bounce FAILS to reclaim VWAP on a closing basis
  5. the bounce is a LOWER HIGH than the session high
  6. a later candle breaks below that bounce candle's low
  7. short on the following bar

We do not predict the top. The short does not exist until the bulls fail.

Frozen parameters live in PARAMS and are not fitted anywhere in this file.

Conventions that had to be pinned down, and why:
  * VWAP is session-anchored from 09:30 on typical price (H+L+C)/3.
  * EMA9/EMA20 are session-anchored, seeded at the first bar's close. A
    continuous intraday EMA would need the prior session's M5 bars, which are
    not pulled; session anchoring is the standard platform fallback.
  * Entry is the OPEN of the bar AFTER the break bar — never an intrabar fill.
    That is strictly executable and is the pessimistic reading of "short on the
    following bar".
  * A fill more than `max_chase` below the trigger is REJECTED, which is the
    "next-bar limit within 0.5% of trigger" rule.
  * If a single bar touches both stop and target, the STOP is taken.
"""
import numpy as np
import pandas as pd

PARAMS = dict(
    win_start=9 * 60 + 45,      # 09:45 ET
    win_end=11 * 60 + 30,       # 11:30 ET
    vwap_touch=0.002,           # bounce must reach within 0.2% of VWAP to count as a test
    stop_atr_mult=0.15,         # stop = bounce high + 0.15 * ATR14(M5)
    max_stop_pct=0.04,          # reject if the structural stop is >4% from entry
    max_chase=0.005,            # reject if entry is >0.5% below the trigger
    entry_mode="next_open",     # "next_open" | "stop_at_trigger" (resting stop order)
    confirm_within=4,           # break must occur within 4 bars of the bounce candle
    target_R=2.0,
    risk_dollars=150.0,
    max_shares=1000,
    slippage=0.01,              # $/share adverse, each fill
    commission=0.005,           # $/share/side
)


def session_indicators(o, h, l, c, v):
    tp = (h + l + c) / 3.0
    cum_v = np.cumsum(v)
    vwap = np.cumsum(tp * v) / np.where(cum_v == 0, np.nan, cum_v)

    def ema(x, n):
        a = 2.0 / (n + 1.0)
        out = np.empty_like(x)
        out[0] = x[0]
        for i in range(1, len(x)):
            out[i] = a * x[i] + (1 - a) * out[i - 1]
        return out

    ema9, ema20 = ema(c, 9), ema(c, 20)

    prev_c = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr = pd.Series(tr).rolling(14, min_periods=3).mean().to_numpy()
    return vwap, ema9, ema20, atr


def find_setup(minute, o, h, l, c, v, p=PARAMS):
    """Return the first valid setup in the window, or None."""
    vwap, ema9, ema20, atr = session_indicators(o, h, l, c, v)
    n = len(c)
    hod = np.maximum.accumulate(h)

    for k in range(2, n):
        if minute[k] < p["win_start"] or minute[k] > p["win_end"]:
            continue
        if not np.isfinite(atr[k]) or atr[k] <= 0:
            continue

        # (1)(2) backside regime, (3)(4) bounce tested VWAP but closed under it
        if not (c[k] < vwap[k] and ema9[k] < ema20[k]):
            continue
        if h[k] < vwap[k] * (1 - p["vwap_touch"]):
            continue                                   # never got back to VWAP
        if h[k] >= vwap[k] and c[k] >= vwap[k]:
            continue                                   # actually reclaimed it
        # (5) lower high: the bounce must fail below the session high
        if h[k] >= hod[k - 1]:
            continue

        bounce_high, trigger = h[k], l[k]

        # (6) a later bar breaks the bounce candle's low, within confirm_within
        for j in range(k + 1, min(k + 1 + p["confirm_within"], n)):
            # setup invalidated before confirmation?
            if h[j] > hod[k] or (c[j] > vwap[j] and ema9[j] > ema20[j]):
                break
            if l[j] < trigger:
                if j + 1 >= n:
                    return None
                if p.get("entry_mode", "next_open") == "stop_at_trigger":
                    # a resting short-stop at the confirmation low: fills on the
                    # break bar itself, at the trigger, or at that bar's open if
                    # the bar opened straight through it
                    entry_i, entry = j, min(trigger, o[j])
                else:
                    if j + 1 >= n:
                        return None
                    entry_i, entry = j + 1, o[j + 1]    # (7) short the following bar
                if entry < trigger * (1 - p["max_chase"]):
                    return None                         # chased too far below trigger
                stop = bounce_high + p["stop_atr_mult"] * atr[k]
                if stop <= entry:
                    return None
                if (stop - entry) / entry > p["max_stop_pct"]:
                    return None                         # structural stop too wide
                return dict(entry_i=entry_i, entry=entry, stop=stop, trigger=trigger,
                            bounce_high=bounce_high, atr=atr[k],
                            entry_min=minute[entry_i], vwap_at_entry=vwap[entry_i])
    return None


def run_trade(minute, o, h, l, c, s, p=PARAMS):
    entry, stop = s["entry"], s["stop"]
    R = stop - entry
    target = entry - p["target_R"] * R

    for i in range(s["entry_i"] + 1, len(c)):
        if o[i] >= stop:
            return o[i], "stop_gap", minute[i]
        if h[i] >= stop:                                # stop before target, always
            return stop, "stop", minute[i]
        if l[i] <= target:
            return target, "target", minute[i]
    return c[-1], "eod", minute[-1]


def size_and_pnl(entry, exit_px, stop, p=PARAMS):
    R = stop - entry
    shares = min(p["max_shares"], int(p["risk_dollars"] // R)) if R > 0 else 0
    if shares <= 0:
        return None
    fill_in = entry - p["slippage"]                     # short fills lower = worse
    fill_out = exit_px + p["slippage"]                  # cover fills higher = worse
    gross = (fill_in - fill_out) * shares
    net = gross - p["commission"] * shares * 2
    return dict(shares=shares, R_dollars=R, gross=gross, net=net,
                R_multiple=net / (R * shares))
