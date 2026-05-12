"""
API Client - Yahoo Finance via yfinance library (GRATIS, no RapidAPI quota)
Menggantikan api_client berbasis RapidAPI yang sering kena rate limit.
"""

import logging
import time
import yfinance as yf

logger = logging.getLogger(__name__)

# Cache sederhana in-memory per session
_cache: dict = {}
CACHE_TTL = 3600  # 1 jam


def _get_ticker(ticker: str) -> yf.Ticker:
    return yf.Ticker(ticker)


def _cached(key: str, ttl: int = CACHE_TTL):
    """Decorator-style cache check."""
    entry = _cache.get(key)
    if entry:
        data, ts = entry
        if time.time() - ts < ttl:
            return data
    return None


def _store(key: str, data):
    _cache[key] = (data, time.time())
    return data


# ═══════════════════════════════════════════════════════════
#  DATA FETCHERS
# ═══════════════════════════════════════════════════════════

def get_financial_data(ticker: str) -> dict | None:
    """ROE, ROA, margins, growth, target price dari yfinance."""
    key = f"financial_{ticker}"
    cached = _cached(key)
    if cached is not None:
        return cached

    try:
        t = _get_ticker(ticker)
        info = t.info
        if not info or info.get("regularMarketPrice") is None:
            return _store(key, None)

        data = {
            "returnOnEquity":        {"raw": info.get("returnOnEquity")},
            "returnOnAssets":        {"raw": info.get("returnOnAssets")},
            "profitMargins":         {"raw": info.get("profitMargins")},
            "operatingMargins":      {"raw": info.get("operatingMargins")},
            "revenueGrowth":         {"raw": info.get("revenueGrowth")},
            "earningsGrowth":        {"raw": info.get("earningsGrowth")},
            "currentRatio":          {"raw": info.get("currentRatio")},
            "debtToEquity":          {"raw": info.get("debtToEquity")},
            "targetMeanPrice":       {"raw": info.get("targetMeanPrice")},
            "recommendationMean":    {"raw": info.get("recommendationMean")},
            "freeCashflow":          {"raw": info.get("freeCashflow")},
            "totalRevenue":          {"raw": info.get("totalRevenue")},
            "grossProfits":          {"raw": info.get("grossProfits")},
        }
        return _store(key, data)
    except Exception as e:
        logger.warning(f"get_financial_data {ticker}: {e}")
        return _store(key, None)


def get_statistics(ticker: str) -> dict | None:
    """PER, PBV, DER, beta, market cap."""
    key = f"stats_{ticker}"
    cached = _cached(key)
    if cached is not None:
        return cached

    try:
        t = _get_ticker(ticker)
        info = t.info
        if not info:
            return _store(key, None)

        result = {
            "defaultKeyStatistics": {
                "trailingEps":          {"raw": info.get("trailingEps")},
                "forwardEps":           {"raw": info.get("forwardEps")},
                "priceToBook":          {"raw": info.get("priceToBook")},
                "beta":                 {"raw": info.get("beta")},
                "earningsGrowth":       {"raw": info.get("earningsGrowth")},
                "revenueGrowth":        {"raw": info.get("revenueGrowth")},
                "52WeekChange":         {"raw": info.get("52WeekChange")},
            },
            "financialData": {
                "debtToEquity":         {"raw": info.get("debtToEquity")},
                "currentRatio":         {"raw": info.get("currentRatio")},
                "returnOnEquity":       {"raw": info.get("returnOnEquity")},
            },
            "summaryDetail": {
                "trailingPE":           {"raw": info.get("trailingPE")},
                "forwardPE":            {"raw": info.get("forwardPE")},
                "dividendYield":        {"raw": info.get("dividendYield")},
                "marketCap":            {"raw": info.get("marketCap")},
                "volume":               {"raw": info.get("volume")},
            },
        }
        return _store(key, result)
    except Exception as e:
        logger.warning(f"get_statistics {ticker}: {e}")
        return _store(key, None)


def get_price(ticker: str) -> dict | None:
    """Harga, market cap, volume."""
    key = f"price_{ticker}"
    cached = _cached(key, ttl=300)  # 5 menit untuk harga
    if cached is not None:
        return cached

    try:
        t = _get_ticker(ticker)
        info = t.info
        if not info:
            return _store(key, None)

        data = {
            "regularMarketPrice":       {"raw": info.get("regularMarketPrice") or info.get("currentPrice")},
            "regularMarketVolume":      {"raw": info.get("regularMarketVolume")},
            "regularMarketChangePercent": {"raw": info.get("regularMarketChangePercent")},
            "marketCap":                {"raw": info.get("marketCap")},
            "shortName":                info.get("shortName", ticker),
            "currency":                 info.get("currency", "IDR"),
        }
        return _store(key, data)
    except Exception as e:
        logger.warning(f"get_price {ticker}: {e}")
        return _store(key, None)


def get_fundamentals(ticker: str) -> dict | None:
    """Sektor, industri, profil perusahaan."""
    key = f"profile_{ticker}"
    cached = _cached(key, ttl=86400)  # 24 jam
    if cached is not None:
        return cached

    try:
        t = _get_ticker(ticker)
        info = t.info
        if not info:
            return _store(key, None)

        data = {
            "sector":       info.get("sector", ""),
            "industry":     info.get("industry", ""),
            "longName":     info.get("longName", ""),
            "fullTimeEmployees": info.get("fullTimeEmployees"),
            "longBusinessSummary": info.get("longBusinessSummary", ""),
        }
        return _store(key, data)
    except Exception as e:
        logger.warning(f"get_fundamentals {ticker}: {e}")
        return _store(key, None)


def get_earnings(ticker: str) -> dict | None:
    """Data earnings historis."""
    key = f"earnings_{ticker}"
    cached = _cached(key, ttl=86400)
    if cached is not None:
        return cached

    try:
        t = _get_ticker(ticker)
        info = t.info
        data = {
            "earningsGrowth":    info.get("earningsGrowth"),
            "revenueGrowth":     info.get("revenueGrowth"),
            "trailingEps":       info.get("trailingEps"),
            "forwardEps":        info.get("forwardEps"),
        }
        return _store(key, data)
    except Exception as e:
        logger.warning(f"get_earnings {ticker}: {e}")
        return _store(key, None)


def get_chart(ticker: str, interval: str = "1d", range_: str = "5y") -> dict | None:
    """Data OHLCV historis untuk teknikal & seasonality."""
    key = f"chart_{ticker}_{range_}"
    cached = _cached(key, ttl=3600)
    if cached is not None:
        return cached

    try:
        t = _get_ticker(ticker)
        # Map range_ ke period yfinance
        period_map = {"5y": "5y", "1y": "1y", "6mo": "6mo", "3mo": "3mo", "1mo": "1mo"}
        period = period_map.get(range_, "5y")
        hist = t.history(period=period, interval=interval, auto_adjust=True)

        if hist.empty:
            return _store(key, None)

        # Format mirip Yahoo Finance chart API
        timestamps = [int(ts.timestamp()) for ts in hist.index]
        data = {
            "timestamp": timestamps,
            "indicators": {
                "quote": [{
                    "open":   hist["Open"].tolist(),
                    "high":   hist["High"].tolist(),
                    "low":    hist["Low"].tolist(),
                    "close":  hist["Close"].tolist(),
                    "volume": hist["Volume"].tolist(),
                }]
            },
            "meta": {
                "symbol": ticker,
                "currency": "IDR",
                "dataGranularity": interval,
            }
        }
        return _store(key, data)
    except Exception as e:
        logger.warning(f"get_chart {ticker}: {e}")
        return _store(key, None)


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
