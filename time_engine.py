"""
DIMENSI 4: WHEN (TIME / SEASONALITY)
Analisis probabilitas historis saham naik di bulan saat ini (Siklus Musiman).
"""

import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def analyze_seasonality(chart_data: dict, current_month: int = None) -> dict:
    """
    Evaluasi probabilitas saham naik di bulan berjalan (historis 3-5 tahun).
    Return: {"score": 0-10, "win_rate": float, "notes": list}
    """
    default_res = {"score": 0.0, "win_rate": None, "notes": []}
    
    if not chart_data:
        return default_res
        
    try:
        timestamps = chart_data.get('timestamp', [])
        indicators = chart_data.get('indicators', {}).get('quote', [{}])[0]
        closes = indicators.get('close', [])
        
        if not closes or len(closes) < 250: # Butuh minimal ~1 tahun data (250 hari bursa)
            return default_res
            
        df = pd.DataFrame({'timestamp': timestamps, 'close': closes})
        df['date'] = pd.to_datetime(df['timestamp'], unit='s')
        df.dropna(inplace=True)
        
        # Resample menjadi data bulanan
        df.set_index('date', inplace=True)
        monthly = df['close'].resample('ME').last().to_frame()
        
        # Hitung return per bulan
        monthly['return'] = monthly['close'].pct_change() * 100
        monthly.dropna(inplace=True)
        monthly['month'] = monthly.index.month
        
        if current_month is None:
            current_month = datetime.now().month
            
        # Filter data untuk bulan saat ini di tahun-tahun sebelumnya
        target_month_data = monthly[monthly['month'] == current_month]
        
        if len(target_month_data) == 0:
            return default_res
            
        years_analyzed = len(target_month_data)
        wins = len(target_month_data[target_month_data['return'] > 0])
        win_rate = (wins / years_analyzed) * 100
        
        score = 0.0
        notes = []
        month_name = datetime.now().strftime("%B")
        
        # --- SCORING RULES (Total 10) ---
        if win_rate >= 80:
            score = 10.0
            notes.append(f"Strong Seasonality: Menang {wins} dari {years_analyzed} tahun di bulan {month_name}")
        elif win_rate >= 60:
            score = 7.0
            notes.append(f"Good Seasonality: Win rate {win_rate:.0f}% di bulan {month_name}")
        elif win_rate >= 40:
            score = 4.0
        else:
            score = 0.0
            notes.append(f"Bad Seasonality: Cenderung turun di bulan {month_name} ({wins}/{years_analyzed} win)")
            
        return {
            "score": round(score, 1),
            "win_rate": round(win_rate, 1),
            "notes": notes
        }
        
    except Exception as e:
        logger.error(f"Seasonality parse error: {e}")
        return default_res
