"""The Bounce-Fade short: specification and signal generation.

Thesis
------
A high-volatility name that is already in a downtrend gaps up at the open. That
pop is relief/short-covering rather than a change of trend, so it is distributed
into. We do NOT short strength in an uptrend — the research showed that loses.
The gap must also be capped: above ~12% the distribution flips to a coin-flip
with a fat squeeze tail.

Entry requires CONFIRMATION. Shorting the opening print unconditionally has no
out-of-sample edge; waiting for the first 15-minute bar to fail, and for the
market to break that bar's low, is what carries the result.

All positions open and close inside RTH. Nothing is held overnight.
"""
import pandas as pd

PARAMS = dict(
    gap_min=0.03,      # gap must be a real pop
    gap_max=0.12,      # above this it is a squeeze, not a fade
    atr_min=0.04,      # only names that actually move
    min_price=5.0,     # borrowable, no sub-$5 tick/locate problems
    min_adv=25e6,      # can short size into it
    stop_pct=0.05,     # hard stop above entry
    target_pct=None,   # let the EOD cover do the work; targets tested worse
    rule="orb_down_red",
)


def signals(panel, intraday_symbols, suspect_sessions=frozenset(), params=PARAMS):
    """Point-in-time signal set. Every field is known before 09:30 on the trade date."""
    p = params
    m = (
        panel["symbol"].isin(intraday_symbols)
        & (panel["prev_close"] >= p["min_price"])
        & (panel["adv20"] >= p["min_adv"])
        & panel["atr14"].notna()
        & (panel["gap"] >= p["gap_min"])
        & (panel["gap"] <= p["gap_max"])
        & (panel["ext_sma20"] < 0)          # prior close BELOW its 20d mean: downtrend
        & (panel["atr_pct"] >= p["atr_min"])
    )
    ev = panel[m].copy()
    if suspect_sessions:
        keep = [(s, d) not in suspect_sessions for s, d in zip(ev["symbol"], ev["date"])]
        ev = ev[keep]
    return ev.sort_values(["date", "symbol"]).reset_index(drop=True)
