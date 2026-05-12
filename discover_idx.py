"""Discover all working IDX API endpoints."""
import http.client, json, time

KEY = "579e737afemshf2a850aeb8c8d67p1fc4dbjsnf3d2389897ab"
HOST = "indonesia-stock-exchange-idx.p.rapidapi.com"

def call(path):
    conn = http.client.HTTPSConnection(HOST)
    h = {"x-rapidapi-key": KEY, "x-rapidapi-host": HOST}
    conn.request("GET", path, headers=h)
    r = conn.getresponse()
    raw = r.read().decode("utf-8")
    try:
        return r.status, json.loads(raw)
    except:
        return r.status, {"raw": raw[:200]}

endpoints = [
    # Main
    "/api/main/trending",
    "/api/main/symbols",
    # Emiten
    "/api/emiten/BBCA/info",
    "/api/emiten/BBCA/profile",
    "/api/emiten/BBCA/key-statistics",
    "/api/emiten/BBCA/financials",
    "/api/emiten/BBCA/seasonality",
    "/api/emiten/BBCA/insider",
    "/api/emiten/BBCA/insider-trading",
    "/api/emiten/BBCA/foreign-ownership",
    "/api/emiten/BBCA/holding-composition",
    "/api/emiten/BBCA/historical-summary",
    "/api/emiten/BBCA/broker-summary",
    # Chart
    "/api/chart/BBCA/daily/latest?limit=5",
    "/api/chart/BBCA/intraday/latest?interval=1h&limit=5",
    # Technical
    "/api/analysis/technical/BBCA?indicators=rsi,macd,sma",
    "/api/analysis/technical/BBCA?indicators=bollinger,stochastic,atr",
    # Sentiment
    "/api/analysis/sentiment/BBCA?days=7",
    "/api/analysis/ipo-momentum",
    # Bandarmology
    "/api/analysis/bandarmology/BBCA",
    "/api/analysis/accumulation/BBCA",
    "/api/analysis/distribution/BBCA",
    "/api/analysis/smart-money/BBCA",
    "/api/analysis/pump-dump/BBCA",
    # Movers
    "/api/movers/top-gainer",
    "/api/movers/top-loser",
    "/api/movers/most-active",
    # Retail
    "/api/analysis/multibagger",
    "/api/analysis/breakout",
    "/api/analysis/risk-reward/BBCA",
    "/api/analysis/sector-rotation",
    # Market
    "/api/market/overview",
    "/api/global/overview",
    "/api/global/indices-impact",
    # Detector
    "/api/detector/whale/BBCA",
    "/api/analysis/whale/BBCA",
    "/api/analysis/correlation",
    "/api/analysis/insider-screening",
    # Sectors
    "/api/sectors",
    "/api/sectors/all",
    # Calendar
    "/api/calendar/dividend",
    "/api/calendar/ipo",
    # Beta
    "/api/beta/insights/BBCA",
    "/api/beta/earnings/BBCA",
    "/api/beta/key-ratios/BBCA",
]

print(f"Testing {len(endpoints)} endpoints...\n")
working = []
for ep in endpoints:
    time.sleep(1.2)
    status, data = call(ep)
    ok = status == 200 and isinstance(data, dict) and data.get("success")
    icon = "OK" if ok else "XX"
    print(f"[{icon}] {status:>3} {ep}")
    if ok:
        working.append(ep)

print(f"\n{'='*60}")
print(f"WORKING ENDPOINTS: {len(working)} / {len(endpoints)}")
for w in working:
    print(f"  + {w}")
