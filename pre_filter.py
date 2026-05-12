"""
Pre-Filter Engine - Smart Universe Selection
Strategi: Dari 868 saham IDX → filter ke ~100 kandidat terbaik
sebelum dijalankan full 5D analysis.

Kriteria pre-filter (data ringan, 1 API call per saham):
- Market Cap minimal (hindari micro-cap gorengan)
- Sektor aktif (bukan shell company / suspensi)
- Masuk index utama (LQ45, IDX80, IHSG30, dll)
- Data tersedia di Yahoo Finance (.JK)
"""

import http.client
import json
import time
import logging

logger = logging.getLogger(__name__)

IDX_API_KEY = "579e737afemshf2a850aeb8c8d67p1fc4dbjsnf3d2389897ab"
IDX_HOST = "indonesia-stock-exchange-idx.p.rapidapi.com"

# Saham yang WAJIB masuk (blue chip + high conviction list)
MANDATORY_TICKERS = [
    "BBCA", "BBRI", "BMRI", "BBNI", "BRIS",       # Perbankan Top
    "TLKM", "ISAT", "EXCL",                         # Telco
    "UNVR", "ICBP", "INDF", "MYOR", "SIDO",         # Consumer
    "KLBF", "HEAL", "MIKA",                          # Healthcare
    "ADRO", "PTBA", "ITMG", "INCO",                 # Energi/Tambang
    "ACES", "MAPI", "ERAA", "LPPF",                 # Retail
    "GOTO", "EMTK",                                  # Digital
    "CPIN", "JPFA", "CMRY",                          # Agri/Food
    "SMGR", "WOOD",                                  # Material
    "MARK", "ULTJ",                                  # Small cap potensial
]

# Index utama IDX (saham yang masuk index ini otomatis prioritas)
PRIORITY_INDEXES = {
    "LQ45", "IDX30", "IDX80", "IDXHIDIV20",
    "IDXQ30", "KOMPAS100", "BISNIS-27", "IDXG30"
}

# Sektor yang SKIP (biasanya banyak shell company)
SKIP_SECTORS = {"N/A", "", "Lainnya"}

# Market cap minimum (Rp 500 Miliar)
MIN_MARKET_CAP = 500_000_000_000


def _req(path: str) -> dict | None:
    """Single API call ke IDX."""
    conn = http.client.HTTPSConnection(IDX_HOST, timeout=10)
    h = {"x-rapidapi-key": IDX_API_KEY, "x-rapidapi-host": IDX_HOST}
    try:
        conn.request("GET", path, headers=h)
        r = conn.getresponse()
        raw = r.read().decode("utf-8")
        data = json.loads(raw)
        return data if data.get("success") else None
    except Exception as e:
        logger.debug(f"Pre-filter req error: {e}")
        return None
    finally:
        conn.close()


def get_all_idx_symbols() -> list[str]:
    """Ambil semua 868 simbol dari IDX API."""
    data = _req("/api/main/symbols")
    if data and isinstance(data.get("data"), list):
        return data["data"]
    return []


def get_trending_symbols() -> list[str]:
    """Ambil saham trending hari ini."""
    data = _req("/api/main/trending")
    if not data: return []
    # Struktur: data.data = list of {symbol, name, percent, ...}
    items = data.get("data", [])
    if isinstance(items, dict):
        items = items.get("data", [])
    result = []
    for item in (items or []):
        s = item.get("symbol", "") if isinstance(item, dict) else str(item)
        if s: result.append(s.replace(".JK", ""))
    return result


def get_top_movers() -> list[str]:
    """Ambil top gainer + top loser (volume tinggi = aktif)."""
    symbols = []
    for endpoint in ["/api/movers/top-gainer", "/api/movers/top-loser"]:
        data = _req(endpoint)
        if not data: continue
        # Struktur: data.data.mover_list = list of stocks
        inner = data.get("data", {})
        if isinstance(inner, dict):
            inner = inner.get("data", {})
        if isinstance(inner, dict):
            items = inner.get("mover_list", [])
        elif isinstance(inner, list):
            items = inner
        else:
            items = []
        for item in items[:10]:
            if isinstance(item, dict):
                s = item.get("symbol", "") or item.get("ticker", "") or item.get("stock_code", "")
                if s: symbols.append(s.replace(".JK", ""))
    return symbols


def check_emiten_quick(ticker: str) -> dict | None:
    """
    Ambil info emiten dengan 1 API call.
    Return dict dengan info penting atau None jika skip.
    """
    data = _req(f"/api/emiten/{ticker}/info")
    time.sleep(0.8)  # Rate limit BASIC
    if not data: return None
    
    return {
        "ticker": ticker,
        "name": data.get("name", ticker),
        "sector": data.get("sector", ""),
        "indexes": data.get("indexes", []),
        "market_cap": _safe_float(data.get("marketCap") or data.get("mktcap")),
        "price": _safe_float(data.get("close") or data.get("lastTradedPrice")),
    }


def _safe_float(val) -> float | None:
    try: return float(val)
    except: return None


def build_filtered_universe(max_stocks: int = 100) -> list[str]:
    """
    Bangun universe saham terfilter dari 868 → max_stocks kandidat.
    
    Prioritas:
    1. Mandatory list (blue chip & high conviction)
    2. Trending hari ini
    3. Top movers (volume aktif)  
    4. Quick scan sektor/market cap (jika kuota masih ada)
    
    Return: List ticker format TICKER.JK untuk Yahoo Finance
    """
    logger.info("Membangun universe saham...")
    
    candidates = set()
    
    # 1. Mandatory (selalu masuk)
    candidates.update(MANDATORY_TICKERS)
    logger.info(f"  Mandatory: {len(MANDATORY_TICKERS)} saham")
    
    # 2. Trending today
    trending = get_trending_symbols()
    candidates.update(trending[:20])
    logger.info(f"  Trending: +{len(trending[:20])} saham")
    time.sleep(1)
    
    # 3. Top movers
    movers = get_top_movers()
    candidates.update(movers[:20])
    logger.info(f"  Movers: +{len(movers[:20])} saham")
    time.sleep(1)
    
    # Batasi ke max_stocks
    candidates = list(candidates)[:max_stocks]
    
    # Convert ke format Yahoo Finance (.JK)
    return [f"{t}.JK" for t in candidates]


def build_full_universe_with_filter(max_stocks: int = 150) -> list[str]:
    """
    Mode LENGKAP: Scan semua 868 saham dengan quick check,
    filter berdasarkan market cap & index membership.
    Warning: butuh ~15-20 menit.
    
    Return: List ticker format TICKER.JK
    """
    print("\n⚠️  Mode FULL SCAN: mengecek semua saham IDX...")
    print("    Estimasi waktu: ~20 menit (868 saham × 0.8 detik)")
    
    all_symbols = get_all_idx_symbols()
    if not all_symbols:
        logger.error("Gagal ambil daftar simbol IDX!")
        return [f"{t}.JK" for t in MANDATORY_TICKERS]
    
    time.sleep(1)
    
    filtered = []
    mandatory_set = set(MANDATORY_TICKERS)
    
    for i, ticker in enumerate(all_symbols, 1):
        # Mandatory langsung masuk tanpa cek
        if ticker in mandatory_set:
            filtered.append({"ticker": ticker, "priority": 1})
            continue
        
        # Quick check untuk yang lain (1 API call)
        info = check_emiten_quick(ticker)
        if not info:
            continue
        
        # Filter market cap
        mc = info.get("market_cap")
        if mc and mc < MIN_MARKET_CAP:
            continue
        
        # Filter sektor
        if info.get("sector") in SKIP_SECTORS:
            continue
        
        # Bonus jika masuk index prioritas
        idx_member = set(info.get("indexes", []))
        priority = 2 if idx_member & PRIORITY_INDEXES else 3
        
        filtered.append({"ticker": ticker, "priority": priority, **info})
        
        if i % 50 == 0:
            print(f"    Progress: {i}/{len(all_symbols)} scanned, {len(filtered)} candidates...")
    
    # Sort by priority, ambil top N
    filtered.sort(key=lambda x: x.get("priority", 99))
    top = filtered[:max_stocks]
    
    print(f"\n✅ Filter selesai: {len(all_symbols)} → {len(top)} kandidat")
    return [f"{t['ticker']}.JK" for t in top]
