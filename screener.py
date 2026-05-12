"""
Multi-Bagger Stock Screener - Main Runner (V2 - IDX Integrated)
Output: tabel CLI 5 Dimensi + Bandarmologi + Portfolio Allocation + CSV

Mode:
  default      : Pakai IDX_WATCHLIST dari config.py
  --mode=quick : Mandatory list + trending (35-50 saham, ~10 menit)
  --mode=smart : Auto-build universe IDX 100 terbaik (~20 menit)
  --mode=full  : Scan semua 868 saham IDX (~90+ menit, hati-hati quota!)
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import csv
import logging
from datetime import datetime
from analyzer import fetch_stock_data, score_stock, StockData
from config import IDX_WATCHLIST, OUTPUT_CSV, SCORE_THRESHOLD
from portfolio_engine import allocate_portfolio
from pre_filter import build_filtered_universe, build_full_universe_with_filter, MANDATORY_TICKERS
from filter_engine import FilterCriteria, parse_filters_from_args, apply_filters, print_filter_summary, get_filter_help

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    CYAN    = "\033[96m"
    MAGENTA = "\033[95m"
    BLUE    = "\033[94m"
    GREY    = "\033[90m"
    WHITE   = "\033[97m"

W = 120

def sep(char="─"): return C.GREY + char * W + C.RESET

def color_score(score: float) -> str:
    s = f"{score:5.1f}"
    if score >= SCORE_THRESHOLD["strong_buy"]: return f"{C.GREEN}{C.BOLD}{s}{C.RESET}"
    elif score >= SCORE_THRESHOLD["watch"]: return f"{C.YELLOW}{s}{C.RESET}"
    elif score > 0: return f"{C.RED}{s}{C.RESET}"
    return f"{C.GREY}  N/A{C.RESET}"

def color_signal(signal: str) -> str:
    if "MULTI" in signal: return f"{C.GREEN}{C.BOLD}{signal:<18}{C.RESET}"
    elif "WATCH" in signal: return f"{C.YELLOW}{signal:<18}{C.RESET}"
    return f"{C.GREY}{signal:<18}{C.RESET}"

def color_bandar(status: str) -> str:
    s = status.upper()
    if "ACCUM" in s: return f"{C.GREEN}{C.BOLD}{status}{C.RESET}"
    elif "NEUTRAL" in s: return f"{C.YELLOW}{status}{C.RESET}"
    elif "DIST" in s or "EXIT" in s: return f"{C.RED}{C.BOLD}{status}{C.RESET}"
    return f"{C.GREY}{status}{C.RESET}"

def fmt(val, suffix="", decimals=1):
    if val is None: return f"{C.GREY}N/A{C.RESET}"
    return f"{val:.{decimals}f}{suffix}"

def fmt_cap(val):
    if val is None: return f"{C.GREY}N/A{C.RESET}"
    if abs(val) >= 1e12: return f"{val/1e12:.1f}T"
    if abs(val) >= 1e9:  return f"{val/1e9:.1f}B"
    if abs(val) >= 1e6:  return f"{val/1e6:.1f}M"
    return f"{val:,.0f}"

def fmt_idr(val):
    if val >= 1e9:  return f"Rp {val/1e9:.1f} M"
    if val >= 1e6:  return f"Rp {val/1e6:.1f} Jt"
    return f"Rp {val:,.0f}"

def print_banner(total: int):
    print(f"\n{C.CYAN}{C.BOLD}{'=' * W}{C.RESET}")
    print(f"{C.CYAN}{C.BOLD}  5D STOCK SCREENER  |  Macro + Fundamental + Technical + Bandarmologi + Seasonality{C.RESET}")
    print(f"{C.CYAN}{C.BOLD}{'=' * W}{C.RESET}")
    print(f"  Waktu   : {C.WHITE}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{C.RESET}")
    print(f"  Saham   : {C.WHITE}{total} ticker{C.RESET}")
    print(f"  Scoring : Why(15) + What(45) + Where(15) + Who(15) + When(10) = 100")
    print(f"  Source  : {C.GREEN}IDX API{C.RESET} (Bandar/Tech) + {C.BLUE}Yahoo Finance{C.RESET} (Fund) + {C.MAGENTA}Gemini AI{C.RESET}")
    print(sep())

def print_table(results: list[StockData]):
    hdr = (
        f"{'TICKER':<10} {'SIGNAL':<19} {'SCORE':>6}  | "
        f"{'WHY':>4} {'WHAT':>4} {'WHERE':>5} {'WHO':>4} {'WHEN':>4} | "
        f"{'BANDAR':>10} {'RSI':>5} {'TRND':>8} "
        f"{'WIN%':>5}"
    )
    print(f"\n{C.BOLD}{hdr}{C.RESET}")
    print(sep("-"))

    for s in results:
        trend_short = s.trend[:8] if s.trend else "N/A"
        bandar_short = s.bandar_status[:10] if s.bandar_status else "N/A"
        print(
            f"{C.CYAN}{s.ticker:<10}{C.RESET}"
            f"{color_signal(s.signal)} "
            f"{color_score(s.total_score)}  | "
            f"{C.MAGENTA}{s.score_macro:>4.0f}{C.RESET} "
            f"{C.MAGENTA}{s.score_fundamental:>4.0f}{C.RESET} "
            f"{C.MAGENTA}{s.score_technical:>5.0f}{C.RESET} "
            f"{C.MAGENTA}{s.score_bandarmology:>4.0f}{C.RESET} "
            f"{C.MAGENTA}{s.score_seasonality:>4.0f}{C.RESET} | "
            f"{color_bandar(bandar_short):>10} "
            f"{fmt(s.rsi, ''):>5} "
            f"{trend_short:>8} "
            f"{fmt(s.seasonality_win_rate, '%'):>5}"
        )
    print(sep())

def print_detail_card(s: StockData):
    print(f"\n{C.BOLD}{C.BLUE}{'─'*70}{C.RESET}")
    print(f"  {C.BOLD}{C.WHITE}{s.ticker}{C.RESET}  {s.company_name}")
    print(f"  {C.GREY}{s.sector} | {s.industry}{C.RESET}")

    # 1. WHY (Macro)
    print(f"\n  {C.BOLD}{C.MAGENTA}[1. WHY] Kondisi Makro & Sektoral{C.RESET}")
    print(f"    Outlook Sektor  : {s.macro_outlook}")
    print(f"    Alasan          : {s.macro_reason}")
    print(f"    Skor Macro      : {s.score_macro} / 15")

    # 2. WHAT (Fundamental)
    ocf_fmt = fmt_cap(s.operating_cashflow) if s.operating_cashflow else f"{C.GREY}N/A{C.RESET}"
    fcf_fmt = fmt_cap(s.free_cashflow) if s.free_cashflow else f"{C.GREY}N/A{C.RESET}"
    
    print(f"\n  {C.BOLD}{C.MAGENTA}[2. WHAT] Fundamental Perusahaan{C.RESET}")
    print(f"    Valuasi         : PER {fmt(s.per, 'x')} | PBV {fmt(s.pbv, 'x')} | Cap {fmt_cap(s.market_cap)}")
    print(f"    Profitabilitas  : ROE {fmt(s.roe, '%')} | Net Margin {fmt(s.net_margin, '%')}")
    print(f"    Pertumbuhan     : Rev {fmt(s.revenue_growth, '%')} YoY | EPS {fmt(s.earnings_growth, '%')} YoY")
    print(f"    Kesehatan & Kas : DER {fmt(s.der, 'x')} | OCF: {ocf_fmt} | FCF: {fcf_fmt}")
    if s.eps_surprise_pct is not None:
        surprise_color = C.GREEN if s.eps_surprise_pct > 0 else C.RED
        print(f"    EPS Surprise    : {surprise_color}{s.eps_surprise_pct:+.2f}%{C.RESET} | Next Report: {s.next_earnings_date or 'N/A'}")
    if s.insight_good or s.insight_bad:
        print(f"    Insight Score   : {C.GREEN}{s.insight_good} Good{C.RESET} vs {C.RED}{s.insight_bad} Bad{C.RESET}")
    print(f"    Skor Fund       : {s.score_fundamental} / 45")

    # 3. WHERE (Technical)
    macd_color = C.GREEN if s.macd_signal == "BUY" else C.RED if s.macd_signal == "SELL" else C.YELLOW
    print(f"\n  {C.BOLD}{C.MAGENTA}[3. WHERE] Posisi Teknikal & Trend{C.RESET}")
    print(f"    Harga Saat Ini  : {fmt(s.current_price, ' IDR', 0)}")
    print(f"    Trend           : {s.trend}")
    print(f"    Moving Averages : SMA50 {fmt(s.sma50, '', 0)} | SMA200 {fmt(s.sma200, '', 0)}")
    print(f"    Momentum        : RSI {fmt(s.rsi, '')} | MACD: {macd_color}{s.macd_signal or 'N/A'}{C.RESET}")
    print(f"    Skor Teknikal   : {s.score_technical} / 15")

    # 4. WHO (Bandarmologi) — NEW!
    print(f"\n  {C.BOLD}{C.MAGENTA}[4. WHO] Bandarmologi & Smart Money{C.RESET}")
    print(f"    Status Bandar   : {color_bandar(s.bandar_status)} (skor: {fmt(s.bandar_score, '')})")
    if s.foreign_flow_7d:
        ff_color = C.GREEN if s.foreign_flow_7d > 0 else C.RED
        ff_label = "NET BUY" if s.foreign_flow_7d > 0 else "NET SELL"
        print(f"    Foreign Flow 7d : {ff_color}{ff_label} Rp {abs(s.foreign_flow_7d)/1e9:.1f} Miliar{C.RESET}")
    print(f"    Retail Danger   : {s.retail_danger}")
    if s.top_buyer_broker:
        print(f"    Top Buyer       : {C.GREEN}{s.top_buyer_broker}{C.RESET}")
    if s.top_seller_broker:
        print(f"    Top Seller      : {C.RED}{s.top_seller_broker}{C.RESET}")
    print(f"    Skor Bandar     : {s.score_bandarmology} / 15")

    # 5. WHEN (Seasonality)
    month = datetime.now().strftime("%B")
    print(f"\n  {C.BOLD}{C.MAGENTA}[5. WHEN] Siklus Waktu & Musiman{C.RESET}")
    print(f"    Win Rate Historis: {fmt(s.seasonality_win_rate, '%')} di bulan {month}")
    print(f"    Skor Waktu       : {s.score_seasonality} / 10")

    if s.red_flags or s.notes:
        print(f"\n  {C.BOLD}[Catatan & Red Flags]{C.RESET}")
        for n in s.notes: print(f"    {C.YELLOW}>> {n}{C.RESET}")
        for r in s.red_flags: print(f"    {C.RED}!! {r}{C.RESET}")

    print(f"\n  {C.BOLD}TOTAL SKOR 5D : {color_score(s.total_score)} / 100{C.RESET}")
    print(s.conclusion)


def print_portfolio(results: list[StockData], total_capital: float = 100_000_000):
    portfolio = allocate_portfolio(results, total_capital)
    if not portfolio:
        print(f"\n  {C.RED}Tidak ada saham yang memenuhi syarat portfolio (min skor 40).{C.RESET}")
        return
    
    print(f"\n{C.GREEN}{C.BOLD}{'=' * W}{C.RESET}")
    print(f"{C.GREEN}{C.BOLD}  REKOMENDASI ALOKASI PORTFOLIO  |  Modal: {fmt_idr(total_capital)}{C.RESET}")
    print(f"{C.GREEN}{C.BOLD}{'=' * W}{C.RESET}")
    
    print(f"\n  {C.BOLD}{'No':<4} {'TICKER':<12} {'BOBOT':>7} {'ALOKASI':>16} {'STRATEGI':<14} {'CATATAN ENTRY'}{C.RESET}")
    print(f"  {C.GREY}{'-'*106}{C.RESET}")
    
    for i, p in enumerate(portfolio, 1):
        if p.strategy == "AGGRESSIVE": strat_color = C.GREEN
        elif p.strategy == "MODERATE": strat_color = C.YELLOW
        elif p.strategy == "CONSERVATIVE": strat_color = C.CYAN
        else: strat_color = C.GREY
        
        bar = ("█" if p.ticker != "CASH" else "░") * int(p.weight_pct / 3)
        tk = f"{C.WHITE}{C.BOLD}{p.ticker:<12}{C.RESET}" if p.ticker != "CASH" else f"{C.GREY}{p.ticker:<12}{C.RESET}"
        
        print(f"  {i:<4}{tk}{strat_color}{p.weight_pct:>6.1f}%{C.RESET} {C.WHITE}{fmt_idr(p.allocation_idr):>16}{C.RESET} {strat_color}{p.strategy:<14}{C.RESET} {p.entry_note}")
        print(f"  {'':>4}{'':>12}{strat_color}{bar}{C.RESET}")
    
    total_inv = sum(p.allocation_idr for p in portfolio if p.ticker != "CASH")
    cash_res = sum(p.allocation_idr for p in portfolio if p.ticker == "CASH")
    n = len([p for p in portfolio if p.ticker != "CASH"])
    
    print(f"\n  {C.GREY}{'─'*60}{C.RESET}")
    print(f"  {C.BOLD}Ringkasan:{C.RESET} {n} emiten | Investasi: {C.GREEN}{fmt_idr(total_inv)}{C.RESET} | Cash: {C.YELLOW}{fmt_idr(cash_res)}{C.RESET}")
    print(f"{C.GREEN}{C.BOLD}{'=' * W}{C.RESET}")


def export_csv(results: list[StockData]):
    fieldnames = [
        "ticker", "company_name", "sector", "signal", "total_score",
        "score_macro", "score_fundamental", "score_technical", "score_bandarmology", "score_seasonality",
        "roe", "per", "pbv", "der", "revenue_growth", "earnings_growth",
        "operating_cashflow", "free_cashflow", "rsi", "trend", "macd_signal",
        "bandar_status", "foreign_flow_7d", "retail_danger",
        "seasonality_win_rate", "eps_surprise_pct", "macro_outlook", "red_flags"
    ]
    try:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for s in results:
                writer.writerow({
                    "ticker": s.ticker, "company_name": s.company_name,
                    "sector": s.sector, "signal": s.signal, "total_score": s.total_score,
                    "score_macro": s.score_macro, "score_fundamental": s.score_fundamental,
                    "score_technical": s.score_technical, "score_bandarmology": s.score_bandarmology,
                    "score_seasonality": s.score_seasonality,
                    "roe": s.roe, "per": s.per, "pbv": s.pbv, "der": s.der,
                    "revenue_growth": s.revenue_growth, "earnings_growth": s.earnings_growth,
                    "operating_cashflow": s.operating_cashflow, "free_cashflow": s.free_cashflow,
                    "rsi": s.rsi, "trend": s.trend, "macd_signal": s.macd_signal,
                    "bandar_status": s.bandar_status, "foreign_flow_7d": s.foreign_flow_7d,
                    "retail_danger": s.retail_danger, "seasonality_win_rate": s.seasonality_win_rate,
                    "eps_surprise_pct": s.eps_surprise_pct, "macro_outlook": s.macro_outlook,
                    "red_flags": " | ".join(s.red_flags),
                })
        print(f"\n  {C.GREEN}[OK] Hasil disimpan ke: {OUTPUT_CSV}{C.RESET}")
    except Exception as e:
        logger.error(f"CSV export error: {e}")


def run_screener(tickers=None, capital=100_000_000, filters: FilterCriteria = None):
    if tickers is None: tickers = IDX_WATCHLIST
    print_banner(len(tickers))
    
    results = []
    for i, t in enumerate(tickers, 1):
        print(f"{C.GREY}[{i:>2}/{len(tickers)}]{C.RESET} 5D Analisis {C.CYAN}{t:<10}{C.RESET}", end="", flush=True)
        try:
            stock = fetch_stock_data(t)
            stock = score_stock(stock)
            results.append(stock)
            print(f" {color_signal(stock.signal)} {color_score(stock.total_score)}")
        except Exception as e:
            print(f" {C.RED}ERROR: {e}{C.RESET}")
            logger.error(f"{t}: {e}")

    results.sort(key=lambda x: x.total_score, reverse=True)
    
    # Terapkan filter jika ada
    display_results = results
    if filters:
        filtered = apply_filters(results, filters)
        print_filter_summary(filters, len(results), len(filtered))
        display_results = filtered
    
    print_table(display_results)
    
    worthy = [s for s in display_results if s.total_score >= SCORE_THRESHOLD["watch"]]
    for s in worthy: print_detail_card(s)
    
    print_portfolio(display_results, capital)
    export_csv(display_results)

if __name__ == "__main__":
    import sys as _sys
    args = _sys.argv[1:]
    
    # Help flag
    if "--help" in args or "-h" in args:
        print(get_filter_help())
        print("\nMode Options:")
        print("  --mode=quick   Mandatory + trending (~50 saham, ~10 menit)")
        print("  --mode=smart   Auto-build 100 kandidat terbaik (~20 menit)")
        print("  --mode=full    Scan semua 868 saham IDX (~90 menit!)")
        print("  --capital=N    Modal portofolio dalam IDR (default: 100.000.000)")
        print("\nContoh:")
        print("  python screener.py --mode=quick --bandar=ACCUMULATING --min-roe=15")
        print("  python screener.py BBCA.JK BBRI.JK TLKM.JK --capital=50000000")
        _sys.exit(0)

    capital = 100_000_000
    mode = "default"
    tickers = []

    # Parse non-filter args
    FILTER_PREFIXES = (
        "--sector=", "--min-roe=", "--max-per=", "--min-score=",
        "--min-cap=", "--bandar=", "--signal=", "--min-winrate=",
        "--max-der=", "--min-margin=", "--foreign="
    )
    for a in args:
        if a.startswith("--capital="):
            try: capital = float(a.split("=")[1].replace("_", ""))
            except: pass
        elif a.startswith("--mode="):
            mode = a.split("=")[1].lower()
        elif not any(a.startswith(p) for p in FILTER_PREFIXES) and not a.startswith("--"):
            tickers.append(a)

    # Parse filter criteria
    filters = parse_filters_from_args(args)
    # Hanya aktifkan filter object jika ada filter yang diset
    has_filters = any([
        filters.sector, filters.min_roe, filters.max_per,
        filters.min_score > 0, filters.min_cap_miliar,
        filters.bandar_status, filters.signal, filters.min_winrate,
        filters.max_der, filters.min_margin, filters.foreign_flow
    ])

    # Pilih universe berdasarkan mode
    if tickers:
        final_tickers = tickers
    elif mode == "quick":
        print(f"\033[96m[MODE] QUICK: Mandatory list + trending hari ini...\033[0m")
        final_tickers = build_filtered_universe(max_stocks=60)
    elif mode == "smart":
        print(f"\033[96m[MODE] SMART: Auto-build 100 kandidat terbaik IDX...\033[0m")
        final_tickers = build_filtered_universe(max_stocks=100)
    elif mode == "full":
        print(f"\033[93m[MODE] FULL: Scan semua 868 saham IDX (butuh ~90 menit!)\033[0m")
        final_tickers = build_full_universe_with_filter(max_stocks=200)
    else:
        final_tickers = IDX_WATCHLIST

    run_screener(final_tickers, capital, filters if has_filters else None)

