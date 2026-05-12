"""
Telegram Bot - Push Alert Hasil Screening IDX ke HP
Fitur:
  - /scan         : Jalankan screening default (IDX_WATCHLIST)
  - /quick        : Mode quick (trending + mandatory)
  - /filter       : Custom filter via pesan
  - /top5         : Top 5 saham terbaik hari ini
  - /bandar BBCA  : Cek bandarmologi 1 saham spesifik
  - /help         : Daftar perintah
  - Auto-push     : Jadwal screening pagi (07:00 WIB) otomatis
"""

import logging
import asyncio
import os
from datetime import datetime, time as dt_time

from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    IDX_WATCHLIST, SCORE_THRESHOLD
)
from analyzer import fetch_stock_data, score_stock, StockData
from filter_engine import FilterCriteria, apply_filters
from pre_filter import build_filtered_universe
import idx_client

import sys

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING,     # Hanya WARNING ke atas yang dilog
    stream=sys.stdout          # Railway: stdout = info, bukan error
)
# Kurangi noise dari httpx & telegram internals
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("telegram").setLevel(logging.ERROR)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ─── FORMATTERS ─────────────────────────────────────────────

def signal_emoji(signal: str) -> str:
    if "MULTI" in signal: return "🚀"
    elif "WATCH" in signal: return "👀"
    return "❌"

def bandar_emoji(status: str) -> str:
    s = status.upper()
    if "ACCUM" in s: return "🟢"
    elif "HOLDING" in s: return "🟡"
    elif "DIST" in s or "EXIT" in s: return "🔴"
    return "⚪"

def format_score_bar(score: float, max_score: float = 100) -> str:
    filled = int((score / max_score) * 10)
    return "█" * filled + "░" * (10 - filled)

def fmt_idr(val: float) -> str:
    if abs(val) >= 1e12: return f"Rp {val/1e12:.1f}T"
    if abs(val) >= 1e9:  return f"Rp {val/1e9:.1f}M"
    if abs(val) >= 1e6:  return f"Rp {val/1e6:.1f}Jt"
    return f"Rp {val:,.0f}"


def format_stock_card(s: StockData, rank: int = None, short: bool = False) -> str:
    """Format kartu 1 saham untuk Telegram (Markdown)."""
    sig_emoji = signal_emoji(s.signal)
    rank_str = f"#{rank} " if rank else ""
    
    # Header
    lines = [
        f"{sig_emoji} *{rank_str}{s.ticker}* — {s.company_name}",
        f"📊 Skor 5D: *{s.total_score:.1f}/100* `{format_score_bar(s.total_score)}`",
    ]
    
    if short:
        # Mode ringkas untuk top5
        lines += [
            f"   Why {s.score_macro:.0f} | What {s.score_fundamental:.0f} | Where {s.score_technical:.0f} | Who {s.score_bandarmology:.0f} | When {s.score_seasonality:.0f}",
            f"   {bandar_emoji(s.bandar_status)} Bandar: *{s.bandar_status}* | RSI: {s.rsi:.1f}" if s.rsi else f"   {bandar_emoji(s.bandar_status)} Bandar: *{s.bandar_status}*",
        ]
        if s.foreign_flow_7d:
            ff_dir = "📈" if s.foreign_flow_7d > 0 else "📉"
            lines.append(f"   {ff_dir} Foreign: {fmt_idr(abs(s.foreign_flow_7d))} ({'masuk' if s.foreign_flow_7d > 0 else 'keluar'})")
        return "\n".join(lines)
    
    # Mode detail
    lines += [
        f"",
        f"📐 *Breakdown Skor:*",
        f"   WHY (Macro)    : {s.score_macro:.0f}/15 — {s.macro_outlook}",
        f"   WHAT (Fund)    : {s.score_fundamental:.0f}/45 — ROE {s.roe or 'N/A'}% | PER {s.per or 'N/A'}x",
        f"   WHERE (Tech)   : {s.score_technical:.0f}/15 — {s.trend} | RSI {s.rsi or 'N/A'}",
        f"   WHO (Bandar)   : {s.score_bandarmology:.0f}/15 — {bandar_emoji(s.bandar_status)} {s.bandar_status}",
        f"   WHEN (Season)  : {s.score_seasonality:.0f}/10 — Win {s.seasonality_win_rate or 'N/A'}% di {datetime.now().strftime('%B')}",
        f"",
        f"🏦 *Bandarmologi:*",
        f"   Status: {bandar_emoji(s.bandar_status)} *{s.bandar_status}*",
    ]
    
    if s.foreign_flow_7d:
        ff_dir = "📈 NET BUY" if s.foreign_flow_7d > 0 else "📉 NET SELL"
        lines.append(f"   Foreign 7d: {ff_dir} {fmt_idr(abs(s.foreign_flow_7d))}")
    
    if s.top_buyer_broker:
        lines.append(f"   Top Buyer: {s.top_buyer_broker}")
    if s.top_seller_broker:
        lines.append(f"   Top Seller: {s.top_seller_broker}")
    lines.append(f"   Retail Danger: {s.retail_danger}")
    
    if s.red_flags:
        lines += ["", "⚠️ *Red Flags:*"]
        for r in s.red_flags[:3]:
            lines.append(f"   ‼️ {r}")
    
    if s.eps_surprise_pct is not None:
        surprise_dir = "↑" if s.eps_surprise_pct > 0 else "↓"
        lines.append(f"\n📈 EPS Surprise: {surprise_dir} {s.eps_surprise_pct:+.1f}%")
    
    return "\n".join(lines)


def format_screening_summary(results: list[StockData], title: str = "Hasil Screening") -> str:
    """Format ringkasan semua hasil untuk Telegram."""
    multibagger = [s for s in results if "MULTI" in s.signal]
    watch = [s for s in results if "WATCH" in s.signal]
    skip = [s for s in results if "SKIP" in s.signal]
    
    now = datetime.now().strftime("%d %b %Y %H:%M WIB")
    lines = [
        f"📊 *{title}*",
        f"🕐 {now}",
        f"Total: {len(results)} saham",
        f"",
        f"🚀 MULTI-BAGGER ({len(multibagger)}): {', '.join(s.ticker.replace('.JK','') for s in multibagger) or 'Tidak ada'}",
        f"👀 WATCH ({len(watch)}): {', '.join(s.ticker.replace('.JK','') for s in watch) or 'Tidak ada'}",
        f"❌ SKIP ({len(skip)}): {len(skip)} saham",
    ]
    
    if multibagger or watch:
        lines += ["", "─" * 30, "🏆 *TOP PICKS:*"]
        top_picks = (multibagger + watch)[:5]
        for i, s in enumerate(top_picks, 1):
            lines.append(format_stock_card(s, rank=i, short=True))
            lines.append("")
    
    return "\n".join(lines)


# ─── SCREENER RUNNER ────────────────────────────────────────

async def run_screening_async(
    tickers: list[str],
    filters: FilterCriteria = None,
    progress_cb=None          # async callback(done, total, latest_ticker)
) -> list[StockData]:
    """Jalankan screening di background thread dengan live progress."""
    loop = asyncio.get_event_loop()
    results = []
    total = len(tickers)

    for i, t in enumerate(tickers, 1):
        try:
            stock = await loop.run_in_executor(None, lambda tk=t: score_stock(fetch_stock_data(tk)))
            results.append(stock)
        except Exception as e:
            logger.error(f"Error {t}: {e}")

        # Update progress setiap 5 saham atau di saham terakhir
        if progress_cb and (i % 5 == 0 or i == total):
            try:
                await progress_cb(i, total, t.replace(".JK", ""))
            except Exception:
                pass

    results.sort(key=lambda x: x.total_score, reverse=True)
    if filters:
        results = apply_filters(results, filters)
    return results



# ─── COMMAND HANDLERS ────────────────────────────────────────

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏆 Top 5 Hari Ini", callback_data="top5"),
         InlineKeyboardButton("⚡ Quick Scan", callback_data="quick")],
        [InlineKeyboardButton("📊 Full Scan 100 Saham", callback_data="scan")],
        [InlineKeyboardButton("🏦 Cek Bandar", callback_data="menu_bandar"),
         InlineKeyboardButton("🔍 Cek Saham", callback_data="menu_cek")],
        [InlineKeyboardButton("🎯 Filter & Screener", callback_data="menu_filter")],
        [InlineKeyboardButton("❓ Help", callback_data="help")],
    ])

def filter_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏢 Filter Sektor", callback_data="menu_sektor")],
        [InlineKeyboardButton("🟢 Bandar Akumulasi", callback_data="filter_accum"),
         InlineKeyboardButton("💰 Asing Masuk", callback_data="filter_foreign")],
        [InlineKeyboardButton("🔴 Bandar Distribusi", callback_data="filter_distrib"),
         InlineKeyboardButton("📉 Asing Keluar", callback_data="filter_foreign_sell")],
        [InlineKeyboardButton("🚀 Multi-Bagger Only", callback_data="filter_multibagger")],
        [InlineKeyboardButton("💎 ROE > 20% + PER < 15", callback_data="filter_value")],
        [InlineKeyboardButton("📈 Momentum (Score > 65)", callback_data="filter_momentum")],
        [InlineKeyboardButton("🔙 Menu Utama", callback_data="main_menu")],
    ])

def sektor_keyboard():
    sektors = [
        ("🏦 Perbankan",    "sektor_Perbankan"),
        ("📱 Teknologi",    "sektor_Teknologi"),
        ("🏥 Kesehatan",    "sektor_Kesehatan"),
        ("⚡ Energi",       "sektor_Energi"),
        ("🌾 Agrikultur",   "sektor_Agrikultur"),
        ("🏗️ Konstruksi",  "sektor_Konstruksi"),
        ("🏠 Properti",     "sektor_Properti"),
        ("📡 Telekomunikasi","sektor_Telekomunikasi"),
        ("🚗 Otomotif",     "sektor_Otomotif"),
        ("🛒 Konsumer",     "sektor_Konsumer"),
        ("⛏️ Tambang",     "sektor_Tambang"),
        ("🧪 Kimia/Industri","sektor_Kimia"),
    ]
    rows = [[InlineKeyboardButton(label, callback_data=cb)] for label, cb in sektors]
    rows.append([InlineKeyboardButton("🔙 Filter Menu", callback_data="menu_filter")])
    return InlineKeyboardMarkup(rows)

# Mapping sektor → saham (tanpa .JK)
SEKTOR_TICKERS = {
    "Perbankan":      ["BBCA","BBRI","BMRI","BBNI","BRIS","BJTM","BDMN","NISP","MEGA","AGRO"],
    "Konsumer":       ["UNVR","ICBP","INDF","MYOR","SIDO","ULTJ","DMND","ACES","MAPI","ERAA","LPPF","RALS","AMRT","MIDI"],
    "Kesehatan":      ["KLBF","HEAL","MIKA","PRDA","DVLA","TSPC"],
    "Teknologi":      ["GOTO","BUKA","EMTK"],
    "Telekomunikasi": ["TLKM","ISAT","EXCL"],
    "Energi":         ["ADRO","PTBA","ITMG","BYAN","HRUM","KKGI","GEMS","MEDC","ENRG","RUIS"],
    "Tambang":        ["INCO","ANTM","TINS","MDKA","NCKL","AMMN"],
    "Konstruksi":     ["JSMR","WIKA","PTPP","ADHI","WSKT"],
    "Properti":       ["BSDE","SMRA","CTRA","PWON","LPKR","SMGR","INTP","WSBP"],
    "Otomotif":       ["ASII","AUTO","SMSM"],
    "Agrikultur":     ["AALI","LSIP","SSMS","TBLA","CPIN","JPFA","MAIN"],
    "Industri":       ["TPIA","BRPT","DPNS","WOOD","INKP","TKIM","PGAS","MARK","CMRY"],
}

SEKTOR_EMOJI = {
    "Perbankan": "🏦", "Konsumer": "🛒", "Kesehatan": "🏥",
    "Teknologi": "📱", "Telekomunikasi": "📡", "Energi": "⚡",
    "Tambang": "⛏️", "Konstruksi": "🏗️", "Properti": "🏠",
    "Otomotif": "🚗", "Agrikultur": "🌾", "Industri": "🧪",
}

def bandar_keyboard():
    """Pilih sektor dulu → baru lihat saham."""
    rows = []
    sektors = list(SEKTOR_TICKERS.keys())
    for i in range(0, len(sektors), 2):
        row = []
        for s in sektors[i:i+2]:
            emoji = SEKTOR_EMOJI.get(s, "📊")
            row.append(InlineKeyboardButton(f"{emoji} {s}", callback_data=f"bsektor_{s}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Menu Utama", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)

def bandar_sektor_keyboard(sektor: str):
    """Saham-saham dalam sektor tertentu untuk cek bandar."""
    tickers = SEKTOR_TICKERS.get(sektor, [])
    rows = []
    for i in range(0, len(tickers), 4):
        rows.append([InlineKeyboardButton(t, callback_data=f"bandar_{t}") for t in tickers[i:i+4]])
    emoji = SEKTOR_EMOJI.get(sektor, "📊")
    rows.append([InlineKeyboardButton(f"🔍 Scan Semua Bandar {emoji} {sektor}", callback_data=f"bscan_{sektor}")])
    rows.append([InlineKeyboardButton("🔙 Pilih Sektor", callback_data="menu_bandar")])
    return InlineKeyboardMarkup(rows)

def cek_keyboard():
    """Pilih sektor dulu → baru lihat saham untuk analisis 5D."""
    rows = []
    sektors = list(SEKTOR_TICKERS.keys())
    for i in range(0, len(sektors), 2):
        row = []
        for s in sektors[i:i+2]:
            emoji = SEKTOR_EMOJI.get(s, "📊")
            row.append(InlineKeyboardButton(f"{emoji} {s}", callback_data=f"csektor_{s}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Menu Utama", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)

def cek_sektor_keyboard(sektor: str):
    """Saham-saham dalam sektor tertentu untuk analisis 5D."""
    tickers = SEKTOR_TICKERS.get(sektor, [])
    rows = []
    for i in range(0, len(tickers), 4):
        rows.append([InlineKeyboardButton(t, callback_data=f"cek_{t}") for t in tickers[i:i+4]])
    rows.append([InlineKeyboardButton("🔙 Pilih Sektor", callback_data="menu_cek")])
    return InlineKeyboardMarkup(rows)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "☕ *Ngopi Saham Bot — 5D Stock Screener*\n\n"
        "Macro + Fundamental + Technical + *Bandarmologi* + Seasonality\n\n"
        "Pilih menu di bawah:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard()
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 *Daftar Perintah:*\n\n"
        "🔍 *Screening:*\n"
        "  /scan — Screen IDX Watchlist (100 saham)\n"
        "  /quick — Screen mode cepat\n"
        "  /top5 — Top 5 saham terbaik\n\n"
        "🏦 *Analisis Spesifik:*\n"
        "  /cek BBCA — Analisis 5D penuh\n"
        "  /bandar BBCA — Cek bandarmologi\n\n"
        "🎯 *Filter:*\n"
        "  /filter roe:15 per:20 bandar:ACCUMULATING\n\n"
        "Atau klik tombol di bawah!"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())

async def cmd_top5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kirim top 5 saham dari watchlist."""
    msg = await update.message.reply_text("⏳ Sedang scan top saham... (butuh ~2 menit)")
    
    try:
        # Ambil 15 saham mandatory saja untuk speed
        from pre_filter import MANDATORY_TICKERS
        quick_tickers = [f"{t}.JK" for t in MANDATORY_TICKERS[:15]]
        results = await run_screening_async(quick_tickers)
        
        text = format_screening_summary(results[:5], "🏆 Top 5 Saham Hari Ini")
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan full IDX Watchlist dengan live progress."""
    total = len(IDX_WATCHLIST)
    msg = await update.message.reply_text(
        f"📊 *Full Scan {total} Saham*\n"
        f"\n`[░░░░░░░░░░] 0/{total}`\n\n"
        "Estimasi ~15-20 menit. Progress update otomatis!",
        parse_mode=ParseMode.MARKDOWN
    )

    async def on_progress(done, total, ticker):
        pct = done / total
        bar = '█' * int(pct * 10) + '░' * (10 - int(pct * 10))
        await msg.edit_text(
            f"📊 *Full Scan {total} Saham*\n"
            f"\n`[{bar}] {done}/{total}` ({int(pct*100)}%)\n"
            f"Terakhir: `{ticker}`",
            parse_mode=ParseMode.MARKDOWN
        )

    try:
        results = await run_screening_async(IDX_WATCHLIST, progress_cb=on_progress)
        summary = format_screening_summary(results, "📊 Hasil Full Scan")
        back = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]])
        await msg.edit_text(summary, parse_mode=ParseMode.MARKDOWN, reply_markup=back)

        worthy = [s for s in results if s.total_score >= SCORE_THRESHOLD["watch"]][:5]
        for s in worthy:
            card = format_stock_card(s)
            await update.message.reply_text(card, parse_mode=ParseMode.MARKDOWN)
            await asyncio.sleep(0.5)
    except Exception as e:
        await msg.edit_text(f"❌ Error scanning: {e}")

async def cmd_quick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan mode quick dengan live progress."""
    tickers = build_filtered_universe(max_stocks=50)
    total = len(tickers)
    msg = await update.message.reply_text(
        f"⚡ *Quick Scan {total} Saham*\n"
        f"\n`[░░░░░░░░░░] 0/{total}`",
        parse_mode=ParseMode.MARKDOWN
    )

    async def on_progress(done, total, ticker):
        pct = done / total
        bar = '█' * int(pct * 10) + '░' * (10 - int(pct * 10))
        await msg.edit_text(
            f"⚡ *Quick Scan {total} Saham*\n"
            f"\n`[{bar}] {done}/{total}` ({int(pct*100)}%)\n"
            f"Terakhir: `{ticker}`",
            parse_mode=ParseMode.MARKDOWN
        )

    try:
        results = await run_screening_async(tickers, progress_cb=on_progress)
        text = format_screening_summary(results, "⚡ Quick Scan")
        back = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]])
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def cmd_cek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analisis 1 saham spesifik: /cek BBCA"""
    args = context.args
    if not args:
        await update.message.reply_text("❓ Format: /cek BBCA (tanpa .JK)")
        return
    
    ticker_raw = args[0].upper().replace(".JK", "")
    ticker = f"{ticker_raw}.JK"
    
    msg = await update.message.reply_text(f"⏳ Analisis 5D untuk *{ticker_raw}*...", parse_mode=ParseMode.MARKDOWN)
    
    try:
        loop = asyncio.get_event_loop()
        stock = await loop.run_in_executor(None, lambda: score_stock(fetch_stock_data(ticker)))
        card = format_stock_card(stock)
        
        if stock.conclusion:
            card += f"\n\n{stock.conclusion[:1000]}"
        
        await msg.edit_text(card, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error cek {ticker_raw}: {e}")

async def cmd_bandar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cek bandarmologi 1 saham: /bandar BBCA"""
    args = context.args
    if not args:
        await update.message.reply_text("❓ Format: /bandar BBCA (tanpa .JK)")
        return
    
    ticker = args[0].upper().replace(".JK", "")
    msg = await update.message.reply_text(f"🔍 Cek bandar *{ticker}*...", parse_mode=ParseMode.MARKDOWN)
    
    try:
        loop = asyncio.get_event_loop()
        sentiment = await loop.run_in_executor(None, lambda: idx_client.get_bandar_sentiment(ticker))
        
        if not sentiment:
            await msg.edit_text(f"❌ Data bandarmologi {ticker} tidak tersedia.")
            return
        
        bandar = sentiment.get("bandar_sentiment", {})
        retail = sentiment.get("retail_sentiment", {})
        
        status = bandar.get("status", "N/A")
        score = bandar.get("score", "N/A")
        ff = bandar.get("indicators", {}).get("foreign_flow")
        
        top_buyers = bandar.get("top_brokers", {}).get("buyers", [])
        top_sellers = bandar.get("top_brokers", {}).get("sellers", [])
        
        now = datetime.now().strftime("%d %b %Y")
        lines = [
            f"🏦 *Bandarmologi {ticker}* — {now}",
            f"",
            f"Status Bandar: {bandar_emoji(status)} *{status}*",
            f"Skor Bandar  : {score}/10",
            f"Retail Danger: {retail.get('danger_level', 'N/A')}",
        ]
        
        if ff:
            ff_dir = "📈 NET BUY" if ff > 0 else "📉 NET SELL"
            lines.append(f"Foreign 7d   : {ff_dir} {fmt_idr(abs(ff))}")
        
        if top_buyers:
            b = top_buyers[0]
            lines.append(f"\n👆 Top Buyer : {b.get('code','')} ({b.get('type','')}) {b.get('net_value_formatted','')}")
        if top_sellers:
            s = top_sellers[0]
            lines.append(f"👇 Top Seller: {s.get('code','')} ({s.get('type','')}) {s.get('net_value_formatted','')}")
        
        if "ACCUM" in status.upper():
            lines.append(f"\n✅ *Sinyal: Smart money sedang AKUMULASI. Potensi breakout!*")
        elif "EXIT" in status.upper() or "DIST" in status.upper():
            lines.append(f"\n🚨 *WASPADA: Bandar sedang KELUAR dari saham ini!*")
        
        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def cmd_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Custom filter: /filter roe:15 per:20 bandar:ACCUMULATING sektor:Perbankan
    """
    args_text = " ".join(context.args)
    if not args_text:
        await update.message.reply_text(
            "❓ *Format filter:*\n"
            "/filter roe:15 per:20\n"
            "/filter bandar:ACCUMULATING foreign:BUY\n"
            "/filter sektor:Perbankan score:60",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Parse filter dari format Telegram (roe:15 → --min-roe=15)
    filter_map = {
        "roe": "--min-roe=", "per": "--max-per=",
        "score": "--min-score=", "cap": "--min-cap=",
        "bandar": "--bandar=", "signal": "--signal=",
        "winrate": "--min-winrate=", "der": "--max-der=",
        "margin": "--min-margin=", "foreign": "--foreign=",
        "sektor": "--sector=", "sector": "--sector="
    }
    
    cli_args = []
    for part in args_text.split():
        if ":" in part:
            key, val = part.split(":", 1)
            prefix = filter_map.get(key.lower())
            if prefix:
                cli_args.append(f"{prefix}{val}")
    
    from filter_engine import parse_filters_from_args
    fc = parse_filters_from_args(cli_args)
    
    msg = await update.message.reply_text(f"⏳ Screening dengan filter: `{args_text}`...", parse_mode=ParseMode.MARKDOWN)
    
    try:
        results_all = await run_screening_async(IDX_WATCHLIST)
        filtered = apply_filters(results_all, fc)
        
        if not filtered:
            await msg.edit_text(
                f"🔍 Filter: `{args_text}`\n❌ Tidak ada saham yang lolos filter ini.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        text = format_screening_summary(filtered, f"🎯 Filter: {args_text}")
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Status bot."""
    now = datetime.now().strftime("%d %b %Y %H:%M WIB")
    text = (
        f"✅ *Bot Status: Online*\n"
        f"🕐 Waktu: {now}\n"
        f"📋 Watchlist: {len(IDX_WATCHLIST)} saham\n"
        f"🔄 Auto-scan: Setiap hari jam 07:00 WIB\n"
        f"🤖 Engine: IDX API + Yahoo Finance + Gemini AI"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ─── AUTH GUARD ─────────────────────────────────────────────

ALLOWED_USERS = set()
if TELEGRAM_CHAT_ID:
    ALLOWED_USERS.add(int(TELEGRAM_CHAT_ID))

def is_authorized(user_id: int) -> bool:
    """Cek apakah user boleh pakai bot. Kosong = semua boleh."""
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

async def auth_check(update: Update) -> bool:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        text = "🔒 Bot ini private. Hubungi owner untuk akses."
        if update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
        elif update.message:
            await update.message.reply_text(text)
        return False
    return True


# ─── CALLBACK HANDLER (INLINE BUTTONS) ──────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not await auth_check(update):
        return

    data = query.data

    # Menu navigasi
    if data == "main_menu":
        await query.edit_message_text(
            "☕ *Ngopi Saham Bot — 5D Stock Screener*\n\nPilih menu:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard()
        )
    elif data == "menu_bandar":
        await query.edit_message_text(
            "🏦 *Pilih saham untuk cek Bandarmologi:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=bandar_keyboard()
        )
    elif data == "menu_cek":
        await query.edit_message_text(
            "🔍 *Pilih saham untuk Analisis 5D:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=cek_keyboard()
        )
    elif data == "help":
        await query.edit_message_text(
            "📋 *Perintah:*\n/scan /quick /top5\n/cek BBCA\n/bandar BBCA\n/filter roe:15 bandar:ACCUMULATING\n\nAtau pakai tombol!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard()
        )

    # Status
    elif data == "status":
        now = datetime.now().strftime("%d %b %Y %H:%M WIB")
        await query.edit_message_text(
            f"✅ *Online* | {now}\n📋 {len(IDX_WATCHLIST)} saham | 🔄 07:00 WIB",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]])
        )

    # Screening actions
    elif data == "top5":
        from pre_filter import MANDATORY_TICKERS
        tickers = [f"{t}.JK" for t in MANDATORY_TICKERS[:15]]
        total = len(tickers)
        await query.edit_message_text(
            f"🏆 *Top 5 — Scan {total} Saham*\n\n`[░░░░░░░░░░] 0/{total}`",
            parse_mode=ParseMode.MARKDOWN
        )
        async def on_progress(done, total, ticker):
            pct = done / total
            bar = '█' * int(pct * 10) + '░' * (10 - int(pct * 10))
            try:
                await query.edit_message_text(
                    f"🏆 *Top 5 — Scan {total} Saham*\n\n"
                    f"`[{bar}] {done}/{total}` ({int(pct*100)}%)\n"
                    f"Terakhir: `{ticker}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass
        try:
            results = await run_screening_async(tickers, progress_cb=on_progress)
            text = format_screening_summary(results[:5], "🏆 Top 5 Hari Ini")
            back = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]])
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")

    elif data == "quick":
        tickers = build_filtered_universe(max_stocks=50)
        total = len(tickers)
        await query.edit_message_text(
            f"⚡ *Quick Scan {total} Saham*\n\n`[░░░░░░░░░░] 0/{total}`",
            parse_mode=ParseMode.MARKDOWN
        )
        async def on_progress_q(done, total, ticker):
            pct = done / total
            bar = '█' * int(pct * 10) + '░' * (10 - int(pct * 10))
            try:
                await query.edit_message_text(
                    f"⚡ *Quick Scan {total} Saham*\n\n"
                    f"`[{bar}] {done}/{total}` ({int(pct*100)}%)\n"
                    f"Terakhir: `{ticker}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass
        try:
            results = await run_screening_async(tickers, progress_cb=on_progress_q)
            text = format_screening_summary(results, "⚡ Quick Scan")
            back = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]])
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")

    elif data == "scan":
        await query.edit_message_text("⏳ *Full scan 100 saham...* (~15 menit)\nGue notif pas selesai!", parse_mode=ParseMode.MARKDOWN)
        try:
            results = await run_screening_async(IDX_WATCHLIST)
            text = format_screening_summary(results, "📊 Full Scan")
            back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]])
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")

    elif data == "menu_filter":
        await query.edit_message_text(
            "🎯 *Filter & Screener*\nPilih filter yang mau lo terapkan:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=filter_menu_keyboard()
        )

    elif data == "menu_sektor":
        await query.edit_message_text(
            "🏢 *Pilih Sektor:*\nHasil scan akan difilter sesuai sektor pilihan.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=sektor_keyboard()
        )

    # Sektor filter: sektor_Perbankan, sektor_Teknologi, dll
    elif data.startswith("sektor_"):
        sektor_name = data.replace("sektor_", "")
        await query.edit_message_text(f"⏳ Scanning sektor *{sektor_name}*...", parse_mode=ParseMode.MARKDOWN)
        try:
            fc = FilterCriteria(sector=sektor_name)
            results = await run_screening_async(IDX_WATCHLIST)
            filtered = apply_filters(results, fc)
            if not filtered:
                await query.edit_message_text(
                    f"🔍 Sektor *{sektor_name}*\n❌ Tidak ada saham yang lolos.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Sektor Lain", callback_data="menu_sektor")]])
                )
                return
            text = format_screening_summary(filtered, f"🏢 Sektor: {sektor_name}")
            back = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Sektor Lain", callback_data="menu_sektor"),
                 InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")

    elif data == "filter_distrib":
        await query.edit_message_text("⏳ Cari saham bandar DISTRIBUSI...")
        try:
            fc = FilterCriteria(bandar_status="DISTRIBUTING")
            results = await run_screening_async(IDX_WATCHLIST)
            filtered = apply_filters(results, fc)
            text = format_screening_summary(filtered or results[:5], "🔴 Bandar Distribusi")
            back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Filter", callback_data="menu_filter")]])
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")

    elif data == "filter_foreign_sell":
        await query.edit_message_text("⏳ Cari saham asing KELUAR (net sell)...")
        try:
            fc = FilterCriteria(foreign_flow="SELL")
            results = await run_screening_async(IDX_WATCHLIST)
            filtered = apply_filters(results, fc)
            text = format_screening_summary(filtered or results[:5], "📉 Foreign Net Sell")
            back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Filter", callback_data="menu_filter")]])
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")

    elif data == "filter_multibagger":
        await query.edit_message_text("⏳ Cari MULTI-BAGGER...")
        try:
            fc = FilterCriteria(signal="MULTI-BAGGER")
            results = await run_screening_async(IDX_WATCHLIST)
            filtered = apply_filters(results, fc)
            text = format_screening_summary(filtered or [], "🚀 Multi-Bagger Candidates")
            back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Filter", callback_data="menu_filter")]])
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")

    elif data == "filter_value":
        await query.edit_message_text("⏳ Cari value stock (ROE > 20%, PER < 15)...")
        try:
            fc = FilterCriteria(min_roe=20.0, max_per=15.0)
            results = await run_screening_async(IDX_WATCHLIST)
            filtered = apply_filters(results, fc)
            text = format_screening_summary(filtered or [], "💎 Value Stocks: ROE>20% PER<15")
            back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Filter", callback_data="menu_filter")]])
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")

    elif data == "filter_momentum":
        await query.edit_message_text("⏳ Cari momentum stocks (Score > 65)...")
        try:
            fc = FilterCriteria(min_score=65.0)
            results = await run_screening_async(IDX_WATCHLIST)
            filtered = apply_filters(results, fc)
            text = format_screening_summary(filtered or [], "📈 Momentum: Score > 65")
            back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Filter", callback_data="menu_filter")]])
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")
        await query.edit_message_text("⏳ Cari saham bandar AKUMULASI...")
        try:
            fc = FilterCriteria(bandar_status="ACCUMULATING")
            results = await run_screening_async(IDX_WATCHLIST)
            filtered = apply_filters(results, fc)
            text = format_screening_summary(filtered, "🟢 Bandar Akumulasi")
            back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]])
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")

    elif data == "filter_foreign":
        await query.edit_message_text("⏳ Cari saham asing masuk (net buy)...")
        try:
            fc = FilterCriteria(foreign_flow="BUY")
            results = await run_screening_async(IDX_WATCHLIST)
            filtered = apply_filters(results, fc)
            text = format_screening_summary(filtered, "💰 Foreign Net Buy")
            back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]])
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")

    # Bandar sektor picker: bsektor_Perbankan
    elif data.startswith("bsektor_"):
        sektor = data.replace("bsektor_", "")
        emoji = SEKTOR_EMOJI.get(sektor, "📊")
        count = len(SEKTOR_TICKERS.get(sektor, []))
        await query.edit_message_text(
            f"{emoji} *Sektor {sektor}* — {count} saham\n\n"
            "Pilih saham atau scan semua bandar sekaligus:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=bandar_sektor_keyboard(sektor)
        )

    # Cek sektor picker: csektor_Perbankan
    elif data.startswith("csektor_"):
        sektor = data.replace("csektor_", "")
        emoji = SEKTOR_EMOJI.get(sektor, "📊")
        count = len(SEKTOR_TICKERS.get(sektor, []))
        await query.edit_message_text(
            f"{emoji} *Sektor {sektor}* — {count} saham\n\n"
            "Pilih saham untuk analisis 5D:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=cek_sektor_keyboard(sektor)
        )

    # Scan SEMUA bandar di 1 sektor: bscan_Perbankan
    elif data.startswith("bscan_"):
        sektor = data.replace("bscan_", "")
        tickers = SEKTOR_TICKERS.get(sektor, [])
        emoji = SEKTOR_EMOJI.get(sektor, "📊")
        total = len(tickers)
        await query.edit_message_text(
            f"🔍 *Scan Bandar {emoji} {sektor}*\n\n"
            f"`[░░░░░░░░░░] 0/{total}`",
            parse_mode=ParseMode.MARKDOWN
        )
        try:
            results = []
            for i, t in enumerate(tickers, 1):
                try:
                    loop = asyncio.get_event_loop()
                    sentiment = await loop.run_in_executor(
                        None, lambda tk=t: idx_client.get_bandar_sentiment(tk)
                    )
                    if sentiment:
                        bandar = sentiment.get("bandar_sentiment", {})
                        results.append({
                            "ticker": t,
                            "status": bandar.get("status", "N/A"),
                            "score":  bandar.get("score", 0),
                        })
                except Exception:
                    pass

                # Update progress tiap 3 saham
                if i % 3 == 0 or i == total:
                    pct = i / total
                    bar = '█' * int(pct * 10) + '░' * (10 - int(pct * 10))
                    try:
                        await query.edit_message_text(
                            f"🔍 *Scan Bandar {emoji} {sektor}*\n\n"
                            f"`[{bar}] {i}/{total}` ({int(pct*100)}%)\n"
                            f"Terakhir: `{t}`",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except Exception:
                        pass

            # Format hasil
            results.sort(key=lambda x: x.get("score", 0), reverse=True)
            lines = [f"🏦 *Bandarmologi {emoji} Sektor {sektor}*\n"]
            for r in results:
                em = bandar_emoji(r["status"])
                lines.append(f"{em} `{r['ticker']:5s}` — *{r['status']}* (skor: {r['score']})")
            if not results:
                lines.append("❌ Tidak ada data bandar tersedia.")

            back = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Sektor Lain", callback_data="menu_bandar"),
                 InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]
            ])
            await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")

    # Bandar per saham: bandar_BBCA
    elif data.startswith("bandar_"):
        ticker = data.replace("bandar_", "")
        await query.edit_message_text(f"🔍 Cek bandar *{ticker}*...", parse_mode=ParseMode.MARKDOWN)
        try:
            loop = asyncio.get_event_loop()
            sentiment = await loop.run_in_executor(None, lambda: idx_client.get_bandar_sentiment(ticker))
            if not sentiment:
                await query.edit_message_text(f"❌ Data bandar {ticker} tidak tersedia.")
                return
            bandar = sentiment.get("bandar_sentiment", {})
            status = bandar.get("status", "N/A")
            score = bandar.get("score", "N/A")
            lines = [
                f"🏦 *Bandarmologi {ticker}*",
                f"Status: {bandar_emoji(status)} *{status}*",
                f"Skor: {score}/10",
            ]
            back = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Bandar Lain", callback_data="menu_bandar"),
                 InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]
            ])
            await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")


    # Cek per saham: cek_BBCA
    elif data.startswith("cek_"):
        ticker = data.replace("cek_", "")
        try:
            await query.edit_message_text(
                f"⏳ *Analisis 5D: {ticker}*\n\n"
                "📊 Mengambil data fundamental...",
                parse_mode=ParseMode.MARKDOWN
            )
            loop = asyncio.get_event_loop()
            stock_data = await loop.run_in_executor(None, lambda: fetch_stock_data(f"{ticker}.JK"))

            await query.edit_message_text(
                f"⏳ *Analisis 5D: {ticker}*\n\n"
                "📊 Data fundamental ✅\n"
                "📈 Scoring & analisis teknikal...",
                parse_mode=ParseMode.MARKDOWN
            )
            stock = await loop.run_in_executor(None, lambda: score_stock(stock_data))

            card = format_stock_card(stock)
            if stock.conclusion:
                card += f"\n\n{stock.conclusion[:1000]}"

            back = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Cek Lain", callback_data="menu_cek"),
                 InlineKeyboardButton("🏠 Menu", callback_data="main_menu")]
            ])
            await query.edit_message_text(card, parse_mode=ParseMode.MARKDOWN, reply_markup=back)
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")


# ─── SCHEDULER ──────────────────────────────────────────────

async def daily_morning_push(context: ContextTypes.DEFAULT_TYPE):
    """Push otomatis tiap pagi jam 07:00 WIB."""
    chat_id = TELEGRAM_CHAT_ID
    if not chat_id:
        logger.warning("TELEGRAM_CHAT_ID belum diset di config.py!")
        return
    
    logger.info("Menjalankan daily morning push...")
    
    try:
        from pre_filter import MANDATORY_TICKERS
        tickers = [f"{t}.JK" for t in MANDATORY_TICKERS]
        results = await run_screening_async(tickers)
        
        text = format_screening_summary(results, "🌅 Morning Alert — Top Picks Hari Ini")
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
        
        # Kirim detail tiap MULTI-BAGGER
        top = [s for s in results if "MULTI" in s.signal][:3]
        for s in top:
            await context.bot.send_message(
                chat_id=chat_id,
                text=format_stock_card(s),
                parse_mode=ParseMode.MARKDOWN
            )
            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"Daily push error: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Morning scan error: {e}")


# ─── MAIN ────────────────────────────────────────────────────

def main():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "ISI_TOKEN_TELEGRAM_BOT_LO":
        print("❌ ERROR: TELEGRAM_BOT_TOKEN belum diset di config.py!")
        print("   1. Buat bot baru di @BotFather di Telegram")
        print("   2. Salin token ke config.py → TELEGRAM_BOT_TOKEN")
        return
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("quick", cmd_quick))
    app.add_handler(CommandHandler("top5", cmd_top5))
    app.add_handler(CommandHandler("cek", cmd_cek))
    app.add_handler(CommandHandler("bandar", cmd_bandar))
    app.add_handler(CommandHandler("filter", cmd_filter))
    app.add_handler(CommandHandler("status", cmd_status))

    # Callback handler for inline buttons
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Error handler — suppress 409 Conflict saat redeploy
    async def error_handler(update, context):
        from telegram.error import Conflict, NetworkError, BadRequest
        err = context.error
        if isinstance(err, Conflict):
            logger.warning("409 Conflict: instance lama masih hidup, tunggu sebentar...")
        elif isinstance(err, BadRequest) and "not modified" in str(err).lower():
            pass  # Progress bar kirim konten sama — suppress, normal
        elif isinstance(err, NetworkError):
            logger.warning(f"NetworkError (akan retry): {err}")
        else:
            logger.error(f"Error: {err}")
    app.add_error_handler(error_handler)

    # Scheduler
    if TELEGRAM_CHAT_ID:
        app.job_queue.run_daily(
            daily_morning_push,
            time=dt_time(0, 0, 0),
            name="morning_push"
        )
        print(f"[OK] Auto-push terjadwal jam 07:00 WIB ke chat ID: {TELEGRAM_CHAT_ID}")

    print("[BOT] 5D Stock Screener Bot RUNNING...")
    print("   Tekan Ctrl+C untuk stop\n")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
