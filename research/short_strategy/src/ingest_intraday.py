"""Consolidate M15 RTH intraday dumps into a per-session bar panel."""
import json, glob, os
import pandas as pd

RAW = "/root/.claude/projects/-home-user-colibri/fb539145-badf-594e-b692-771260e3ce37/tool-results"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "intraday_m15.parquet")

def main():
    recs = {}   # (symbol, utc_time) -> row, dedupes overlapping windows
    for f in sorted(glob.glob(os.path.join(RAW, "mcp-Webull-get_stock_bars-*.txt"))):
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
                    continue          # daily dumps carry "" here, so this also filters them out
                key = (sym, b["time"])
                if key in recs:
                    continue
                try:
                    recs[key] = (sym, b["time"], float(b["open"]), float(b["high"]),
                                 float(b["low"]), float(b["close"]), float(b["volume"]))
                except (TypeError, ValueError):
                    continue

    df = pd.DataFrame(recs.values(),
                      columns=["symbol", "time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df["et"] = df["time"].dt.tz_convert("America/New_York")
    df["date"] = df["et"].dt.normalize().dt.tz_localize(None)
    df["minute"] = df["et"].dt.hour * 60 + df["et"].dt.minute
    df = df.sort_values(["symbol", "time"]).reset_index(drop=True)
    df.to_parquet(OUT)
    print(f"rows={len(df)} symbols={df.symbol.nunique()} "
          f"sessions={df.groupby('symbol').date.nunique().median():.0f} (median/symbol)")
    print("date range", df.date.min().date(), "->", df.date.max().date())
    return df

if __name__ == "__main__":
    main()
