"""
IDX Client - Indonesia Stock Exchange API via RapidAPI
Sumber data utama untuk: Bandarmologi, Teknikal, Sentimen, Earnings, Foreign Flow.
"""

import http.client
import json
import time
import logging

logger = logging.getLogger(__name__)

IDX_API_KEY = "579e737afemshf2a850aeb8c8d67p1fc4dbjsnf3d2389897ab"
IDX_HOST = "indonesia-stock-exchange-idx.p.rapidapi.com"

# Rate limit: 1 request per second (BASIC plan)
REQUEST_DELAY = 1.2


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
                wait = 3 * (attempt + 1)
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


def get_dividend_calendar() -> dict | None:
    """Kalender dividen."""
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
