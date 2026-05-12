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

from telegram import Update, Bot
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
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

async def run_screening_async(tickers: list[str], filters: FilterCriteria = None) -> list[StockData]:
    """Jalankan screening di background thread."""
    loop = asyncio.get_event_loop()
    
    def _run():
        results = []
        for t in tickers:
            try:
                stock = fetch_stock_data(t)
                stock = score_stock(stock)
                results.append(stock)
            except Exception as e:
                logger.error(f"Error {t}: {e}")
        results.sort(key=lambda x: x.total_score, reverse=True)
        if filters:
            results = apply_filters(results, filters)
        return results
    
    return await loop.run_in_executor(None, _run)


# ─── COMMAND HANDLERS ────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *5D Stock Screener Bot*\n\n"
        "Halo! Gue bisa bantu lo screen saham IDX pake 5 dimensi:\n"
        "Macro + Fundamental + Technical + *Bandarmologi* + Seasonality\n\n"
        "Ketik /help untuk lihat semua perintah.",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 *Daftar Perintah:*\n\n"
        "🔍 *Screening:*\n"
        "  /scan — Screen IDX Watchlist (100 saham)\n"
        "  /quick — Screen mode cepat (trending + mandatory)\n"
        "  /top5 — Top 5 saham terbaik hari ini\n\n"
        "🏦 *Analisis Spesifik:*\n"
        "  /cek BBCA — Analisis 1 saham penuh\n"
        "  /bandar BBCA — Cek bandarmologi 1 saham\n\n"
        "🎯 *Filter Custom:*\n"
        "  /filter roe:15 per:20 bandar:ACCUMULATING\n"
        "  /filter sektor:Perbankan score:60\n"
        "  /filter foreign:BUY margin:10 der:1.0\n\n"
        "ℹ️ *Info:*\n"
        "  /status — Status bot & quota API\n\n"
        "💡 Bot auto-push screening tiap pagi jam 07:00 WIB!"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

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
    """Scan full IDX Watchlist."""
    await update.message.reply_text(
        "⏳ *Screening 100 saham dimulai...*\n"
        "Estimasi: ~15-20 menit. Gue notif pas selesai!",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        results = await run_screening_async(IDX_WATCHLIST)
        
        # Kirim summary dulu
        summary = format_screening_summary(results, "📊 Hasil Screening Penuh")
        await update.message.reply_text(summary, parse_mode=ParseMode.MARKDOWN)
        
        # Kirim detail card tiap MULTI-BAGGER & WATCH
        worthy = [s for s in results if s.total_score >= SCORE_THRESHOLD["watch"]][:5]
        for s in worthy:
            card = format_stock_card(s)
            await update.message.reply_text(card, parse_mode=ParseMode.MARKDOWN)
            await asyncio.sleep(0.5)
    except Exception as e:
        await update.message.reply_text(f"❌ Error scanning: {e}")

async def cmd_quick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan mode quick."""
    msg = await update.message.reply_text("⏳ Quick scan: ambil trending + mandatory list...")
    
    try:
        tickers = build_filtered_universe(max_stocks=50)
        results = await run_screening_async(tickers)
        text = format_screening_summary(results, "⚡ Quick Scan")
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
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
            card += f"\n\n{stock.conclusion[:500]}"
        
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
    
    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("quick", cmd_quick))
    app.add_handler(CommandHandler("top5", cmd_top5))
    app.add_handler(CommandHandler("cek", cmd_cek))
    app.add_handler(CommandHandler("bandar", cmd_bandar))
    app.add_handler(CommandHandler("filter", cmd_filter))
    app.add_handler(CommandHandler("status", cmd_status))
    
    # Scheduler: push harian jam 07:00 WIB (UTC+7 = UTC 00:00)
    if TELEGRAM_CHAT_ID:
        app.job_queue.run_daily(
            daily_morning_push,
            time=dt_time(0, 0, 0),  # 00:00 UTC = 07:00 WIB
            name="morning_push"
        )
        print(f"✅ Auto-push terjadwal jam 07:00 WIB ke chat ID: {TELEGRAM_CHAT_ID}")
    
    print("🤖 5D Stock Screener Bot RUNNING...")
    print("   Tekan Ctrl+C untuk stop\n")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
