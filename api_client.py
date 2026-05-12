"""
API Client - Yahoo Finance via RapidAPI (yahoo-finance166)
Endpoint yang sudah terverifikasi berfungsi.
"""

import http.client
import json
import time
import logging
from config import RAPIDAPI_KEY, RAPIDAPI_HOST

logger = logging.getLogger(__name__)

# Delay antar request agar tidak kena rate limit
REQUEST_DELAY = 0.5


def _request(endpoint: str, retries: int = 3) -> dict | None:
    """Generic GET request ke RapidAPI dengan retry."""
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST,
    }
    for attempt in range(retries):
        try:
            conn = http.client.HTTPSConnection(RAPIDAPI_HOST, timeout=15)
            conn.request("GET", endpoint, headers=headers)
            res = conn.getresponse()
            raw = res.read().decode("utf-8")
            conn.close()

            if res.status == 429:
                wait = 3 * (attempt + 1)
                logger.warning(f"Rate limited. Tunggu {wait}s...")
                time.sleep(wait)
                continue
            if res.status != 200:
                logger.error(f"HTTP {res.status} untuk {endpoint}")
                return None

            return json.loads(raw)

        except Exception as e:
            logger.warning(f"Attempt {attempt+1} gagal: {e}")
            time.sleep(1.5)
    return None


def _quote_summary_result(data: dict) -> dict | None:
    """Ambil result pertama dari format quoteSummary standard."""
    try:
        result = data.get("quoteSummary", {}).get("result", [])
        return result[0] if result else None
    except Exception:
        return None


def get_financial_data(ticker: str) -> dict | None:
    """
    ROE, ROA, margins, growth, rekomendasi analis, target price.
    Key: financialData
    """
    data = _request(f"/api/stock/get-financial-data?region=ID&symbol={ticker}")
    time.sleep(REQUEST_DELAY)
    if not data:
        return None
    result = _quote_summary_result(data)
    return result.get("financialData") if result else None


def get_statistics(ticker: str) -> dict | None:
    """
    PER, PBV, DER, short ratio, beta, earnings growth.
    Keys: defaultKeyStatistics, financialData
    """
    data = _request(f"/api/stock/get-statistics?region=ID&symbol={ticker}")
    time.sleep(REQUEST_DELAY)
    if not data:
        return None
    result = _quote_summary_result(data)
    return result if result else None


def get_price(ticker: str) -> dict | None:
    """
    Harga pasar saat ini, market cap, volume.
    Key: price
    """
    data = _request(f"/api/stock/get-price?region=ID&symbol={ticker}")
    time.sleep(REQUEST_DELAY)
    if not data:
        return None
    result = _quote_summary_result(data)
    return result.get("price") if result else None


def get_fundamentals(ticker: str) -> dict | None:
    """
    Profil perusahaan, sektor, industri, dan JAJARAN DIREKSI.
    Key: assetProfile (berisi companyOfficers)
    """
    data = _request(f"/api/stock/get-fundamentals?region=ID&symbol={ticker}")
    time.sleep(REQUEST_DELAY)
    if not data:
        return None
    result = _quote_summary_result(data)
    return result.get("assetProfile") if result else None


def get_earnings(ticker: str) -> dict | None:
    """
    Laporan laba per kuartal vs estimasi analis.
    Key: earnings
    """
    data = _request(f"/api/stock/get-earnings?region=ID&symbol={ticker}")
    time.sleep(REQUEST_DELAY)
    if not data:
        return None
    result = _quote_summary_result(data)
    return result.get("earnings") if result else None


def get_chart(ticker: str, interval: str = "1d", range_: str = "5y") -> dict | None:
    """
    Data harga historis untuk momentum, technical (SMA/RSI), dan seasonality.
    Default 5y untuk mendapatkan probabilitas historis yang cukup.
    """
    data = _request(
        f"/api/stock/get-chart?symbol={ticker}&interval={interval}&range={range_}&region=ID"
    )
    time.sleep(REQUEST_DELAY)
    if not data:
        return None
    try:
        result = data.get("chart", {}).get("result", [])
        return result[0] if result else None
    except Exception:
        return None


def safe_raw(data: dict, *keys, default=None):
    """
    Ambil nilai dari nested dict secara aman.
    Otomatis ambil 'raw' jika format Yahoo Finance {"raw": x, "fmt": "y"}.
    """
    try:
        val = data
        for k in keys:
            val = val[k]
        if isinstance(val, dict) and "raw" in val:
            return val["raw"]
        return val if val != {} else default
    except (KeyError, TypeError, IndexError):
        return default
