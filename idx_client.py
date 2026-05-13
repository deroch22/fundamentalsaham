"""
IDX Client - Indonesia Stock Exchange API via RapidAPI
Sumber data utama untuk: Bandarmologi, Teknikal, Sentimen, Earnings, Foreign Flow.
"""

import http.client
import json
import time
import logging

logger = logging.getLogger(__name__)

from api_client import _cache, _cached, _store

IDX_API_KEY = "579e737afemshf2a850aeb8c8d67p1fc4dbjsnf3d2389897ab"
IDX_HOST = "indonesia-stock-exchange-idx.p.rapidapi.com"

# Rate limit: Basic plan = max 10 req/detik tapi sering kena 429
# Naikkan delay untuk mengurangi error
REQUEST_DELAY = 2.0  # Antar setiap endpoint call


def _request(endpoint: str, retries: int = 2) -> dict | None:
    """Generic GET request ke IDX API."""
    headers = {
        "x-rapidapi-key": IDX_API_KEY,
        "x-rapidapi-host": IDX_HOST,
    }
    for attempt in range(retries):
        try:
            conn = http.client.HTTPSConnection(IDX_HOST, timeout=15)
            conn.request("GET", endpoint, headers=headers)
            res = conn.getresponse()
            raw = res.read().decode("utf-8")
            conn.close()

            if res.status == 429:
                wait = 5 * (attempt + 1)
                logger.warning(f"IDX Rate limited. Tunggu {wait}s...")
                time.sleep(wait)
                continue
            if res.status != 200:
                logger.error(f"IDX HTTP {res.status} untuk {endpoint}")
                return None

            data = json.loads(raw)
            if data.get("success"):
                return data.get("data", data)
            else:
                logger.warning(f"IDX API response not success: {data.get('message', '')}")
                return None

        except Exception as e:
            logger.warning(f"IDX Attempt {attempt+1} gagal: {e}")
            time.sleep(1.5)
    return None


# ═══════════════════════════════════════════════════════════
#  EMITEN (Company Data)
# ═══════════════════════════════════════════════════════════

def get_emiten_info(ticker: str) -> dict | None:
    """
    Info saham: harga, volume, market cap, orderbook, sektor.
    Ticker tanpa .JK (misal: BBCA, bukan BBCA.JK)
    """
    data = _request(f"/api/emiten/{ticker}/info")
    time.sleep(REQUEST_DELAY)
    return data


def get_emiten_profile(ticker: str) -> dict | None:
    """Profil perusahaan: deskripsi, executives, shareholders."""
    data = _request(f"/api/emiten/{ticker}/profile")
    time.sleep(REQUEST_DELAY)
    return data


def get_insider_trading(ticker: str) -> dict | None:
    """Data insider trading (pembelian/penjualan direksi)."""
    data = _request(f"/api/emiten/{ticker}/insider")
    time.sleep(REQUEST_DELAY)
    return data


def get_foreign_ownership(ticker: str) -> dict | None:
    """Kepemilikan asing: Vanguard, BlackRock, dll."""
    data = _request(f"/api/emiten/{ticker}/foreign-ownership")
    time.sleep(REQUEST_DELAY)
    return data


# ═══════════════════════════════════════════════════════════
#  CHART (OHLCV + Foreign Flow)
# ═══════════════════════════════════════════════════════════

def get_daily_chart(ticker: str, limit: int = 250) -> dict | None:
    """
    Data OHLCV harian + foreign buy/sell per hari.
    Limit 250 = ~1 tahun trading.
    """
    data = _request(f"/api/chart/{ticker}/daily/latest?limit={limit}")
    time.sleep(REQUEST_DELAY)
    return data


# ═══════════════════════════════════════════════════════════
#  TECHNICAL ANALYSIS (Pre-calculated)
# ═══════════════════════════════════════════════════════════

def get_technical_analysis(ticker: str) -> dict | None:
    """
    Analisis teknikal: RSI, MACD, SMA (5/10/20/50/200),
    Bollinger, Stochastic, ATR, OBV, VWAP.
    """
    data = _request(
        f"/api/analysis/technical/{ticker}?indicators=rsi,macd,sma,bollinger,stochastic,atr,obv,vwap"
    )
    time.sleep(REQUEST_DELAY)
    return data


# ═══════════════════════════════════════════════════════════
#  BANDARMOLOGY & SENTIMENT
# ═══════════════════════════════════════════════════════════

def get_bandar_sentiment(ticker: str, days: int = 7) -> dict | None:
    """
    Sentimen Retail vs Bandar:
    - retail_sentiment: score, status, danger_level, fomo_score
    - bandar_sentiment: score, status, foreign_flow, accumulation_score
    - top_brokers: buyers & sellers dengan net value
    """
    data = _request(f"/api/analysis/sentiment/{ticker}?days={days}")
    time.sleep(REQUEST_DELAY)
    return data


# ═══════════════════════════════════════════════════════════
#  EARNINGS & INSIGHTS (Beta)
# ═══════════════════════════════════════════════════════════

def get_insights(ticker: str) -> dict | None:
    """
    Skor insight: Valuation, Growth, Profitability, Health, Performance.
    Perbandingan vs peers dan industri.
    """
    data = _request(f"/api/beta/insights/{ticker}")
    time.sleep(REQUEST_DELAY)
    if data and "data" in data:
        return data["data"]
    return data


def get_earnings(ticker: str) -> dict | None:
    """
    Earnings: EPS aktual vs forecast, revenue surprise,
    forecast tahunan & kuartalan.
    """
    data = _request(f"/api/beta/earnings/{ticker}")
    time.sleep(REQUEST_DELAY)
    if data and "data" in data:
        return data["data"]
    return data


# ═══════════════════════════════════════════════════════════
#  MARKET-WIDE DATA
# ═══════════════════════════════════════════════════════════

def get_top_gainers() -> dict | None:
    """Top gainer hari ini."""
    data = _request("/api/movers/top-gainer")
    time.sleep(REQUEST_DELAY)
    return data


def get_top_losers() -> dict | None:
    """Top loser hari ini."""
    data = _request("/api/movers/top-loser")
    time.sleep(REQUEST_DELAY)
    return data


def get_sectors() -> dict | None:
    """Data semua sektor IDX."""
    data = _request("/api/sectors")
    time.sleep(REQUEST_DELAY)
    return data


def get_global_impact() -> dict | None:
    """Dampak indeks global terhadap IHSG."""
    data = _request("/api/global/indices-impact")
    time.sleep(REQUEST_DELAY)
    return data

def get_all_corporate_actions() -> dict:
    """
    Mengambil data kalender Right Issue, Stock Split, dan Dividend.
    Return dictionary: { 'BBCA': ['Dividend: Rp 50 (Cum: 2026-05-20)'], 'PYFA': ['Right Issue (Cum: 2026-07-07)'] }
    Di-cache 12 jam (43200 detik) untuk mengurangi request 429.
    """
    key = "global_corp_actions"
    cached = _cached(key, ttl=43200)
    if cached is not None:
        return cached

    corp_actions = {}
    endpoints = {
        "Right Issue": ("/api/calendar/right-issue", "rightissue"),
        "Stock Split": ("/api/calendar/stock-split", "stocksplit"),
        "Dividend": ("/api/calendar/dividend", "dividend"),
    }

    for action_name, (ep, datakey) in endpoints.items():
        time.sleep(2.0) # Hindari 429 rate limit
        res = _request(ep)
        if not res or "data" not in res or datakey not in res["data"]:
            continue
        
        items = res["data"][datakey]
        for item in items:
            sym = item.get("company_symbol", "")
            if not sym:
                continue
            
            cumdate = item.get(f"{datakey}_cumdate", "")
            if not cumdate:
                continue
                
            if sym not in corp_actions:
                corp_actions[sym] = []
                
            if action_name == "Dividend":
                val = item.get("dividend_value_formatted") or item.get("dividend_value", "")
                corp_actions[sym].append(f"Dividend: {val} (Cum: {cumdate})")
            elif action_name == "Stock Split":
                ratio = item.get("stocksplit_ratio", "")
                corp_actions[sym].append(f"Stock Split: {ratio} (Cum: {cumdate})")
            elif action_name == "Right Issue":
                corp_actions[sym].append(f"Right Issue (Cum: {cumdate})")

    return _store(key, corp_actions)

def get_dividend_calendar() -> dict | None:
    """Kalender dividen (raw endpoint)."""
    data = _request("/api/calendar/dividend")
    time.sleep(REQUEST_DELAY)
    return data

def get_insider_screening() -> dict | None:
    """Screening insider trading seluruh emiten."""
    data = _request("/api/analysis/insider-screening")
    time.sleep(REQUEST_DELAY)
    return data

def get_trending() -> dict | None:
    """Saham trending hari ini."""
    data = _request("/api/main/trending")
    time.sleep(REQUEST_DELAY)
    return data
