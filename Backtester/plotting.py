# plotting.py
import os
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf

def plot_equity_curve_impl(equity_data: list, report_details: dict):
    """Implementasi asli _plot_equity_curve, tanpa mengubah parameter/kontrak."""
    if not equity_data or len(equity_data) < 2:
        print("Tidak cukup data untuk membuat kurva ekuitas.")
        return

    # Siapkan data
    timestamps = [pd.to_datetime(int(item[0]), unit='ms', utc=True) for item in equity_data]
    balances   = [float(item[1]) for item in equity_data]

    # Teks laporan (tetap opsional kalau ada field-nya)
    report_lines = ["--- Laporan Backtest Bulanan ---"]
    if 'period' in report_details:
        report_lines.append(report_details['period'])
    if report_details.get('trading_session_info'):
        report_lines.append(report_details['trading_session_info'])
    if report_details.get('adx_filter_info'):
        report_lines.append(report_details['adx_filter_info'])
    if report_details.get('sl_info'):
        report_lines.append(report_details['sl_info'])
    report_string = "\n".join(report_lines)

    # Plot
    fig, ax = plt.subplots(figsize=(16, 8))
    ax.plot(timestamps, balances, linewidth=2)
    ax.set_title(f"Kurva Ekuitas untuk {report_details.get('symbol','')}", fontsize=16)
    ax.set_xlabel("Tanggal", fontsize=12)
    ax.set_ylabel("Saldo Akun ($)", fontsize=12)
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.2f}'))

    # Tempel ringkasan di pojok atas (jika ada)
    if report_string.strip():
        ax.text(
            0.01, 0.99, report_string,
            transform=ax.transAxes,
            va='top', ha='left', fontsize=10,
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.85)
        )

    # Simpan
    run_directory = report_details['run_directory']
    period_tag = report_details['period_for_filename']
    os.makedirs(run_directory, exist_ok=True)
    filename = os.path.join(run_directory, f"equity_curve_{period_tag}.png")

    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"Kurva Ekuitas bulanan disimpan: {filename}")
    # Tidak perlu return apa-apa (sama seperti implementasi lama), tapi aman kalau mau:
    # return filename


def plot_completed_trade_impl(df_slice: pd.DataFrame, trade: dict, trade_index: int, output_folder: str):
    """Implementasi asli _plot_completed_trade, tanpa mengubah parameter/kontrak."""
    style = mpf.make_marketcolors(up='green', down='red', inherit=True)
    s = mpf.make_mpf_style(marketcolors=style, gridstyle=':')

    entry_time, exit_time = trade['entry_time'], trade['exit_time']
    trade_type, profit = trade['type'], trade['profit_usd']
    padding = 0.005

    # Marker ENTRY
    entry_series = pd.Series(float('nan'), index=df_slice.index)
    if trade_type == 'BUY':
        y_pos = df_slice.loc[entry_time, 'low'] * (1 - padding)
        entry_marker_shape = '^'
    else:  # SELL
        y_pos = df_slice.loc[entry_time, 'high'] * (1 + padding)
        entry_marker_shape = 'v'
    entry_series[entry_time] = y_pos
    entry_marker = mpf.make_addplot(
        entry_series, type='scatter', color='green', marker=entry_marker_shape, markersize=120
    )

    # Marker EXIT
    exit_series = pd.Series(float('nan'), index=df_slice.index)
    if trade_type == 'BUY':
        y_pos = df_slice.loc[exit_time, 'high'] * (1 + padding)
        exit_marker_shape = 'v'
    else:  # SELL
        y_pos = df_slice.loc[exit_time, 'low'] * (1 - padding)
        exit_marker_shape = '^'
    exit_series[exit_time] = y_pos
    exit_marker = mpf.make_addplot(
        exit_series, type='scatter', color='red', marker=exit_marker_shape, markersize=120
    )

    # Tambahkan garis indikator BB kalau ada
    bb_cols = [col for col in df_slice.columns if 'BB' in col]
    addplots = [entry_marker, exit_marker] + [mpf.make_addplot(df_slice[col], width=0.7) for col in bb_cols]

    # Simpan
    os.makedirs(output_folder, exist_ok=True)
    filename = f"{output_folder}/{trade_index:03d}_{trade_type}_PROFIT_{profit:,.0f}.png"

    mpf.plot(
        df_slice,
        type='candle',
        style=s,
        title=f"Trade #{trade_index} — {trade_type} — Profit: ${profit:,.2f}",
        ylabel='Price',
        addplot=addplots,
        figsize=(16, 8),
        savefig=filename
    )
    print(f"Chart untuk trade #{trade_index} disimpan.")
    # Sama seperti sebelumnya, tidak perlu return value.
