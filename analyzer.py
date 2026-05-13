"""
Fundamental Analyzer + 6-Dimensional Engine (UPGRADED)
Macro, Fundamental, Technical, Seasonality, Bandarmologi, Earnings Quality
Hybrid: IDX API (primary) + Yahoo Finance (supplementary)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

# Yahoo Finance (legacy - fundamental & seasonality)
from api_client import (
    get_financial_data, get_statistics, get_price,
    get_fundamentals, get_earnings, get_chart, safe_raw
)
# IDX API (primary - bandarmologi, teknikal, sentimen, earnings forecast)
import idx_client

from config import SCREENING_CRITERIA, SCORE_THRESHOLD, GEMINI_API_KEY
from google import genai

# Setup Gemini AI (new SDK: google-genai)
# Model chain berdasarkan live test:
gemini_client = None
GEMINI_MODELS = [
    "gemini-3-flash-preview",    # ✅ OK — cepat, Pro-level
    "gemini-3.1-flash-lite",     # ✅ OK — fallback hemat
    "gemini-2.5-flash",          # ✅ OK — last resort stabil
    "gemini-3.1-pro-preview",    # 503 sering — coba paling akhir
]

if GEMINI_API_KEY and GEMINI_API_KEY != "ISI_API_KEY_GEMINI_LO_DISINI":
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Gemini init gagal: {e}")

from macro_engine import analyze_macro
from technical_engine import analyze_technical
from time_engine import analyze_seasonality

logger = logging.getLogger(__name__)


# ─── DATA STRUCTURES ────────────────────────────────────────

@dataclass
class Officer:
    name: str
    title: str
    age: Optional[int] = None
    total_pay: Optional[float] = None


@dataclass
class ManagementAnalysis:
    officers: list = field(default_factory=list)
    avg_age: Optional[float] = None
    has_ceo: bool = False
    ceo_name: str = ""
    ceo_age: Optional[int] = None
    total_officers: int = 0
    avg_pay_idr: Optional[float] = None
    score: float = 0.0


@dataclass
class EarningsBeat:
    quarter: str
    actual: Optional[float] = None
    estimate: Optional[float] = None
    surprise_pct: Optional[float] = None
    beat: bool = False


@dataclass
class StockData:
    ticker: str
    company_name: str = ""
    sector: str = ""
    industry: str = ""
    website: str = ""
    description: str = ""

    # Fundamental (What)
    current_price: Optional[float] = None
    target_mean_price: Optional[float] = None
    upside_pct: Optional[float] = None
    market_cap: Optional[float] = None
    
    per: Optional[float] = None
    pbv: Optional[float] = None
    peg: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    net_margin: Optional[float] = None
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None
    operating_cashflow: Optional[float] = None
    free_cashflow: Optional[float] = None
    der: Optional[float] = None
    current_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    analyst_recommendation: str = ""

    earnings_history: list = field(default_factory=list)
    beat_rate: Optional[float] = None

    management: ManagementAnalysis = field(default_factory=ManagementAnalysis)
    
    # Macro (Why)
    macro_outlook: str = "Neutral"
    macro_reason: str = ""
    
    # Technical (Where) - Now from IDX API!
    rsi: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    trend: str = "Unknown"
    volume_spike: bool = False
    macd_signal: str = ""
    macd_histogram: Optional[float] = None
    
    # Seasonality (When)
    seasonality_win_rate: Optional[float] = None

    # ═══ NEW: Bandarmologi (Who) - from IDX API ═══
    bandar_status: str = "N/A"        # ACCUMULATING / DISTRIBUTING / EXITING / NEUTRAL
    bandar_score: Optional[float] = None
    foreign_flow_7d: Optional[float] = None  # Net foreign flow 7 hari (IDR)
    retail_danger: str = "N/A"        # LOW / MEDIUM / HIGH
    retail_fomo_score: Optional[float] = None
    top_buyer_broker: str = ""
    top_seller_broker: str = ""
    accumulation_score: Optional[float] = None

    # ═══ NEW: Earnings Forecast - from IDX API ═══
    eps_forecast_2026: Optional[float] = None
    eps_forecast_2027: Optional[float] = None
    eps_surprise_pct: Optional[float] = None
    
    # ═══ NEW: Corporate Actions ═══
    corporate_actions: list = field(default_factory=list)
    next_earnings_date: str = ""

    # ═══ NEW: Insight Scores - from IDX API ═══
    insight_good: int = 0
    insight_bad: int = 0
    insight_score: int = 0

    # 4D SCORING (Max 100)
    score_macro: float = 0.0          # Max 15
    score_fundamental: float = 0.0    # Max 45
    score_technical: float = 0.0      # Max 15
    score_seasonality: float = 0.0    # Max 10
    score_bandarmology: float = 0.0   # Max 15 (NEW!)
    total_score: float = 0.0
    
    signal: str = "? No Data"
    red_flags: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    conclusion: str = ""


# ─── FETCH & POPULATE ───────────────────────────────────────

def fetch_stock_data(ticker: str) -> StockData:
    """Ambil semua data dari IDX API + Yahoo Finance dan jalankan 6 Dimensi."""
    stock = StockData(ticker=ticker)
    
    # Strip .JK for IDX API (IDX uses BBCA, Yahoo uses BBCA.JK)
    idx_ticker = ticker.replace(".JK", "")

    # ═══════════════════════════════════════════════
    # PHASE 1: IDX API (Primary Source)
    # ═══════════════════════════════════════════════
    
    # 1A. Emiten Info (harga, volume, sektor, orderbook)
    emiten = idx_client.get_emiten_info(idx_ticker)
    if emiten:
        stock.company_name = emiten.get("name", ticker)
        stock.current_price = _safe_float(emiten.get("close") or emiten.get("lastTradedPrice"))
        stock.sector = emiten.get("sector", "")
        stock.industry = emiten.get("subSector", "") or emiten.get("industry", "")
    
    # 1B. Technical Analysis (RSI, MACD, SMA - pre-calculated!)
    tech_idx = idx_client.get_technical_analysis(idx_ticker)
    if tech_idx:
        indicators = tech_idx.get("indicators", {})
        sma_data = indicators.get("sma", {})
        rsi_data = indicators.get("rsi", {})
        macd_data = indicators.get("macd", {})
        
        stock.rsi = rsi_data.get("value")
        stock.sma50 = sma_data.get("sma50")
        stock.sma200 = sma_data.get("sma200")
        stock.macd_signal = macd_data.get("signal", "")
        stock.macd_histogram = macd_data.get("histogram")
        
        # Determine trend from SMA
        if stock.current_price and stock.sma50 and stock.sma200:
            if stock.current_price > stock.sma50 > stock.sma200:
                stock.trend = "Strong Uptrend"
            elif stock.current_price > stock.sma200:
                stock.trend = "Uptrend"
            elif stock.current_price < stock.sma50 < stock.sma200:
                stock.trend = "Strong Downtrend"
            else:
                stock.trend = "Downtrend"
        elif stock.current_price and stock.sma50:
            stock.trend = "Uptrend" if stock.current_price > stock.sma50 else "Downtrend"
        
        # Score technical (max 10, will be scaled later)
        tech_score = 0
        if stock.rsi:
            if 40 <= stock.rsi <= 70: tech_score += 3
            elif stock.rsi < 30: 
                tech_score += 2
                stock.notes.append("RSI Oversold — potensi rebound")
            elif stock.rsi > 80:
                stock.notes.append("RSI Overbought — hati-hati koreksi")
        if "Uptrend" in stock.trend: tech_score += 4
        if stock.macd_signal == "BUY": tech_score += 3
        elif stock.macd_signal == "NEUTRAL": tech_score += 1
        
        stock.score_technical = round(min(tech_score * 1.5, 15), 1)
    
    # 1C. Bandar Sentiment (BANDARMOLOGI!)
    sentiment = idx_client.get_bandar_sentiment(idx_ticker)
    if sentiment:
        bandar = sentiment.get("bandar_sentiment", {})
        retail = sentiment.get("retail_sentiment", {})
        
        stock.bandar_status = bandar.get("status", "N/A")
        stock.bandar_score = bandar.get("score")
        stock.accumulation_score = bandar.get("indicators", {}).get("accumulation_score")
        stock.foreign_flow_7d = bandar.get("indicators", {}).get("foreign_flow")
        
        stock.retail_danger = retail.get("danger_level", "N/A")
        stock.retail_fomo_score = retail.get("indicators", {}).get("fomo_score")
        
        # Top brokers
        top_buyers = bandar.get("top_brokers", {}).get("buyers", [])
        top_sellers = bandar.get("top_brokers", {}).get("sellers", [])
        if top_buyers:
            stock.top_buyer_broker = f"{top_buyers[0].get('code','')} ({top_buyers[0].get('type','')}) {top_buyers[0].get('net_value_formatted','')}"
        if top_sellers:
            stock.top_seller_broker = f"{top_sellers[0].get('code','')} ({top_sellers[0].get('type','')}) {top_sellers[0].get('net_value_formatted','')}"
        
        # Score bandarmologi (Max 15)
        bscore = 0
        status = stock.bandar_status.upper()
        if "ACCUMULATING" in status: bscore += 8
        elif "NEUTRAL" in status: bscore += 4
        elif "DISTRIBUTING" in status or "EXITING" in status:
            stock.red_flags.append(f"BANDAR {status}! Smart money sedang keluar.")
        
        if stock.foreign_flow_7d and stock.foreign_flow_7d > 0:
            bscore += 4
            stock.notes.append(f"Foreign Net BUY 7d: Rp {stock.foreign_flow_7d/1e9:.1f}M")
        elif stock.foreign_flow_7d and stock.foreign_flow_7d < 0:
            stock.notes.append(f"Foreign Net SELL 7d: Rp {abs(stock.foreign_flow_7d)/1e9:.1f}M")
        
        if stock.retail_danger == "HIGH":
            bscore -= 2
            stock.red_flags.append("Retail Danger HIGH — FOMO retail berlebihan!")
        elif stock.retail_danger == "LOW":
            bscore += 3
            
        stock.score_bandarmology = round(max(0, min(bscore, 15)), 1)
        
    # 1E. Corporate Actions Calendar
    try:
        corp_cal = idx_client.get_all_corporate_actions()
        if corp_cal and idx_ticker in corp_cal:
            stock.corporate_actions = corp_cal[idx_ticker]
            for action in stock.corporate_actions:
                stock.notes.append(f"Aksi Korporasi Terdekat: {action}")
    except Exception as e:
        logger.warning(f"Gagal get corporate actions untuk {idx_ticker}: {e}")
    
    # 1F. Earnings Forecast
    earnings_idx = idx_client.get_earnings(idx_ticker)
    if earnings_idx:
        latest = earnings_idx.get("latestActual", {})
        stock.eps_surprise_pct = latest.get("epsSurprisePercent")
        stock.next_earnings_date = earnings_idx.get("summary", {}).get("expectedReportDate", "")[:10]
        
        forecast = earnings_idx.get("forecast", {}).get("annual", {})
        if "2026" in forecast:
            stock.eps_forecast_2026 = forecast["2026"].get("EpsForecast")
        if "2027" in forecast:
            stock.eps_forecast_2027 = forecast["2027"].get("EpsForecast")
    
    # 1E. Insights (valuation scores vs peers)
    insights = idx_client.get_insights(idx_ticker)
    if insights:
        summary = insights.get("summary", {})
        stock.insight_good = summary.get("good", 0)
        stock.insight_bad = summary.get("bad", 0)
        stock.insight_score = summary.get("score", 0)

    # ═══════════════════════════════════════════════
    # PHASE 2: YAHOO FINANCE (Supplementary)
    # ═══════════════════════════════════════════════
    
    # 2A. Fundamentals & Profile
    profile = get_fundamentals(ticker)
    if profile:
        if not stock.sector: stock.sector = profile.get("sector", "")
        if not stock.industry: stock.industry = profile.get("industry", "")
        stock.website = profile.get("website", "")
        stock.description = profile.get("longBusinessSummary", "")[:300]
        stock.management = _parse_management(profile)

    # 2B. Macro (Why)
    if stock.sector:
        macro_res = analyze_macro(stock.sector, stock.industry)
        stock.macro_outlook = macro_res["outlook"]
        stock.macro_reason = macro_res["reason"]
        stock.score_macro = round(macro_res["score"] * 1.5, 1)

    # 2C. Financial Data & Stats (What - fundamental details)
    fin = get_financial_data(ticker)
    if fin:
        if not stock.current_price:
            stock.current_price = safe_raw(fin, "currentPrice")
        stock.target_mean_price = safe_raw(fin, "targetMeanPrice")
        stock.roe = _pct(safe_raw(fin, "returnOnEquity"))
        stock.roa = _pct(safe_raw(fin, "returnOnAssets"))
        stock.net_margin = _pct(safe_raw(fin, "profitMargins"))
        stock.revenue_growth = _pct(safe_raw(fin, "revenueGrowth"))
        stock.earnings_growth = _pct(safe_raw(fin, "earningsGrowth"))
        stock.operating_cashflow = safe_raw(fin, "operatingCashflow")
        stock.free_cashflow = safe_raw(fin, "freeCashflow")
        stock.current_ratio = safe_raw(fin, "currentRatio")
        stock.dividend_yield = _pct(safe_raw(fin, "dividendYield"))
        stock.analyst_recommendation = safe_raw(fin, "recommendationKey") or ""

        der_raw = safe_raw(fin, "debtToEquity")
        stock.der = round(der_raw / 100, 3) if der_raw is not None else None

        if stock.current_price and stock.target_mean_price:
            stock.upside_pct = round(
                (stock.target_mean_price - stock.current_price) / stock.current_price * 100, 1
            )

    stats = get_statistics(ticker)
    if stats:
        ks = stats.get("defaultKeyStatistics", {})
        sd = stats.get("summaryDetail", {})
        stock.per = safe_raw(sd, "trailingPE") or safe_raw(ks, "trailingEps")
        stock.pbv = safe_raw(ks, "priceToBook")
        stock.peg = safe_raw(ks, "pegRatio")
        stock.market_cap = safe_raw(sd, "marketCap")

    price_data = get_price(ticker)
    if price_data:
        if not stock.current_price:
            stock.current_price = safe_raw(price_data, "regularMarketPrice")
        if not stock.company_name or stock.company_name == ticker:
            stock.company_name = safe_raw(price_data, "shortName") or stock.company_name

    # 2D. Chart 5Y untuk Seasonality (When) + fallback technical
    chart_daily = get_chart(ticker, interval="1d", range_="5y")
    if chart_daily:
        # Seasonality
        seas_res = analyze_seasonality(chart_daily)
        stock.seasonality_win_rate = seas_res["win_rate"]
        stock.score_seasonality = seas_res["score"]
        stock.notes.extend(seas_res["notes"])
        
        # Fallback technical jika IDX API gagal
        if not tech_idx:
            tech_res = analyze_technical(chart_daily)
            stock.rsi = tech_res["rsi"]
            stock.sma50 = tech_res["sma50"]
            stock.sma200 = tech_res["sma200"]
            stock.trend = tech_res["trend"]
            stock.volume_spike = tech_res.get("volume_spike", False)
            stock.score_technical = round(tech_res["score"] * 1.5, 1)
            stock.notes.extend(tech_res["notes"])

    return stock


# ─── PARSERS ────────────────────────────────────────────────

def _parse_management(profile: dict) -> ManagementAnalysis:
    mgmt = ManagementAnalysis()
    officers = profile.get("companyOfficers", [])
    mgmt.total_officers = len(officers)
    ages, pays = [], []

    for o in officers:
        name  = o.get("name", "Unknown")
        title = o.get("title", "")
        age   = o.get("age")
        pay   = safe_raw(o, "totalPay")

        mgmt.officers.append(Officer(name=name, title=title, age=age, total_pay=pay))
        if age: ages.append(age)
        if pay: pays.append(pay)

        if "ceo" in title.lower() or "chief executive" in title.lower() or "direktur utama" in title.lower():
            mgmt.has_ceo = True
            mgmt.ceo_name = name
            mgmt.ceo_age  = age

    if ages: mgmt.avg_age = round(sum(ages) / len(ages), 1)
    if pays: mgmt.avg_pay_idr = round(sum(pays) / len(pays))
    return mgmt

def _pct(value) -> Optional[float]:
    if value is None: return None
    try: return round(float(value) * 100, 2)
    except: return None

def _safe_float(value) -> Optional[float]:
    if value is None: return None
    try:
        if isinstance(value, str):
            return float(value.replace(",", ""))
        return float(value)
    except: return None


# ─── SCORING ENGINE ─────────────────────────────────────────

def score_stock(stock: StockData) -> StockData:
    """
    Hitung fundamental score dan gabungkan ke total score.
    Bobot: Macro(15) + Fund(45) + Tech(15) + Bandar(15) + Season(10) = 100
    """
    red_flags = []
    f = 0.0  # Max 45
    
    # 1. Growth (Max 15)
    rg = stock.revenue_growth
    if rg is not None:
        if rg >= 25: f += 7.5
        elif rg >= 10: f += 7.5 * (rg - 10) / 15
        elif rg < 0: red_flags.append(f"Revenue drop {rg:.1f}%")
        
    eg = stock.earnings_growth
    if eg is not None:
        if eg >= 35: f += 7.5
        elif eg >= 15: f += 7.5 * (eg - 15) / 20
        elif eg < -20: red_flags.append(f"Laba drop {eg:.1f}%")

    # 2. Profitability (Max 12)
    roe = stock.roe
    if roe is not None:
        if roe >= 20: f += 8
        elif roe >= 10: f += 8 * (roe - 10) / 10
        elif roe < 5: red_flags.append(f"ROE mini ({roe:.1f}%)")
        
    nm = stock.net_margin
    if nm is not None:
        if nm >= 15: f += 4
        elif nm >= 5: f += 4 * (nm - 5) / 10

    # 3. Valuation (Max 12)
    per = stock.per
    if per is not None and per > 0:
        if per <= 12: f += 8
        elif per <= 25: f += 8 * (25 - per) / 13
        else: stock.notes.append(f"PER mahal ({per:.1f}x)")
        
    pbv = stock.pbv
    if pbv is not None and pbv > 0:
        if pbv <= 1.5: f += 4
        elif pbv <= 3: f += 4 * (3 - pbv) / 1.5

    # 4. Health & Cash Flow (Max 6)
    der = stock.der
    if der is not None:
        if der <= 0.5: f += 4
        elif der <= 1.5: f += 4 * (1.5 - der) / 1.0
        else: red_flags.append(f"Hutang gawat DER={der:.2f}x")
        
    ocf = stock.operating_cashflow
    if ocf is not None and ocf < 0:
        red_flags.append("WARNING: Operating Cash Flow NEGATIF!")
    
    if stock.eps_surprise_pct and stock.eps_surprise_pct > 0:
        f += min(2, stock.eps_surprise_pct * 0.5)

    stock.score_fundamental = round(min(f, 45), 1)
    
    # TOTAL SCORE 5 DIMENSI
    raw_total = (
        stock.score_macro + 
        stock.score_fundamental + 
        stock.score_technical + 
        stock.score_bandarmology +
        stock.score_seasonality
    )
    
    penalty = len(red_flags) * 4
    stock.total_score = round(max(0, min(raw_total - penalty, 100)), 1)
    
    stock.red_flags.extend(red_flags)

    t = SCORE_THRESHOLD
    if stock.total_score >= t["strong_buy"]:
        stock.signal = "[**] MULTI-BAGGER"
    elif stock.total_score >= t["watch"]:
        stock.signal = "[~]  WATCH"
    else:
        stock.signal = "[-]  SKIP"

    stock.conclusion = _generate_conclusion(stock)

    return stock

def _generate_conclusion(s: StockData) -> str:
    """Generate narasi kesimpulan 5 Dimensi menggunakan Gemini AI."""
    
    import datetime
    month = datetime.datetime.now().strftime("%B")
    
    if not gemini_client:
        return f"\n[Auto] Skor {s.total_score}/100. Fund {s.score_fundamental}/45, " \
               f"Tech {s.score_technical}/15, Bandar: {s.bandar_status}, Season {s.seasonality_win_rate or 0}%"

    # Format foreign flow
    ff = "N/A"
    if s.foreign_flow_7d:
        ff = f"Net {'BUY' if s.foreign_flow_7d > 0 else 'SELL'} Rp {abs(s.foreign_flow_7d)/1e9:.1f}M (7 hari)"

    corp_str = "\\n- ".join(s.corporate_actions) if s.corporate_actions else "Tidak ada"

    prompt = f"""
Kamu adalah mentor saham yang menjelaskan ke PEMULA (orang yang baru belajar saham).
Buatkan kesimpulan untuk saham {s.ticker} ({s.company_name}).

DATA ANALISIS:
- Harga sekarang: Rp {s.current_price}
- SMA50 (rata-rata 50 hari): {s.sma50}, SMA200 (rata-rata 200 hari): {s.sma200}
- RSI: {s.rsi} (di bawah 30 = murah, di atas 70 = mahal)
- Trend: {s.trend}
- MACD: {s.macd_signal}

- ROE (keuntungan perusahaan): {s.roe}%
- PER (mahal/murahnya): {s.per}x (di bawah 15 = murah)
- PBV: {s.pbv}x
- DER (utang): {s.der}x (di bawah 1 = sehat)
- Pertumbuhan laba: {s.earnings_growth}%
- Net Margin: {s.net_margin}%

- Bandar (pemain besar): {s.bandar_status} (skor {s.bandar_score}/10)
- Asing 7 hari: {ff}
- Retail Danger: {s.retail_danger}

- Seasonality bulan {month}: Win rate {s.seasonality_win_rate}%
- Aksi Korporasi Terdekat: {corp_str}
- Red Flags: {', '.join(s.red_flags) if s.red_flags else 'Tidak ada'}

Skor Total: {s.total_score}/100

FORMAT WAJIB (ikuti persis):

[emoji] VERDICT: [BUY / WATCH & WAIT / HOLD / SELL/AVOID]

📝 Penjelasan Simpel:
[2-3 kalimat sederhana kenapa saham ini layak/tidak layak. Pakai bahasa sehari-hari, hindari jargon. Jelaskan seolah ke teman yang baru belajar saham.]

💰 Target Harga:
• Beli di: Rp [harga entry ideal, biasanya di area support/SMA terdekat]
• Target jual: Rp [target profit realistis]
• Stop loss: Rp [batas rugi, biasanya 5-8% di bawah entry]

⚡ Tips:
[1 kalimat tips praktis untuk saham ini]

ATURAN:
- Emoji verdict: 🚀 (BUY), 👀 (WATCH), ✋ (HOLD), ❌ (SELL/AVOID)
- Harga entry/target/stoploss HARUS angka bulat realistis berdasarkan data teknikal
- Bahasa Indonesia kasual, JANGAN pakai istilah rumit
- SINGKAT, maksimal 8 baris total
"""


    try:
        import time as _time
        last_error = None
        for model in GEMINI_MODELS:
            for attempt in range(2):
                try:
                    response = gemini_client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=genai.types.GenerateContentConfig(
                            max_output_tokens=800,
                            # Gemini 3: jangan set temperature, biarkan default 1.0
                            # thinking_level=low → lebih cepat untuk analisis saham
                            thinking_config=genai.types.ThinkingConfig(
                                thinking_level="low"
                            ) if "gemini-3" in model else None,
                        )
                    )
                    return f"\n🤖 Gemini AI Insight:\n{response.text.strip()}"
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    if "503" in err_str or "unavailable" in err_str or "overload" in err_str:
                        # Model overload — coba fallback
                        logger.warning(f"Gemini {model} overload, coba model lain...")
                        break
                    elif attempt == 0:
                        logger.warning(f"Gemini {model} retry: {e}")
                        _time.sleep(2)
                    else:
                        break
        raise last_error
    except Exception as e:
        logger.error(f"Gemini API Error: {e}")
        narrative = ""
        if s.score_fundamental >= 30: narrative += "Fundamental solid. "
        elif s.score_fundamental >= 15: narrative += "Fundamental cukup. "
        else: narrative += "Fundamental lemah. "
        if "Uptrend" in s.trend: narrative += "Teknikal mendukung. "
        else: narrative += f"Teknikal: {s.trend}. "
        narrative += f"Bandar: {s.bandar_status}. "
        if s.foreign_flow_7d and s.foreign_flow_7d > 0: narrative += "Asing masuk. "
        elif s.foreign_flow_7d and s.foreign_flow_7d < 0: narrative += "Asing keluar. "
        return f"\n📊 Kesimpulan (Auto):\n{narrative}"
