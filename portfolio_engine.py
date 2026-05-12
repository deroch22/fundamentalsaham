"""
PORTFOLIO ALLOCATOR ENGINE
Membagi bobot investasi otomatis berdasarkan skor 4D.
Logika: Semakin tinggi skor total & semakin sedikit red flag,
semakin besar alokasi portfolio-nya.
"""

from dataclasses import dataclass, field


@dataclass
class PortfolioSlot:
    ticker: str
    company_name: str
    score: float
    signal: str
    weight_pct: float = 0.0       # Bobot portfolio (%)
    allocation_idr: float = 0.0   # Nominal rupiah yang dialokasikan
    strategy: str = ""            # Strategi entry (Aggressive / Moderate / Conservative)
    entry_note: str = ""          # Catatan entry


def allocate_portfolio(results: list, total_capital: float = 100_000_000) -> list[PortfolioSlot]:
    """
    Bagi portfolio berdasarkan skor 4D.
    
    Args:
        results: List of StockData dari screener
        total_capital: Modal total (default 100 juta IDR)
    
    Returns:
        List of PortfolioSlot dengan bobot & alokasi
    """
    
    # Filter: Hanya saham dengan skor >= 40 yang layak masuk portfolio
    MIN_SCORE = 40
    candidates = [s for s in results if s.total_score >= MIN_SCORE]
    
    if not candidates:
        return []
    
    # Hitung raw weight berdasarkan skor (kuadratik: saham skor tinggi dapat porsi jauh lebih besar)
    raw_weights = {}
    for s in candidates:
        # Penalty multiplier untuk red flags
        penalty = max(0.3, 1.0 - len(s.red_flags) * 0.15)
        raw_weights[s.ticker] = (s.total_score ** 1.5) * penalty
    
    total_raw = sum(raw_weights.values())
    
    portfolio = []
    for s in candidates:
        weight = (raw_weights[s.ticker] / total_raw) * 100
        alloc = total_capital * (weight / 100)
        
        # Tentukan strategi entry
        if s.total_score >= 75:
            strategy = "AGGRESSIVE"
            entry_note = "Langsung akumulasi. Entry full position."
        elif s.total_score >= 60:
            strategy = "MODERATE"
            entry_note = "Cicil masuk 3 tahap (30%/30%/40%). Tunggu pullback ke SMA 50."
        else:
            strategy = "CONSERVATIVE"
            entry_note = "Entry kecil dulu (max 20% posisi). Tunggu konfirmasi reversal."
        
        # Cap single stock max 35% portfolio
        weight = min(weight, 35.0)
        
        portfolio.append(PortfolioSlot(
            ticker=s.ticker,
            company_name=s.company_name,
            score=s.total_score,
            signal=s.signal,
            weight_pct=round(weight, 1),
            allocation_idr=round(alloc),
            strategy=strategy,
            entry_note=entry_note,
        ))
    
    # Re-normalize setelah capping
    total_w = sum(p.weight_pct for p in portfolio)
    if total_w > 0:
        for p in portfolio:
            p.weight_pct = round((p.weight_pct / total_w) * 100, 1)
            p.allocation_idr = round(total_capital * (p.weight_pct / 100))
    
    # Sort by weight descending
    portfolio.sort(key=lambda x: x.weight_pct, reverse=True)
    
    # Sisa alokasi jadi Cash Buffer
    used_pct = sum(p.weight_pct for p in portfolio)
    if used_pct < 100:
        cash_pct = round(100 - used_pct, 1)
        portfolio.append(PortfolioSlot(
            ticker="CASH",
            company_name="Cash Buffer (Warchest)",
            score=0,
            signal="RESERVE",
            weight_pct=cash_pct,
            allocation_idr=round(total_capital * (cash_pct / 100)),
            strategy="DEFENSIVE",
            entry_note="Dana cadangan untuk averaging down atau peluang mendadak.",
        ))
    
    return portfolio
