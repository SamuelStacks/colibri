"""Build the M5 RTH panel for EXHAUST-S1 event sessions and reconcile against daily."""
import json, glob, os
import pandas as pd

RAW = "/root/.claude/projects/-home-user-colibri/fb539145-badf-594e-b692-771260e3ce37/tool-results"
HERE = os.path.dirname(__file__)
D = lambda *a: os.path.join(HERE, "..", *a)


def main():
    # Only the M5 pulls for this study. Earlier dumps in the same directory are
    # daily bars and the M15 panel from the previous strategy; M15 bars share
    # timestamps with M5 bars (09:30, 09:45, ...) so mixing them silently
    # corrupts every session. Files are named with a millisecond timestamp.
    M5_PULL_START = 1788765000000
    recs = {}
    files = []
    for f in glob.glob(os.path.join(RAW, "mcp-Webull-get_stock_bars-*.txt")):
        try:
            ts = int(os.path.basename(f).rsplit("-", 1)[1].split(".")[0])
        except ValueError:
            continue
        if ts >= M5_PULL_START:
            files.append(f)
    for f in sorted(files):
        try:
            j = json.loads(open(f).read())
        except Exception:
            continue
        if not isinstance(j, dict) or "result" not in j:
            continue
        for blk in j["result"]:
            sym = blk.get("symbol")
            for b in blk.get("result") or []:
                if b.get("trading_session") != "RTH":
                    continue
                k = (sym, b["time"])
                if k in recs:
                    continue
                try:
                    recs[k] = (sym, b["time"], float(b["open"]), float(b["high"]),
                               float(b["low"]), float(b["close"]), float(b["volume"]))
                except (TypeError, ValueError):
                    continue

    df = pd.DataFrame(recs.values(),
                      columns=["symbol", "time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    et = df["time"].dt.tz_convert("America/New_York")
    df["date"] = et.dt.normalize().dt.tz_localize(None)
    df["minute"] = et.dt.hour * 60 + et.dt.minute
    # a complete M5 RTH session is 78 bars; accept 60+ to allow minor vendor gaps
    n = df.groupby(["symbol", "date"]).minute.transform("size")
    df = df[n >= 60]
    df = df.sort_values(["symbol", "date", "minute"]).reset_index(drop=True)

    # put intraday on the daily adjusted basis (same vendor split/div mismatch as before)
    d = pd.read_csv(D("data", "daily_panel.csv"), parse_dates=["date"])
    sess = df.groupby(["symbol", "date"]).agg(n=("minute", "size"),
                                              ic=("close", "last")).reset_index()
    sess = sess.merge(d[["symbol", "date", "close"]], on=["symbol", "date"], how="inner")
    sess["factor"] = sess["close"] / sess["ic"]
    sess = sess[sess["n"].between(60, 79)]
    df = df.merge(sess[["symbol", "date", "factor"]], on=["symbol", "date"], how="inner")
    for c in ("open", "high", "low", "close"):
        df[c] *= df["factor"]
    df = df.drop(columns=["factor"])
    df.to_parquet(D("data", "s1_m5.parquet"))

    chk = df.groupby(["symbol", "date"]).agg(h=("high", "max"), l=("low", "min"),
                                             c=("close", "last")).reset_index().merge(d, on=["symbol", "date"])
    for a, b in (("h", "high"), ("l", "low"), ("c", "close")):
        e = (chk[a] / chk[b] - 1).abs()
        print(f"  reconcile {b:5s}: median {e.median():.1e}  >0.5%: {(e > 0.005).sum()}/{len(chk)}")
    print(f"M5 rows={len(df)} symbols={df.symbol.nunique()} sessions={len(chk)}")
    return df


if __name__ == "__main__":
    main()
