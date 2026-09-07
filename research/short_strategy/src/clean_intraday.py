"""Put intraday bars on the same adjusted price basis as the daily panel.

Nine symbols come back from the vendor on an unadjusted basis (splits and, for a
few, dividends) while the daily bars are adjusted. High/low/close differ from the
daily bar by a single multiplicative factor per session, so we rescale each
session by daily_close / intraday_session_close. That is a no-op (factor 1.0) for
sessions that already agree.

The daily `open` is the official opening-auction print; the first M15 bar opens at
the first consolidated trade in 09:30-09:45, so the two legitimately differ. We
keep the intraday series internally consistent and use the daily open only for
gap measurement.
"""
import os
import pandas as pd

HERE = os.path.dirname(__file__)

def main():
    i = pd.read_parquet(os.path.join(HERE, "..", "data", "intraday_m15.parquet"))
    d = pd.read_csv(os.path.join(HERE, "..", "data", "daily_panel.csv"), parse_dates=["date"])

    sess = i.groupby(["symbol", "date"]).agg(
        n_bars=("open", "size"), i_close=("close", "last")).reset_index()
    sess = sess.merge(d[["symbol", "date", "close"]], on=["symbol", "date"], how="inner")
    sess["factor"] = sess["close"] / sess["i_close"]

    # a session must be a full (26) or half (13) day to be tradable
    sess = sess[sess["n_bars"].isin([26, 13])]

    i = i.merge(sess[["symbol", "date", "factor", "n_bars"]], on=["symbol", "date"], how="inner")
    for c in ("open", "high", "low", "close"):
        i[c] = i[c] * i["factor"]

    i = i.drop(columns=["factor"]).sort_values(["symbol", "date", "minute"]).reset_index(drop=True)
    out = os.path.join(HERE, "..", "data", "intraday_clean.parquet")
    i.to_parquet(out)

    chk = i.groupby(["symbol", "date"]).agg(h=("high", "max"), l=("low", "min"),
                                            c=("close", "last")).reset_index()
    chk = chk.merge(d, on=["symbol", "date"])
    for a, b in (("h", "high"), ("l", "low"), ("c", "close")):
        e = (chk[a] / chk[b] - 1).abs()
        print(f"post-fix {b:5s}: median {e.median():.2e}  max {e.max():.2e}  >0.5%: {(e > 0.005).sum()}")
    print(f"rows={len(i)} symbols={i.symbol.nunique()} sessions={len(chk)}")

if __name__ == "__main__":
    main()
