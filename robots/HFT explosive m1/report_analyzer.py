# report_analyzer.py

import os
import json
import pandas as pd

def calculate_overall_kpis(reports_data: list):
    """
    [DIUBAH] Menerima LIST data laporan, menggabungkannya, dan menghitung
    KPI keseluruhan.
    """
    all_trades = []
    report_summaries = []

    # Jika tidak ada data yang difilter, kembalikan nilai nol
    if not reports_data:
        return {
            "total_pnl": 0.0, "avg_profit_factor": 0.0,
            "overall_win_rate": 0.0, "total_trades": 0
        }

    # Loop melalui data yang sudah ada di memori
    for data in reports_data:
        all_trades.extend(data.get('trades', []))
        report_summaries.append(data.get('analytics', {}))
    
    if not all_trades:
        return {
            "total_pnl": 0.0, "avg_profit_factor": 0.0,
            "overall_win_rate": 0.0, "total_trades": 0
        }

    trades_df = pd.DataFrame(all_trades)
    total_pnl = trades_df['profit'].sum()

    winning_trades = len(trades_df[trades_df['profit'] >= 0])
    total_trades = len(trades_df)
    overall_win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
    
    valid_pfs = [s.get('profit_factor') for s in report_summaries if isinstance(s.get('profit_factor'), (int, float))]
    avg_profit_factor = sum(valid_pfs) / len(valid_pfs) if valid_pfs else 0.0

    return {
        "total_pnl": round(total_pnl, 2),
        "avg_profit_factor": round(avg_profit_factor, 2),
        "overall_win_rate": round(overall_win_rate, 2),
        "total_trades": total_trades,
        "trades_df": trades_df
    }