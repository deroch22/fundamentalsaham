"""
DIMENSI 3: WHERE (TECHNICAL ANALYSIS)
Analisis trend (SMA), momentum (RSI), dan jarak dari support/resistance.
"""

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

def calculate_rsi(prices: pd.Series, window: int = 14) -> float:
    """Hitung RSI (Relative Strength Index)."""
    if len(prices) < window + 1:
        return 50.0  # Default netral jika data tidak cukup
        
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    
    # Simple Moving Average for RSI 
    avg_gain = gain.rolling(window=window, min_periods=1).mean()
    avg_loss = loss.rolling(window=window, min_periods=1).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def analyze_technical(chart_data: dict) -> dict:
    """
    Evaluasi Teknikal dari data historis (harian, range 1-2 tahun disarankan).
    Return: {"score": 0-10, "rsi": float, "sma50": float, "sma200": float, "trend": str, "notes": list}
    """
    default_res = {
        "score": 0.0, "rsi": None, "sma50": None, "sma200": None, 
        "trend": "Unknown", "volume_spike": False, "notes": []
    }
    
    if not chart_data:
        return default_res
        
    try:
        timestamps = chart_data.get('timestamp', [])
        indicators = chart_data.get('indicators', {}).get('quote', [{}])[0]
        closes = indicators.get('close', [])
        volumes = indicators.get('volume', [])
        
        if not closes or len(closes) < 30:
            return default_res
            
        df = pd.DataFrame({'close': closes, 'volume': volumes})
        df.dropna(inplace=True)
        if len(df) < 10:
            return default_res
            
        prices = df['close']
        vols = df['volume']
        current_price = prices.iloc[-1]
        current_vol = vols.iloc[-1]
        
        # Hitung RSI
        rsi = calculate_rsi(prices, 14)
        
        # Deteksi Volume Spike (Bandarmologi Proxy)
        sma_vol = vols.rolling(window=20, min_periods=1).mean().iloc[-1]
        volume_spike = current_vol > (sma_vol * 2) if sma_vol > 0 else False
        
        # Hitung SMA
        sma50 = float(prices.rolling(window=50, min_periods=1).mean().iloc[-1]) if len(prices) >= 50 else None
        sma200 = float(prices.rolling(window=200, min_periods=1).mean().iloc[-1]) if len(prices) >= 200 else None
        
        score = 0.0
        notes = []
        trend = "Sideways"
        
        # --- SCORING RULES (Total 10) ---
        
        # 1. Momentum RSI (Max 4 Poin)
        if rsi < 30:
            score += 4.0
            notes.append(f"Oversold (RSI: {rsi:.1f}) - Potensi Rebound")
        elif rsi < 45:
            score += 3.0
        elif rsi < 60:
            score += 2.0
        elif rsi > 70:
            score += 0.0
            notes.append(f"Overbought (RSI: {rsi:.1f}) - Rawan Koreksi")
        else:
            score += 1.0
            
        # 2. Trend (Max 6 Poin)
        if sma50 and sma200:
            if current_price > sma50 and current_price > sma200:
                trend = "Strong Uptrend"
                score += 6.0
                if sma50 > sma200:
                    notes.append("Golden Cross terkonfirmasi")
            elif current_price > sma50 and current_price < sma200:
                trend = "Early Rebound"
                score += 4.0
                notes.append("Harga menembus SMA 50")
            elif current_price < sma50 and current_price > sma200:
                trend = "Correction"
                score += 3.0
                notes.append("Koreksi jangka pendek, masih di atas SMA 200")
            else:
                trend = "Downtrend"
                score += 0.0
                notes.append("Harga di bawah SMA 50 dan 200")
        elif sma50:
            # Fallback jika data tidak cukup untuk SMA 200
            if current_price > sma50:
                trend = "Uptrend (Short)"
                score += 4.0
            else:
                trend = "Downtrend (Short)"
                
        # 3. Volume Anomaly Bonus
        if volume_spike:
            notes.append("Volume Anomaly: Terjadi lonjakan volume (Bandarmologi Akumulasi/Distribusi)")
        
        return {
            "score": round(score, 1),
            "rsi": round(rsi, 1),
            "sma50": round(sma50, 1) if sma50 else None,
            "sma200": round(sma200, 1) if sma200 else None,
            "trend": trend,
            "volume_spike": volume_spike,
            "notes": notes
        }
        
    except Exception as e:
        logger.error(f"Technical parse error: {e}")
        return default_res
