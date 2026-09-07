"""Consolidate raw Webull get_stock_bars tool-result dumps into a tidy daily panel."""
import json, glob, os, csv

RAW = "/root/.claude/projects/-home-user-colibri/fb539145-badf-594e-b692-771260e3ce37/tool-results"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "daily_panel.csv")

def main():
    bysym = {}
    for f in sorted(glob.glob(os.path.join(RAW, "mcp-Webull-get_stock_bars-*.txt"))):
        try:
            j = json.loads(open(f).read())
        except Exception:
            continue
        if "result" not in j:
            continue
        for blk in j["result"]:
            sym = blk.get("symbol")
            bars = blk.get("result") or []
            if not sym or not bars:
                continue
            # keep the longest series if a symbol appears in several dumps
            if sym in bysym and len(bysym[sym]) >= len(bars):
                continue
            bysym[sym] = bars

    rows = []
    for sym, bars in bysym.items():
        for b in bars:
            # daily bars are stamped 04:00Z; the date part is the session date
            d = b["time"][:10]
            try:
                o, h, l, c = (float(b[k]) for k in ("open", "high", "low", "close"))
                v = float(b["volume"])
            except (TypeError, ValueError):
                continue
            if not (o > 0 and h > 0 and l > 0 and c > 0):
                continue
            rows.append((sym, d, o, h, l, c, v))

    rows.sort(key=lambda r: (r[0], r[1]))
    with open(OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "date", "open", "high", "low", "close", "volume"])
        w.writerows(rows)
    print(f"symbols={len(bysym)} rows={len(rows)} -> {os.path.abspath(OUT)}")

if __name__ == "__main__":
    main()
