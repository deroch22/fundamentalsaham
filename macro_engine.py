"""
DIMENSI 1: WHY (MACRO ECONOMY)
Evaluasi saham berdasarkan kondisi makro ekonomi saat ini.
"""

# Simulasi kondisi makro saat ini (Bisa di-update manual jika kondisi berubah)
CURRENT_MACRO = {
    "interest_rate": "high",     # Suku bunga BI: "high", "low", "neutral"
    "inflation": "moderate",     # Inflasi: "high", "moderate", "low"
    "economic_growth": "stable", # Pertumbuhan: "expanding", "stable", "recession"
    "commodity_cycle": "mixed",  # Harga komoditas: "bull", "bear", "mixed"
}

def analyze_macro(sector: str, industry: str) -> dict:
    """
    Evaluasi sektor berdasarkan makro.
    Return: {"score": 0-10, "outlook": "Bullish/Neutral/Bearish", "reason": str}
    """
    sector = sector.lower()
    industry = industry.lower()
    
    score = 5.0
    outlook = "Neutral"
    reason = "Kondisi makro netral untuk sektor ini."
    
    # Aturan Makro Sederhana
    rate = CURRENT_MACRO["interest_rate"]
    
    if "financial" in sector or "bank" in industry:
        if rate == "high":
            score = 8.0
            outlook = "Bullish"
            reason = "Suku bunga tinggi (NIM perbankan melebar)."
        elif rate == "low":
            score = 4.0
            outlook = "Bearish"
            reason = "Suku bunga rendah menekan margin bunga bersih (NIM)."

    elif "consumer" in sector or "retail" in sector:
        if CURRENT_MACRO["inflation"] in ["low", "moderate"] and CURRENT_MACRO["economic_growth"] != "recession":
            score = 7.5
            outlook = "Bullish"
            reason = "Daya beli terjaga karena inflasi terkendali."
        else:
            score = 3.0
            outlook = "Bearish"
            reason = "Inflasi tinggi menekan margin dan daya beli."

    elif "real estate" in sector or "property" in sector:
        if rate == "high":
            score = 2.0
            outlook = "Bearish"
            reason = "Suku bunga tinggi menekan KPR dan penjualan properti."
        elif rate == "low":
            score = 9.0
            outlook = "Bullish"
            reason = "Suku bunga rendah memicu kredit dan pembelian properti."

    elif "energy" in sector or "mining" in sector or "basic materials" in sector:
        if CURRENT_MACRO["commodity_cycle"] == "bull":
            score = 8.5
            outlook = "Bullish"
            reason = "Diuntungkan oleh siklus super komoditas."
        elif CURRENT_MACRO["commodity_cycle"] == "bear":
            score = 3.0
            outlook = "Bearish"
            reason = "Tertekan oleh penurunan harga komoditas global."
            
    elif "technology" in sector:
        if rate == "high":
            score = 3.5
            outlook = "Bearish"
            reason = "Suku bunga tinggi mendiskon valuasi growth stocks/tech."
        else:
            score = 8.0
            outlook = "Bullish"
            reason = "Suku bunga rendah menguntungkan valuasi tech."

    return {
        "score": score,  # Skala 0-10
        "outlook": outlook,
        "reason": reason
    }
