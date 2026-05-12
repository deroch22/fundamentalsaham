"""
Filter Engine - Post-Analysis Filtering & Custom Universe Builder
User bisa filter hasil screening berdasarkan berbagai kriteria.

Cara pakai CLI:
  python screener.py --sector=Perbankan
  python screener.py --min-roe=20 --max-per=15
  python screener.py --bandar=ACCUMULATING
  python screener.py --min-score=65
  python screener.py --min-cap=5000 --sector=Teknologi
  python screener.py --signal=MULTI-BAGGER
  python screener.py --mode=smart --bandar=ACCUMULATING --min-roe=15

Filter yang tersedia:
  --sector=NAME          Nama sektor (bisa partial, case-insensitive)
                         Contoh: Perbankan, Teknologi, Kesehatan, Energi
  --min-roe=N            ROE minimal N% (default: tidak ada batas)
  --max-per=N            PER maksimal N (default: tidak ada batas)
  --min-score=N          Skor 5D minimal N (default: 0)
  --min-cap=N            Market cap minimal N Miliar IDR
  --bandar=STATUS        Filter bandar status: ACCUMULATING/NEUTRAL/HOLDING
  --signal=TYPE          Filter signal: MULTI-BAGGER/WATCH/SKIP
  --min-winrate=N        Seasonality win rate minimal N%
  --max-der=N            DER (hutang) maksimal N
  --min-margin=N         Net margin minimal N%
  --foreign=BUY          Foreign flow: BUY (masuk) atau SELL (keluar)
"""

from dataclasses import dataclass
from typing import Optional
from analyzer import StockData


@dataclass
class FilterCriteria:
    """Kriteria filter yang bisa dikustomisasi user."""
    sector: Optional[str] = None           # Partial match, case-insensitive
    min_roe: Optional[float] = None
    max_per: Optional[float] = None
    min_score: float = 0.0
    min_cap_miliar: Optional[float] = None # Dalam Miliar IDR
    bandar_status: Optional[str] = None    # ACCUMULATING/NEUTRAL/HOLDING/EXITING
    signal: Optional[str] = None          # MULTI-BAGGER/WATCH/SKIP
    min_winrate: Optional[float] = None
    max_der: Optional[float] = None
    min_margin: Optional[float] = None
    foreign_flow: Optional[str] = None    # BUY atau SELL


def parse_filters_from_args(args: list[str]) -> FilterCriteria:
    """
    Parse CLI arguments ke FilterCriteria object.
    
    Args:
        args: list argv (sudah tanpa script name)
    
    Returns:
        FilterCriteria dengan nilai yang diisi dari args
    """
    fc = FilterCriteria()
    
    for arg in args:
        if not arg.startswith("--"): continue
        if "=" not in arg: continue
        
        key, val = arg[2:].split("=", 1)
        key = key.lower()
        
        try:
            if key == "sector":
                fc.sector = val
            elif key == "min-roe":
                fc.min_roe = float(val)
            elif key == "max-per":
                fc.max_per = float(val)
            elif key == "min-score":
                fc.min_score = float(val)
            elif key == "min-cap":
                fc.min_cap_miliar = float(val)
            elif key == "bandar":
                fc.bandar_status = val.upper()
            elif key == "signal":
                fc.signal = val.upper()
            elif key == "min-winrate":
                fc.min_winrate = float(val)
            elif key == "max-der":
                fc.max_der = float(val)
            elif key == "min-margin":
                fc.min_margin = float(val)
            elif key == "foreign":
                fc.foreign_flow = val.upper()
        except ValueError:
            pass
    
    return fc


def apply_filters(stocks: list[StockData], fc: FilterCriteria) -> list[StockData]:
    """
    Terapkan filter ke list StockData.
    
    Args:
        stocks: Hasil 5D analysis
        fc: FilterCriteria dari user
    
    Returns:
        List StockData yang lolos semua filter
    """
    filtered = []
    
    for s in stocks:
        # 1. Sector filter (partial match)
        if fc.sector:
            sector_str = f"{s.sector} {s.industry}".lower()
            if fc.sector.lower() not in sector_str:
                continue
        
        # 2. ROE minimum
        if fc.min_roe is not None:
            if s.roe is None or s.roe < fc.min_roe:
                continue
        
        # 3. PER maksimum
        if fc.max_per is not None:
            if s.per is None or s.per > fc.max_per:
                continue
        
        # 4. Total score minimum
        if s.total_score < fc.min_score:
            continue
        
        # 5. Market cap minimum (dalam Miliar)
        if fc.min_cap_miliar is not None:
            cap_miliar = (s.market_cap or 0) / 1e9
            if cap_miliar < fc.min_cap_miliar:
                continue
        
        # 6. Bandar status
        if fc.bandar_status:
            if fc.bandar_status not in (s.bandar_status or "").upper():
                continue
        
        # 7. Signal filter
        if fc.signal:
            if fc.signal not in (s.signal or "").upper():
                continue
        
        # 8. Win rate minimum
        if fc.min_winrate is not None:
            if s.seasonality_win_rate is None or s.seasonality_win_rate < fc.min_winrate:
                continue
        
        # 9. DER maksimum
        if fc.max_der is not None:
            if s.der is None or s.der > fc.max_der:
                continue
        
        # 10. Net margin minimum
        if fc.min_margin is not None:
            if s.net_margin is None or s.net_margin < fc.min_margin:
                continue
        
        # 11. Foreign flow filter
        if fc.foreign_flow:
            ff = s.foreign_flow_7d or 0
            if fc.foreign_flow == "BUY" and ff <= 0:
                continue
            if fc.foreign_flow == "SELL" and ff >= 0:
                continue
        
        filtered.append(s)
    
    return filtered


def print_filter_summary(fc: FilterCriteria, before: int, after: int):
    """Print ringkasan filter yang diterapkan."""
    active = []
    
    if fc.sector: active.append(f"Sektor: '{fc.sector}'")
    if fc.min_roe: active.append(f"Min ROE: {fc.min_roe}%")
    if fc.max_per: active.append(f"Max PER: {fc.max_per}x")
    if fc.min_score > 0: active.append(f"Min Score: {fc.min_score}")
    if fc.min_cap_miliar: active.append(f"Min Cap: {fc.min_cap_miliar:.0f} Miliar")
    if fc.bandar_status: active.append(f"Bandar: {fc.bandar_status}")
    if fc.signal: active.append(f"Signal: {fc.signal}")
    if fc.min_winrate: active.append(f"Min WinRate: {fc.min_winrate}%")
    if fc.max_der: active.append(f"Max DER: {fc.max_der}x")
    if fc.min_margin: active.append(f"Min Margin: {fc.min_margin}%")
    if fc.foreign_flow: active.append(f"Foreign: {fc.foreign_flow}")
    
    if not active:
        return
    
    print(f"\n  \033[96m[FILTER AKTIF] {' | '.join(active)}\033[0m")
    print(f"  \033[96mHasil: {before} saham → {after} saham setelah filter\033[0m")


def get_filter_help() -> str:
    """Return help text untuk filter options."""
    return """
Filter Options (tambahkan ke CLI):
  --sector=NAME       Sektor: Perbankan, Teknologi, Kesehatan, Energi, dll
  --min-roe=N         ROE minimal N% (contoh: --min-roe=20)
  --max-per=N         PER maksimal N (contoh: --max-per=15)
  --min-score=N       Skor 5D minimal N/100 (contoh: --min-score=60)
  --min-cap=N         Market cap minimal N Miliar (contoh: --min-cap=5000)
  --bandar=STATUS     Bandar status: ACCUMULATING, NEUTRAL, HOLDING
  --signal=TYPE       Signal: MULTI-BAGGER, WATCH
  --min-winrate=N     Win rate musiman minimal N% (contoh: --min-winrate=70)
  --max-der=N         DER (hutang) maksimal N (contoh: --max-der=1.0)
  --min-margin=N      Net margin minimal N% (contoh: --min-margin=10)
  --foreign=BUY/SELL  Foreign flow arah (contoh: --foreign=BUY)

Contoh kombinasi:
  python screener.py --mode=smart --bandar=ACCUMULATING --min-roe=15 --foreign=BUY
  python screener.py --sector=Perbankan --min-score=60 --max-per=12
  python screener.py --signal=MULTI-BAGGER --min-winrate=70
"""
