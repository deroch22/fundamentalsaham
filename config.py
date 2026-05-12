# ============================================================
# KONFIGURASI BOT ANALISIS FUNDAMENTAL SAHAM
# Multi-Bagger Screener — Railway Edition
# ============================================================
# Di Railway: set via Environment Variables (Settings → Variables)
# Di lokal  : isi langsung atau buat file .env
# ============================================================

import os

# === API CREDENTIALS ===
# Yahoo Finance (legacy, untuk seasonality chart 5 tahun)
RAPIDAPI_KEY  = os.environ.get("RAPIDAPI_KEY",  "f4847705f4msh2a3160f9508003dp1575a8jsnc195177821ee")
RAPIDAPI_HOST = os.environ.get("RAPIDAPI_HOST", "yahoo-finance166.p.rapidapi.com")

# IDX API (primary source: bandarmologi, teknikal, sentimen, earnings)
IDX_API_KEY = os.environ.get("IDX_API_KEY", "579e737afemshf2a850aeb8c8d67p1fc4dbjsnf3d2389897ab")
IDX_HOST    = os.environ.get("IDX_HOST",    "indonesia-stock-exchange-idx.p.rapidapi.com")

# Gemini AI
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDZ8LnsEItmJqkKJHoutYDo7RdfVohXKd4")

# === TELEGRAM BOT ===
# Di Railway: tambahkan TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID di Variables
# Di lokal  : isi langsung di bawah, atau export sebagai env var
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "ISI_TOKEN_TELEGRAM_BOT_LO")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "")

# === DAFTAR SAHAM IDX YANG AKAN DI-SCREEN ===
# Format: TICKER.JK (Yahoo Finance format untuk IDX)
# Default: 100 saham pilihan dari semua sektor utama IDX
# Untuk screening lebih luas: python screener.py --mode=smart / --mode=full
IDX_WATCHLIST = [
    # ── PERBANKAN (Big 4 + Syariah)
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "BRIS.JK",
    "BJTM.JK", "BDMN.JK", "NISP.JK", "MEGA.JK", "AGRO.JK",

    # ── CONSUMER STAPLES
    "UNVR.JK", "ICBP.JK", "INDF.JK", "MYOR.JK", "SIDO.JK",
    "ULTJ.JK", "CLEO.JK", "DMND.JK", "FOOD.JK",

    # ── CONSUMER DISCRETIONARY / RETAIL
    "ACES.JK", "MAPI.JK", "ERAA.JK", "LPPF.JK", "RALS.JK",
    "HERO.JK", "AMRT.JK", "MIDI.JK",

    # ── HEALTHCARE & FARMASI
    "KLBF.JK", "HEAL.JK", "MIKA.JK", "SIDO.JK", "PRDA.JK",
    "DVLA.JK", "TSPC.JK", "PYFA.JK",

    # ── TEKNOLOGI & DIGITAL
    "GOTO.JK", "BUKA.JK", "EMTK.JK", "DMMX.JK", "INET.JK",

    # ── TELEKOMUNIKASI
    "TLKM.JK", "ISAT.JK", "EXCL.JK", "FREN.JK",

    # ── ENERGI & BATUBARA
    "ADRO.JK", "PTBA.JK", "ITMG.JK", "BYAN.JK", "HRUM.JK",
    "KKGI.JK", "GEMS.JK",

    # ── MINYAK & GAS
    "MEDC.JK", "ENRG.JK", "RUIS.JK",

    # ── NIKEL, MINERAL & LOGAM
    "INCO.JK", "ANTM.JK", "TINS.JK", "MDKA.JK", "NCKL.JK",
    "AMMN.JK",

    # ── INFRASTRUKTUR & KONSTRUKSI
    "JSMR.JK", "WIKA.JK", "PTPP.JK", "ADHI.JK", "WSKT.JK",

    # ── PROPERTI
    "BSDE.JK", "SMRA.JK", "CTRA.JK", "PWON.JK", "LPKR.JK",

    # ── SEMEN & MATERIAL BANGUNAN
    "SMGR.JK", "INTP.JK", "WSBP.JK",

    # ── OTOMOTIF & KOMPONEN
    "ASII.JK", "AUTO.JK", "SMSM.JK",

    # ── AGRIKULTUR & PERKEBUNAN
    "AALI.JK", "LSIP.JK", "SSMS.JK", "TBLA.JK",

    # ── POULTRY & PAKAN TERNAK
    "CPIN.JK", "JPFA.JK", "MAIN.JK",

    # ── KIMIA & INDUSTRI DASAR
    "TPIA.JK", "BRPT.JK", "DPNS.JK",

    # ── PACKAGING & KAYU
    "WOOD.JK", "INKP.JK", "TKIM.JK",

    # ── INVESTASI / HOLDING
    "PGAS.JK", "MARK.JK", "CMRY.JK",
]

# === KRITERIA SCORING MULTI-BAGGER ===
SCREENING_CRITERIA = {
    # --- GROWTH (bobot 40%) ---
    "min_revenue_growth_yoy": 15.0,        # % pertumbuhan revenue minimal
    "min_earnings_growth_yoy": 20.0,       # % pertumbuhan EPS minimal
    "ideal_revenue_growth": 30.0,          # % revenue growth = skor penuh

    # --- PROFITABILITAS (bobot 30%) ---
    "min_roe": 15.0,                       # ROE minimal %
    "ideal_roe": 25.0,                     # ROE ideal = skor penuh
    "min_net_margin": 8.0,                 # Net profit margin minimal %

    # --- VALUASI (bobot 20%) ---
    "max_per": 30.0,                       # PER maksimal (price to earnings)
    "max_pbv": 5.0,                        # PBV maksimal (price to book)
    "max_peg": 1.5,                        # PEG ratio (PER / growth)

    # --- KESEHATAN KEUANGAN (bobot 10%) ---
    "max_der": 1.5,                        # Debt to equity maksimal
    "min_current_ratio": 1.2,             # Current ratio minimal
}

# === SCORING THRESHOLD ===
SCORE_THRESHOLD = {
    "strong_buy": 70,     # 🟢 Multi-bagger candidate kuat
    "watch":      50,     # 🟡 Pantau terus
    "skip":        0,     # 🔴 Skip dulu
}

# === OUTPUT SETTINGS ===
OUTPUT_CSV = "hasil_screening.csv"
OUTPUT_LOG = "screening_log.txt"
