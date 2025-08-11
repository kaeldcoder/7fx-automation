import MetaTrader5 as mt5
import pandas as pd
import pandas_ta
import mplfinance as mpf
import matplotlib.pyplot as plt
import os
import calendar
from datetime import datetime, time
from Library.data_handler.data_handler import get_rates, get_symbol_info
from fpdf import FPDF

class PoseidonWave:
    strategy_name = "Poseidon Wave V.1"

    live_status_labels = {
        "condition": "Market Condition: ",
        "wave_position": "Wave Power: "
    }

    parameters = {
        "wave_period": {"display_name": "Wave pressure", "type": "int", "default": 36},
        "fixed_lot_size": {
            "display_name": "Fixed Lot Size", 
            "type": "float", 
            "default": 0.1, 
            "step": 0.01,
        },
        "trade_start_time": {"display_name": "Jam Mulai Trading (HH:MM)", "type": "str", "default": "11:30"},
        "trade_end_time": {"display_name": "Jam Selesai Trading (HH:MM)", "type": "str", "default": "19:30"},
        "use_adx_filter": {"display_name": "Use ADX Filter", "type": "bool", "default": True},
        "adx_period": {"display_name": "ADX Period", "type": "int", "default": 14},
        "adx_threshold": {"display_name": "ADX Threshold", "type": "int", "default": 25},
        "use_stop_loss": {"display_name": "Use Stop Loss", "type": "bool", "default": True},
        "stop_loss_points": {"display_name": "SL Points", "type": "float", "default": 5.0}
    }
    def __init__(self, mt5_instance, config: dict):
        self.mt5 = mt5_instance
        self.config = config
        self.symbol = config.get('symbol')
        self.timeframe = config.get('timeframe_int')

        try:
            start_str = self.config.get("trade_start_time", "11:30")
            end_str = self.config.get("trade_end_time", "19:30")
            self.start_trade_time = datetime.strptime(start_str, '%H:%M').time()
            self.end_trade_time = datetime.strptime(end_str, '%H:%M').time()
        except ValueError:
            print("⚠️ Format waktu di config salah! Gunakan format 'HH:MM'. Menggunakan default 11:30-19:30.")
            self.start_trade_time = time(11, 30)
            self.end_trade_time = time(19, 30)

    def check_signal(self, open_positions_count: int = 0):
        tick = self.mt5.symbol_info_tick(self.symbol)
        symbol_info = get_symbol_info(self.symbol)

        status = {
            "symbol": self.symbol,
            "price": tick.bid if tick else 0,
            "condition": "Analyzing...",
            "trend_info": "-",
            "trade_signal": None
        }
        
        if not symbol_info or not tick:
            status["condition"] = "Symbol/Tick Data Unavailable"
            return status
        
        current_server_time = datetime.fromtimestamp(tick.time).time()
        if not (self.start_trade_time <= current_server_time <= self.end_trade_time):
            status["condition"] = "Outside Trading Hours"
            status["wave_position"] = "Sleeping"
            return status
        
        bb_length = self.config.get("wave_period", 36)
        df = get_rates(self.symbol, self.timeframe, count=bb_length + 2)

        if df.empty or len(df) < bb_length + 2:
            status["condition"] = "Insufficient Historical Data"
            return status
        
        df.ta.bbands(length=bb_length, std=2, append=True)

        df.dropna(inplace=True)
        if len(df) < 2:
            status["condition"] = "Not enough data post-indicator calculation"
            return status
        
        candle_sekarang = df.iloc[-1]
        candle_sebelumnya = df.iloc[-2]
        middle_band_col = f'BBM_{bb_length}_2.0'
        close_sekarang = candle_sekarang['close']
        middle_band_sekarang = candle_sekarang[middle_band_col]
        close_sebelumnya = candle_sebelumnya['close']
        middle_band_sebelumnya = candle_sebelumnya[middle_band_col]
        is_bullish_cross = close_sebelumnya < middle_band_sebelumnya and close_sekarang > middle_band_sekarang
        is_bearish_cross = close_sebelumnya > middle_band_sebelumnya and close_sekarang < middle_band_sekarang

        if open_positions_count == 0:
            if is_bullish_cross:
                status["condition"] = "Bullish Cross"
                status["wave_position"] = "Power UP"
                status["trade_signal"] = "BUY"
            elif is_bearish_cross:
                status["condition"] = "Bearish Cross"
                status["wave_position"] = "Power DOWN"
                status["trade_signal"] = "SELL"
            else:
                status["condition"] = "Waiting for Crossover"
                status["wave_position"] = "Neutral"
        else:
            status["condition"] = "Position Already Open"
            status["wave_position"] = "Monitoring"

        return status
    def _plot_equity_curve(self, equity_data: list, report_details: dict):
        if len(equity_data) < 2:
            print("Tidak cukup data untuk membuat kurva ekuitas.")
            return

        timestamps = [item[0] for item in equity_data]
        balances = [item[1] for item in equity_data]

        # --- MEMBUAT TEKS LAPORAN UNTUK GAMBAR ---
        report_string = "--- Laporan Backtest Bulanan ---\n"
        report_string += report_details['period'] + "\n"
        if report_details.get('trading_session_info'):
            report_string += report_details['trading_session_info'] + "\n"
        if report_details['adx_filter_info']:
            report_string += report_details['adx_filter_info'] + "\n"
        if report_details['sl_info']:
            report_string += report_details['sl_info'] + "\n"
        report_string += "---------------------------------\n"
        report_string += f"Initial Balance:        ${report_details['initial_balance']:,.2f}\n"
        report_string += f"Final Balance:          ${report_details['final_balance']:,.2f}\n"
        report_string += f"Peak Balance:           ${report_details['peak_balance']:,.2f} (Pada {report_details['peak_date']})\n"
        report_string += f"Lowest Balance:         ${report_details['trough_balance']:,.2f} (Pada {report_details['trough_date']})\n"
        report_string += "---------------------------------\n"
        report_string += f"Total Profit/Loss:      ${report_details['total_profit']:,.2f} ({report_details['roi']:.2f}%)\n"
        report_string += f"Total Trades:           {report_details['total_trades']}\n"
        report_string += f"Win Rate:               {report_details['win_rate']:.2f}%\n"

        fig, ax = plt.subplots(figsize=(16, 9))
        ax.plot(timestamps, balances, linestyle='-', marker='o', markersize=3, color='dodgerblue')

        fig.subplots_adjust(bottom=0.35)
        fig.text(0.05, 0.05, report_string, fontname='Courier New', fontsize=10,
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        ax.set_title(f"Kurva Ekuitas untuk {report_details['symbol']}", fontsize=16)
        ax.set_xlabel("Tanggal", fontsize=12)
        ax.set_ylabel("Saldo Akun ($)", fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.6)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.2f}'))
        
        run_directory = report_details['run_directory']
        filename = f"{run_directory}/equity_curve.png"
        os.makedirs(run_directory, exist_ok=True)
        
        plt.savefig(filename)
        plt.close()
        
        print(f"📈 Kurva Ekuitas dengan laporan lengkap disimpan: {filename}")

    def _plot_completed_trade(self, df_slice: pd.DataFrame, trade: dict, trade_index: int, output_folder: str):
        """
        Membuat plot untuk satu trade (entry ke exit) dengan penempatan marker yang akurat.
        """
        style = mpf.make_marketcolors(up='green', down='red', inherit=True)
        s = mpf.make_mpf_style(marketcolors=style, gridstyle=':')
        
        # Detail trade
        entry_time, exit_time = trade['entry_time'], trade['exit_time']
        trade_type, profit = trade['type'], trade['profit_usd']

        # Tentukan padding untuk jarak panah dari candle (0.5% dari harga)
        padding = 0.005 

        # --- Membuat Marker Entry (Panah Hijau) ---
        marker_entry_data = pd.Series(float('nan'), index=df_slice.index)
        if trade_type == 'BUY':
            # Tempatkan di bawah harga LOW candle entry
            y_pos = df_slice.loc[entry_time, 'low'] * (1 - padding)
            marker_shape = '^'
        else: # SELL
            # Tempatkan di atas harga HIGH candle entry
            y_pos = df_slice.loc[entry_time, 'high'] * (1 + padding)
            marker_shape = 'v'
        marker_entry_data[entry_time] = y_pos
        
        entry_marker = mpf.make_addplot(marker_entry_data, type='scatter', color='green', marker=marker_shape, markersize=200)

        # --- Membuat Marker Exit (Panah Merah) ---
        marker_exit_data = pd.Series(float('nan'), index=df_slice.index)
        if trade_type == 'BUY':
            # Exit dari BUY adalah sinyal SELL, tempatkan di atas HIGH candle exit
            y_pos = df_slice.loc[exit_time, 'high'] * (1 + padding)
            marker_shape = 'v'
        else: # SELL
            # Exit dari SELL adalah sinyal BUY, tempatkan di bawah LOW candle exit
            y_pos = df_slice.loc[exit_time, 'low'] * (1 - padding)
            marker_shape = '^'
        marker_exit_data[exit_time] = y_pos

        exit_marker = mpf.make_addplot(marker_exit_data, type='scatter', color='red', marker=marker_shape, markersize=200)

        # Kumpulkan semua add-on plot
        bb_cols = [col for col in df_slice.columns if 'BB' in col]
        addplots = [entry_marker, exit_marker] + [mpf.make_addplot(df_slice[col], width=0.7) for col in bb_cols]

        # Judul dan nama file
        filename = f"{output_folder}/{trade_index:03d}_{trade_type}_PROFIT_{profit:.0f}.png"
        os.makedirs(output_folder, exist_ok=True)
        
        # Generate plot
        mpf.plot(df_slice, type='candle', style=s, title=f"Trade #{trade_index}: {trade_type} | Profit: ${profit:,.2f}", ylabel='Price', addplot=addplots, figsize=(16, 8), savefig=filename)
        print(f"📸 Chart untuk trade #{trade_index} disimpan.")

    def create_summary_report_image(self, monthly_reports: list, config: dict):
        """
        Membuat satu gambar laporan rekapitulasi dari beberapa backtest bulanan.
        """
        if not monthly_reports:
            print("Tidak ada data laporan untuk dibuat rekapitulasinya.")
            return

        # --- 1. Agregasi Data ---
        total_profit = sum(r['total_profit'] for r in monthly_reports)
        total_trades = sum(r['total_trades'] for r in monthly_reports)
        
        # Hitung win rate keseluruhan (tertimbang)
        total_wins = sum(r['win_rate']/100 * r['total_trades'] for r in monthly_reports)
        overall_win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0
        
        months_profit = len([r for r in monthly_reports if r['total_profit'] > 0])
        months_loss = len(monthly_reports) - months_profit
        
        # Data untuk bar chart
        month_names = [datetime.strptime(r['period_for_filename'].split('_to_')[0], '%Y-%m-%d').strftime('%b') for r in monthly_reports]
        monthly_pnl = [r['total_profit'] for r in monthly_reports]

        # --- 2. Membuat Teks Laporan ---
        param_str = monthly_reports[0]['param_str'] # Ambil dari laporan pertama
        trading_session_str = monthly_reports[0].get('trading_session_info', '')
        report_string = "--- Rekapitulasi Backtest ---\n"
        report_string += f"Simbol: {config.get('symbol')}\n"
        report_string += f"Periode: {month_names[0]} - {month_names[-1]} {monthly_reports[0]['period_for_filename'][:4]}\n"
        if trading_session_str:
            report_string += f"{trading_session_str}\n"
        report_string += f"Parameter: {param_str}\n"
        report_string += "---------------------------------\n"
        label_width = 20
        report_string += f"{'Total Profit/Loss:':<{label_width}}${total_profit:,.2f}\n"
        report_string += f"{'Overall Win Rate:':<{label_width}}{overall_win_rate:.2f}%\n"
        report_string += f"{'Total Trades:':<{label_width}}{total_trades}\n"
        report_string += f"{'Bulan Profit:':<{label_width}}{months_profit}\n"
        report_string += f"{'Bulan Rugi:':<{label_width}}{months_loss}\n"
        
        # --- 3. Membuat Plot & Gambar ---
        fig = plt.figure(figsize=(12, 7))
        gs = fig.add_gridspec(1, 2, width_ratios=(1, 1)) # 1 baris, 2 kolom

        # Kolom kiri untuk teks
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.text(0.05, 0.95, report_string, fontname='Courier New', fontsize=11, va='top')
        ax1.axis('off')

        # Kolom kanan untuk bar chart
        ax2 = fig.add_subplot(gs[0, 1])
        colors = ['g' if p > 0 else 'r' for p in monthly_pnl]
        ax2.bar(month_names, monthly_pnl, color=colors)
        ax2.set_title("Profit/Loss Bulanan", fontsize=14)
        ax2.set_ylabel("Profit/Loss ($)")
        ax2.grid(axis='y', linestyle='--', alpha=0.7)
        ax2.axhline(0, color='black', linewidth=0.8) # Garis nol

        fig.suptitle("Laporan Kinerja Strategi", fontsize=18, weight='bold')
        fig.tight_layout(rect=[0, 0, 1, 0.96])

        # Simpan gambar
        time_str = monthly_reports[0].get('time_str', '') # Ambil dari laporan
        filename = f"summary_reports/SUMMARY_{config.get('symbol')}_{param_str}_T{time_str}.png"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        plt.savefig(filename)
        plt.close()

        print("\n" + "#"*80)
        print(f"📊 Laporan Rekapitulasi Akhir disimpan: {filename}")
        print("#"*80)

    def backtest(self, start_date_str: str, end_date_str: str, initial_balance: float = 1000.0):
        lot_size = self.config.get("fixed_lot_size", 0.1)
        bb_length = self.config.get("wave_period", 36)
        use_adx_filter = self.config.get("use_adx_filter", False)
        adx_period = self.config.get("adx_period", 14)
        adx_threshold = self.config.get("adx_threshold", 25)
        use_stop_loss = self.config.get("use_stop_loss", True)
        stop_loss_points = self.config.get("stop_loss_points", 5.0)

        time_str_for_filename = f"{self.start_trade_time.strftime('%H%M')}-{self.end_trade_time.strftime('%H%M')}"

        param_str = "NoFilter"
        if use_adx_filter:
            param_str = f"ADX({adx_period},{adx_threshold})"
        if use_stop_loss:
            if use_adx_filter:
                param_str += f"_SL({stop_loss_points})"
            else:
                param_str = f"SL({stop_loss_points})"

        run_directory = f"backtest_results/{self.symbol}_{start_date_str}_to_{end_date_str}_{param_str}_T{time_str_for_filename}"
        trades_output_folder = f"{run_directory}/trades"

        print(f"--- Memulai Backtest untuk [{self.strategy_name}] ---")
        print(f"Simbol: {self.symbol} | Timeframe: {self.timeframe}")
        print(f"Periode: {start_date_str} hingga {end_date_str}")
        symbol_info = self.mt5.symbol_info(self.symbol)
        if not symbol_info:
            print(f"Error: Gagal mendapatkan info untuk simbol {self.symbol}")
            return
        contract_size = symbol_info.trade_contract_size
        print(f"Initial Balance: ${initial_balance:,.2f} | Lot Size: {lot_size} | Contract Size: {contract_size}")
        print(f"Jam Trading Aktif: {self.start_trade_time.strftime('%H:%M')} - {self.end_trade_time.strftime('%H:%M')}")
        print("----------------------------------------------------")
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        rates = self.mt5.copy_rates_range(self.symbol, self.timeframe, start_date, end_date)
        if rates is None or len(rates) == 0:
            print("Error: Tidak ada data historis untuk rentang waktu yang dipilih.")
            return
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df.ta.bbands(length=bb_length, std=2, append=True)
        adx_col = None # Inisialisasi nama kolom ADX
        if use_adx_filter:
            print(f"Filter Aktif: ADX({adx_period}) > {adx_threshold}")
            df.ta.adx(length=adx_period, append=True)
            adx_col = f'ADX_{adx_period}'
        else:
            print("Filter ADX: Tidak Aktif")
        df.dropna(inplace=True)
        middle_band_col = f'BBM_{bb_length}_2.0'
        current_balance = initial_balance
        peak_balance = initial_balance
        trough_balance = initial_balance
        start_time = df.index[0] if not df.empty else datetime.now()
        equity_curve = [(start_time, initial_balance)]
        peak_balance_date = start_time
        trough_balance_date = start_time
        completed_trades = []
        active_trade = None
        current_position = None

        if use_stop_loss:
            print(f"Stop Loss Aktif: {stop_loss_points} points")

        # 4. Iterasi melalui setiap candle (logika profit diubah)
        for i in range(1, len(df)):
            candle_sekarang = df.iloc[i]
            candle_sebelumnya = df.iloc[i-1]
            is_in_trading_session = self.start_trade_time <= df.index[i].time() <= self.end_trade_time
            is_bullish_cross = candle_sebelumnya['close'] < candle_sebelumnya[middle_band_col] and candle_sekarang['close'] > candle_sekarang[middle_band_col]
            is_bearish_cross = candle_sebelumnya['close'] > candle_sebelumnya[middle_band_col] and candle_sekarang['close'] < candle_sekarang[middle_band_col]
            if current_position is not None and use_stop_loss:
                exit_price = None
                
                if current_position == 'BUY':
                    stop_loss_level = active_trade['entry_price'] - stop_loss_points
                    if candle_sekarang['low'] <= stop_loss_level:
                        exit_price = stop_loss_level
                        profit_usd = (exit_price - active_trade['entry_price']) * lot_size * contract_size
                
                elif current_position == 'SELL':
                    stop_loss_level = active_trade['entry_price'] + stop_loss_points
                    if candle_sekarang['high'] >= stop_loss_level:
                        exit_price = stop_loss_level
                        profit_usd = (active_trade['entry_price'] - exit_price) * lot_size * contract_size

                if exit_price is not None:
                    print(f"--- Posisi ditutup karena Stop Loss @ {exit_price} ---")
                    current_balance += profit_usd
                    equity_curve.append((df.index[i], current_balance))
                    
                    if current_balance > peak_balance:
                        peak_balance, peak_balance_date = current_balance, df.index[i]
                    if current_balance < trough_balance:
                        trough_balance, trough_balance_date = current_balance, df.index[i]
                    
                    active_trade.update({'exit_time': df.index[i], 'exit_price': exit_price, 'profit_usd': profit_usd})
                    completed_trades.append(active_trade)
                    
                    entry_iloc = df.index.get_loc(active_trade['entry_time'])
                    plot_start, plot_end = max(0, entry_iloc - 30), min(len(df), i + 15)
                    self._plot_completed_trade(df.iloc[plot_start:plot_end], active_trade, len(completed_trades), trades_output_folder)
                    
                    current_position = None
                    active_trade = None
                    continue
            signal_is_valid = True # Anggap valid secara default
            if use_adx_filter:
                adx_value = candle_sekarang[adx_col]
                if adx_value <= adx_threshold:
                    signal_is_valid = False

            if is_bullish_cross:
                if current_position == 'SELL':
                    exit_price = candle_sekarang['close']
                    profit_points = active_trade['entry_price'] - exit_price
                    profit_usd = profit_points * lot_size * contract_size
                    current_balance += profit_usd
                    equity_curve.append((df.index[i], current_balance))
                    if current_balance > peak_balance:
                        peak_balance = current_balance
                        peak_balance_date = df.index[i]
                    if current_balance < trough_balance:
                        trough_balance = current_balance
                        trough_balance_date = df.index[i]
                    active_trade.update({'exit_time': df.index[i], 'exit_price': exit_price, 'profit_usd': profit_usd})
                    completed_trades.append(active_trade)
                    
                    # --- PANGGIL PLOT SETELAH TRADE SELESAI ---
                    entry_iloc = df.index.get_loc(active_trade['entry_time'])
                    exit_iloc = i
                    # Potong DataFrame dari 30 candle sebelum entry hingga 15 candle setelah exit
                    plot_start = max(0, entry_iloc - 30)
                    plot_end = min(len(df), exit_iloc + 15)
                    trade_index = len(completed_trades) # Indeks dimulai dari 1
                    self._plot_completed_trade(df.iloc[plot_start:plot_end], active_trade, trade_index, trades_output_folder)

                    print(f"🔻 SELL Closed @ {exit_price} | Profit: ${profit_usd:,.2f} | New Balance: ${current_balance:,.2f}")
                    current_position = None; active_trade = None

                if current_position is None and is_in_trading_session:
                    if signal_is_valid:
                        entry_price = candle_sekarang['close']
                        entry_time = df.index[i]
                        active_trade = {'entry_time': entry_time, 'entry_price': entry_price, 'type': 'BUY'}
                        current_position = 'BUY'
                        print(f"✅ BUY Opened @ {entry_price} on {entry_time.strftime('%Y-%m-%d %H:%M')}")
                    elif use_adx_filter: # Hanya print jika filter aktif
                        print(f"-> Sinyal BUY pada {df.index[i].strftime('%H:%M')} diabaikan (ADX rendah).")

            elif is_bearish_cross:
                if current_position == 'BUY':
                    exit_price = candle_sekarang['close']
                    profit_points = exit_price - active_trade['entry_price']
                    profit_usd = profit_points * lot_size * contract_size
                    current_balance += profit_usd
                    equity_curve.append((df.index[i], current_balance))
                    if current_balance > peak_balance:
                        peak_balance = current_balance
                        peak_balance_date = df.index[i]
                    if current_balance < trough_balance:
                        trough_balance = current_balance
                        trough_balance_date = df.index[i]
                    active_trade.update({'exit_time': df.index[i], 'exit_price': exit_price, 'profit_usd': profit_usd})
                    completed_trades.append(active_trade)

                    entry_iloc = df.index.get_loc(active_trade['entry_time'])
                    exit_iloc = i
                    # Potong DataFrame dari 30 candle sebelum entry hingga 15 candle setelah exit
                    plot_start = max(0, entry_iloc - 30)
                    plot_end = min(len(df), exit_iloc + 15)
                    trade_index = len(completed_trades) # Indeks dimulai dari 1
                    self._plot_completed_trade(df.iloc[plot_start:plot_end], active_trade, trade_index, trades_output_folder)

                    print(f"✅ BUY Closed @ {exit_price} | Profit: ${profit_usd:,.2f} | New Balance: ${current_balance:,.2f}")
                    current_position = None; active_trade = None

                if current_position is None and is_in_trading_session:
                    if signal_is_valid:
                        entry_price = candle_sekarang['close']
                        entry_time = df.index[i]
                        active_trade = {'entry_time': entry_time, 'entry_price': entry_price, 'type': 'SELL'}
                        current_position = 'SELL'
                        print(f"🔻 SELL Opened @ {entry_price} on {entry_time.strftime('%Y-%m-%d %H:%M')}")
                    elif use_adx_filter: # Hanya print jika filter aktif
                        print(f"-> Sinyal SELL pada {df.index[i].strftime('%H:%M')} diabaikan (ADX rendah).")
        
        # 5. Tampilkan Laporan Hasil Backtest dengan info saldo
        print("\n--- Laporan Backtest Selesai ---")
        print(f"Laporan untuk: {self.symbol} ({start_date_str} s/d {end_date_str})")
        print("---------------------------------")
        report_details = {
            "symbol": self.symbol,
            "period": f"Laporan untuk: {self.symbol} ({start_date_str} s/d {end_date_str})",
            "trading_session_info": f"Jam Trading: {self.start_trade_time.strftime('%H:%M')} - {self.end_trade_time.strftime('%H:%M')}",
            "time_str": time_str_for_filename,
            "period_for_filename": f"{start_date_str}_to_{end_date_str}",
            "param_str": param_str,
            "adx_filter_info": f"Filter ADX Aktif: P={self.config.get('adx_period', 14)}, T={self.config.get('adx_threshold', 25)}" if self.config.get("use_adx_filter") else None,
            "sl_info": f"Stop Loss Aktif: {stop_loss_points} points" if use_stop_loss else None,
            "initial_balance": initial_balance,
            "final_balance": current_balance,
            "peak_balance": peak_balance,
            "peak_date": peak_balance_date.strftime('%Y-%m-%d %H:%M'),
            "trough_balance": trough_balance,
            "trough_date": trough_balance_date.strftime('%Y-%m-%d %H:%M'),
            "total_profit": current_balance - initial_balance,
            "roi": (current_balance - initial_balance) / initial_balance * 100 if initial_balance > 0 else 0,
            "total_trades": len(completed_trades),
            "win_rate": (len([t for t in completed_trades if t['profit_usd'] > 0]) / len(completed_trades)) * 100 if completed_trades else 0,
            "run_directory": run_directory,
        }
        report_details['equity_curve'] = equity_curve

        self._plot_equity_curve(equity_curve, report_details)
        return report_details
    
    def _create_summary_page_image(self, monthly_reports: list, config: dict, output_filename: str):
        """
        Membuat Halaman 1 PDF: Gambar ringkasan performa yang berisi teks,
        bar chart P/L, dan grid kurva ekuitas bulanan.
        """
        num_months = len(monthly_reports)
        # Tentukan layout grid: 2 kolom untuk plot mini, sisanya untuk baris
        cols = 2
        plot_rows = (num_months + cols - 1) // cols
        # Total baris = 1 (teks) + 1 (bar chart) + plot_rows
        total_rows = 2 + plot_rows
        
        fig = plt.figure(figsize=(16, 4 * total_rows))
        gs = fig.add_gridspec(total_rows, cols)

        # --- 1. Area Teks Laporan ---
        ax_text = fig.add_subplot(gs[0, :])
        ax_text.axis('off')
        
        # Agregasi data keseluruhan
        total_profit = sum(r['total_profit'] for r in monthly_reports)
        total_trades = sum(r['total_trades'] for r in monthly_reports)
        total_wins = sum(r['win_rate']/100 * r['total_trades'] for r in monthly_reports)
        overall_win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0
        
        param_str = monthly_reports[0]['param_str']
        time_str = monthly_reports[0].get('trading_session_info', '')
        start_month_name = datetime.strptime(monthly_reports[0]['period_for_filename'].split('_to_')[0], '%Y-%m-%d').strftime('%b')
        end_month_name = datetime.strptime(monthly_reports[-1]['period_for_filename'].split('_to_')[0], '%Y-%m-%d').strftime('%b')
        year = monthly_reports[0]['period_for_filename'][:4]
        
        # Membuat header teks
        report_string = "--- Rekapitulasi Backtest Tahunan ---\n"
        report_string += f"Simbol: {config.get('symbol')} | Periode: {start_month_name} - {end_month_name} {year}\n"
        report_string += f"{time_str} | Parameter: {param_str}\n"
        report_string += "----------------------------------------------------------------------------------\n"
        report_string += "PERFORMA KESELURUHAN\n"
        report_string += "----------------------------------------------------------------------------------\n"
        report_string += f"Total Profit/Loss: ${total_profit:,.2f} | Overall Win Rate: {overall_win_rate:.2f}% | Total Trades: {total_trades}\n"
        report_string += "----------------------------------------------------------------------------------\n"
        report_string += "DETAIL PERFORMA BULANAN\n"
        report_string += "----------------------------------------------------------------------------------\n"
        report_string += f"{'Bulan':<8} | {'P/L ($)':>12} | {'Win Rate (%)':>15} | {'Peak ($)':>14} | {'Trough ($)':>14}\n"
        report_string += "-"*82 + "\n"

        # Menambahkan detail bulanan
        for r in monthly_reports:
            month_name = datetime.strptime(r['period_for_filename'].split('_to_')[0], '%Y-%m-%d').strftime('%b %Y')
            report_string += f"{month_name:<8} | ${r['total_profit']:>10,.2f} | {r['win_rate']:>14.2f} | ${r['peak_balance']:>12,.2f} | ${r['trough_balance']:>12,.2f}\n"

        ax_text.text(0, 1, report_string, fontname='Courier New', fontsize=11, va='top')

        # --- 2. Bar Chart P/L Bulanan ---
        ax_bar = fig.add_subplot(gs[1, 0])
        month_names = [datetime.strptime(r['period_for_filename'].split('_to_')[0], '%Y-%m-%d').strftime('%b') for r in monthly_reports]
        monthly_pnl = [r['total_profit'] for r in monthly_reports]
        colors = ['g' if p > 0 else 'r' for p in monthly_pnl]
        ax_bar.bar(month_names, monthly_pnl, color=colors)
        ax_bar.set_title("Profit/Loss Bulanan", fontsize=14)
        ax_bar.set_ylabel("Profit/Loss ($)")
        ax_bar.grid(axis='y', linestyle='--', alpha=0.7)
        ax_bar.axhline(0, color='black', linewidth=0.8)

        # --- 3. Grid Kurva Ekuitas Mini ---
        for i, report in enumerate(monthly_reports):
            row = 2 + (i // cols)
            col = i % cols
            ax_mini = fig.add_subplot(gs[row, col])
            
            equity_data = report['equity_curve']
            timestamps = [item[0] for item in equity_data]
            balances = [item[1] for item in equity_data]
            
            color = 'g' if report['total_profit'] > 0 else 'r'
            ax_mini.plot(timestamps, balances, color=color, linewidth=1.5)
            
            month_name = datetime.strptime(report['period_for_filename'].split('_to_')[0], '%Y-%m-%d').strftime('%B %Y')
            ax_mini.set_title(f"Ekuitas {month_name}", fontsize=10)
            ax_mini.grid(True, linestyle='--', alpha=0.5)
            ax_mini.tick_params(axis='x', rotation=30)
            ax_mini.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))

        fig.suptitle("Laporan Kinerja Strategi", fontsize=20, weight='bold')
        fig.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.savefig(output_filename)
        plt.close()

    def create_final_pdf_report(self, monthly_reports: list, config: dict):
        """
        Fungsi utama untuk membuat laporan PDF multi-halaman.
        """
        if not monthly_reports:
            print("Tidak ada laporan bulanan untuk dibuat menjadi PDF.")
            return

        print("\n" + "#"*80)
        print("Membuat Laporan PDF Komprehensif...")

        # Menentukan nama file berdasarkan parameter
        param_str = monthly_reports[0]['param_str']
        time_str = monthly_reports[0].get('time_str', '')
        pdf_filename = f"summary_reports/FINAL_REPORT_{config.get('symbol')}_{param_str}_T{time_str}.pdf"
        summary_image_path = f"summary_reports/temp_summary_page.png"
        os.makedirs(os.path.dirname(pdf_filename), exist_ok=True)

        # 1. Buat gambar halaman ringkasan
        self._create_summary_page_image(monthly_reports, config, summary_image_path)
        print(f"📄 Halaman ringkasan dibuat: {summary_image_path}")

        # 2. Rakit PDF
        pdf = FPDF('P', 'mm', 'A4') # Portrait, milimeter, ukuran A4
        
        # Tambahkan halaman ringkasan
        pdf.add_page()
        pdf.set_font('helvetica', 'B', 16)
        pdf.cell(0, 10, 'Halaman 1: Ringkasan Kinerja Strategi', 0, 1, 'C')
        # Ukuran gambar di PDF (A4 P: 210x297 mm), sisakan margin
        pdf.image(summary_image_path, x=10, y=25, w=190)

        # 3. Tambahkan halaman detail ekuitas per bulan
        for i, report in enumerate(monthly_reports):
            pdf.add_page()
            pdf.set_font('helvetica', 'B', 16)
            month_name = datetime.strptime(report['period_for_filename'].split('_to_')[0], '%Y-%m-%d').strftime('%B %Y')
            pdf.cell(0, 10, f"Halaman {i+2}: Detail Ekuitas - {month_name}", 0, 1, 'C')
            
            monthly_equity_image_path = f"{report['run_directory']}/equity_curve.png"
            if os.path.exists(monthly_equity_image_path):
                pdf.image(monthly_equity_image_path, x=10, y=25, w=190)
            else:
                pdf.set_font('helvetica', '', 12)
                pdf.cell(0, 10, f"Error: Gambar tidak ditemukan di {monthly_equity_image_path}", 0, 1)
        
        # 4. Simpan PDF dan hapus file sementara
        pdf.output(pdf_filename)
        os.remove(summary_image_path)

        print("#"*80)
        print(f"✅ Laporan PDF Lengkap telah disimpan: {pdf_filename}")
        print("#"*80)
    
if __name__ == '__main__':
    # Inisialisasi koneksi ke MetaTrader 5
    if not mt5.initialize():
        print("initialize() gagal, error code =", mt5.last_error())
        quit()

    # Konfigurasi untuk strategi
    config = {
        'symbol': 'XAUUSD',
        'timeframe_str': 'm5',
        'timeframe_int': mt5.TIMEFRAME_M5,
        'wave_period': 36,
        'fixed_lot_size': 0.2,

        'trade_start_time': '14:30',
        'trade_end_time': '19:30',

        'use_adx_filter': False, # <-- AKTIFKAN FILTER
        'adx_period': 14,
        'adx_threshold': 15,

        'use_stop_loss': False,     # <-- AKTIFKAN STOP LOSS
        'stop_loss_points': 10.0
    }

    # Buat instance strategi
    strategy = PoseidonWave(mt5, config)

    year = 2025
    start_month = 1 # Januari
    end_month = 7   # Juli

    monthly_reports = []

    for month in range(start_month, end_month + 1):
        # Tentukan hari pertama dan terakhir untuk bulan saat ini
        num_days = calendar.monthrange(year, month)[1]
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{num_days}"

        # Beri pemisah antar laporan di terminal
        print("\n" + "="*80)
        print(f"MEMULAI BACKTEST UNTUK PERIODE: {start_date} s/d {end_date}")
        print("="*80 + "\n")

        # Jalankan backtest untuk bulan ini
        report = strategy.backtest(start_date_str=start_date, end_date_str=end_date)
        if report: # Pastikan backtest menghasilkan laporan
            monthly_reports.append(report)
    
    if monthly_reports:
        strategy.create_final_pdf_report(monthly_reports, config)

    # Tutup koneksi MT5
    mt5.shutdown()