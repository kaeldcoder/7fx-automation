# Nama File: worker_backtest.py
import sys
import os
import shutil
import itertools

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

import MetaTrader5 as mt5
import pandas as pd
import pandas_ta
import numpy as np
import mplfinance as mpf
import matplotlib.pyplot as plt
import calendar
import json
import math
from zoneinfo import ZoneInfo
from fpdf.enums import XPos, YPos
from datetime import datetime, time, timezone
# Asumsikan library ini ada di folder 'Library' Anda
from Library.data_handler.data_handler import get_rates, get_symbol_info 
from fpdf import FPDF
from utils import (
    send_status, simulate_equity_stops, to_epoch_ms as _to_epoch_ms,
    spread_pts as _u_spread_pts,
    exec_price as _u_exec_price,
    commission_leg_usd as _u_commission_leg_usd,
    pnl_usd as _u_pnl_usd,
    unrealized_pnl as _u_unrealized_pnl,
    in_session as _u_in_session,
)
from plotting import plot_equity_curve_impl, plot_completed_trade_impl
from reporting import create_final_pdf_report_impl

# ==============================================================================
#  SELURUH KELAS PoseidonWave ANDA DITEMPATKAN DI SINI TANPA PERUBAHAN
# ==============================================================================
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

    class _EquityDownsampler:
        """Keep event points, periodic samples, and min/max/last per window.
        Jika melebihi cap, otomatis diperkasar per bucket (min, max, last)."""
        def __init__(self, every_n_bars: int, window_size: int, max_points: int):
            self.every_n = max(1, int(every_n_bars))
            self.W = max(2, int(window_size))
            self.cap = max(1000, int(max_points))
            self._points = []              # (t_ms, eq, tag)
            self._bar_index = -1
            self._w_cache = []             # cache window aktif

        @staticmethod
        def _dedupe_sorted(seq):
            out, last_t = [], None
            for t, e, tag in seq:
                if t != last_t:
                    out.append((t, e))
                    last_t = t
            return out

        def add(self, t_ms: int, eq: float, is_event: bool):
            self._bar_index += 1
            self._w_cache.append((t_ms, eq))
            if is_event:
                self._points.append((t_ms, eq, 'evt'))
            if self._bar_index % self.every_n == 0:
                self._points.append((t_ms, eq, 'per'))
            if len(self._w_cache) >= self.W:
                t_vals, e_vals = zip(*self._w_cache)
                i_min = int(min(range(len(e_vals)), key=lambda i: e_vals[i]))
                i_max = int(max(range(len(e_vals)), key=lambda i: e_vals[i]))
                self._points.append((t_vals[i_min], e_vals[i_min], 'min'))
                self._points.append((t_vals[i_max], e_vals[i_max], 'max'))
                self._points.append((t_vals[-1],    e_vals[-1],    'last'))
                self._w_cache.clear()

        def finalize(self):
            if self._w_cache:
                t_vals, e_vals = zip(*self._w_cache)
                i_min = int(min(range(len(e_vals)), key=lambda i: e_vals[i]))
                i_max = int(max(range(len(e_vals)), key=lambda i: e_vals[i]))
                self._points.append((t_vals[i_min], e_vals[i_min], 'min'))
                self._points.append((t_vals[i_max], e_vals[i_max], 'max'))
                self._points.append((t_vals[-1],    e_vals[-1],    'last'))
                self._w_cache.clear()
            self._points.sort(key=lambda x: x[0])
            out = self._dedupe_sorted(self._points)
            if len(out) > self.cap:
                step = int(math.ceil(len(out) / self.cap))
                buckets = [out[i:i+step] for i in range(0, len(out), step)]
                reduced = []
                for b in buckets:
                    t_vals, e_vals = zip(*b)
                    i_min = int(min(range(len(e_vals)), key=lambda i: e_vals[i]))
                    i_max = int(max(range(len(e_vals)), key=lambda i: e_vals[i]))
                    reduced.append(b[i_min])
                    if i_max != i_min:
                        reduced.append(b[i_max])
                    reduced.append(b[-1])
                # re-sort & unique timestamp, keep last equity per t
                tmp = {}
                for t, e in reduced:
                    tmp[t] = e
                out = sorted(tmp.items())
            return out
    
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

        self.eq_every_n_bars  = int(self.config.get('equity_every_n_bars', 5))
        self.eq_window_size   = int(self.config.get('equity_window_size', 20))
        self.eq_max_points    = int(self.config.get('equity_max_points', 20000))
        self.eq_write_parquet = bool(self.config.get('equity_write_parquet', True))
        self.eq_write_csv     = bool(self.config.get('equity_write_csv', False))

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
        is_bullish_cross = candle_sebelumnya['close'] < candle_sebelumnya[middle_band_col] and candle_sekarang['close'] > candle_sekarang[middle_band_col]
        is_bearish_cross = candle_sebelumnya['close'] > candle_sebelumnya[middle_band_col] and candle_sekarang['close'] < candle_sekarang[middle_band_col]

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
        return plot_equity_curve_impl(equity_data, report_details)

    def _plot_completed_trade(self, df_slice: pd.DataFrame, trade: dict, trade_index: int, output_folder: str):
        return plot_completed_trade_impl(df_slice, trade, trade_index, output_folder)

    def backtest(self, start_date_str: str, end_date_str: str, initial_balance: float = 1000.0):
        lot_size = self.config.get("fixed_lot_size", 0.1)
        bb_length = self.config.get("wave_period", 36)
        use_adx_filter = self.config.get("use_adx_filter", False)
        adx_period = self.config.get("adx_period", 14)
        adx_threshold = self.config.get("adx_threshold", 25)
        use_stop_loss = self.config.get("use_stop_loss", True)
        stop_loss_points = self.config.get("stop_loss_points", 5.0)

        time_str_for_filename = f"{self.start_trade_time.strftime('%H%M')}-{self.end_trade_time.strftime('%H%M')}"
        param_str = f"ADX({adx_threshold})" if use_adx_filter else "NoFilter"
        if use_stop_loss:
            param_str += f"_SL({stop_loss_points})"

        run_directory = os.path.join(
            'Backtester', 'Hasil Laporan PDF', self.symbol, 
            start_date_str.split('-')[0], # Tahun
            f"L{lot_size}_W{bb_length}_S{time_str_for_filename}" # Folder Sesi
        )
        os.makedirs(run_directory, exist_ok=True)

        print(f"--- Memulai Backtest untuk [{self.strategy_name}] ---")
        print(f"Simbol: {self.symbol} | Periode: {start_date_str} hingga {end_date_str}")
        symbol_info = self.mt5.symbol_info(self.symbol)
        if not symbol_info:
            print(f"Error: Gagal mendapatkan info untuk simbol {self.symbol}")
            return
        contract_size = symbol_info.trade_contract_size
        print(f"Initial Balance: ${initial_balance:,.2f} | Lot Size: {lot_size} | Contract Size: {contract_size}")
        print(f"Jam Trading: {self.start_trade_time.strftime('%H:%M')} - {self.end_trade_time.strftime('%H:%M')}")
        print("----------------------------------------------------")

        point = getattr(symbol_info, 'point', 0.01) if symbol_info else 0.01
        digits = getattr(symbol_info, 'digits', 2) if symbol_info else 2
        commission_rt_usd = float(self.config.get('commission_per_lot_roundturn_usd', 7.0))
        slippage_pts = float(self.config.get('slippage_points', 0.0))
        use_dyn_spread = bool(self.config.get('use_dynamic_spread', False))
        fallback_spread_pts = float(self.config.get('avg_spread_points', 0.0))

        def _spread_pts(i: int) -> float:
            return _u_spread_pts(i, df, use_dyn_spread, fallback_spread_pts)

        def _exec_price(side, close_bid, spr_pts, leg, is_market=True, level_price=None):
            return _u_exec_price(side, close_bid, spr_pts, leg, point, slippage_pts, is_market, level_price)

        def _commission_leg_usd(lot: float) -> float:
            return _u_commission_leg_usd(commission_rt_usd, lot)

        def _pnl_usd(side, entry_px, exit_px, lot) -> float:
            return _u_pnl_usd(side, entry_px, exit_px, lot, contract_size)
        
        def _unrealized_pnl(side, entry_px, close_bid, lot) -> float:
            return _u_unrealized_pnl(side, entry_px, close_bid, lot, contract_size)
        
        def _in_session(ts_utc) -> bool:
            return _u_in_session(ts_utc, self.start_trade_time, self.end_trade_time, session_base, server_tz_name)
        
        def _augment_trade_fields(side: str, exit_i: int, spr_pts_exit: float,
                                  close_bid_exit: float, commission_exit: float,
                                  net_pnl_exec_based: float):
            """
            Syarat:
              - active_trade punya: entry_price_ref_close_bid, entry_spread_points,
                entry_slippage_points, commission_entry_usd, entry_index, mfe_usd, mae_usd
              - spread/slippage dihitung TANPA look-ahead.
            """
            lot = float(self.config.get("fixed_lot_size", 0.1))
            entry_bid = float(active_trade.get('entry_price_ref_close_bid'))
            exit_bid  = float(close_bid_exit)

            # PnL gerak harga murni (gross PnL sebelum semua biaya), pakai BID→BID
            if side == 'BUY':
                gross_move_usd = (exit_bid - entry_bid) * lot * float(contract_size)
                spread_cost_usd = float(active_trade.get('entry_spread_points', 0.0)) * point * lot * float(contract_size)
            else:  # SELL
                gross_move_usd = (entry_bid - exit_bid) * lot * float(contract_size)
                spread_cost_usd = float(spr_pts_exit) * point * lot * float(contract_size)

            slippage_points_total = float(active_trade.get('entry_slippage_points', 0.0)) + float(slippage_pts)
            slippage_usd = slippage_points_total * point * lot * float(contract_size)
            commission_total = float(active_trade.get('commission_entry_usd', 0.0)) + float(commission_exit)

            # Net PnL konsisten (gross_move - spread - slippage - commission)
            net_pnl_usd = gross_move_usd - (spread_cost_usd + slippage_usd + commission_total)

            # Bars held
            bars_held = int(exit_i - int(active_trade.get('entry_index', exit_i)))

            # Simpan field ML-ready; pertahankan profit_usd untuk kompatibilitas lama
            active_trade.update({
                'lot': lot,
                'bars_held': bars_held,
                'gross_pnl_usd': gross_move_usd,         # murni gerak harga (sebelum biaya)
                'commission_usd': commission_total,
                'slippage_usd': slippage_usd,
                'spread_cost_usd': spread_cost_usd,
                'net_pnl_usd': net_pnl_usd,
                'profit_usd': net_pnl_usd,               # kompatibel dengan report lama
            })
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        rates = self.mt5.copy_rates_range(self.symbol, self.timeframe, start_date, end_date)
        if rates is None or len(rates) == 0:
            print(f"Error: Tidak ada data historis untuk {start_date_str}.", file=sys.stderr)
            return None

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df.set_index('time', inplace=True)

        df.ta.bbands(length=bb_length, std=2, append=True)
        adx_col = f'ADX_{adx_period}'
        if use_adx_filter:
            df.ta.adx(length=adx_period, append=True)
        df.dropna(inplace=True)

        middle_band_col = f'BBM_{bb_length}_2.0'
        symbol_info = get_symbol_info(self.symbol)
        contract_size = symbol_info.trade_contract_size if symbol_info else 1.0

        current_balance = initial_balance
        peak_balance = initial_balance
        trough_balance = initial_balance

        eq_ds = self._EquityDownsampler(self.eq_every_n_bars, self.eq_window_size, self.eq_max_points)
        realized_balance = current_balance  # saldo yang hanya berubah saat exit

        # seed titik awal di bar pertama
        equity_seed = realized_balance  # belum ada posisi → unrealized 0
        eq_ds.add(_to_epoch_ms(df.index[0]), float(equity_seed), is_event=True)
        start_time = df.index[0] if not df.empty else pd.Timestamp.now(tz='UTC')
        equity_curve = [(start_time, initial_balance)]
        peak_balance_date = start_time
        trough_balance_date = start_time
        completed_trades = []
        active_trade = None
        current_position = None

        margin_called = False

        server_tz_name = str(self.config.get('server_tz', 'UTC'))
        session_base = str(self.config.get('session_base_tz', 'UTC')).upper()
        
        trade_seq = 0

        for i in range(1, len(df)):
            if current_balance < 0:
                margin_called = True
                if current_position is not None and active_trade is not None:
                    exit_i = i
                    spr_pts = _spread_pts(exit_i)
                    close_bid = float(df.iloc[exit_i]['close'])
                    exit_exec = _exec_price(current_position, close_bid, spr_pts, leg='exit', is_market=True)
                    commission_exit = _commission_leg_usd(lot_size)

                    gross_pnl = _pnl_usd(current_position, active_trade['entry_price'], exit_exec, lot_size)
                    net_pnl = gross_pnl - (active_trade.get('commission_entry_usd', 0.0) + commission_exit)
                    current_balance += net_pnl
                    current_balance = 0.0

                    equity_curve.append((df.index[exit_i], current_balance))
                    active_trade.update({
                        'exit_time': df.index[exit_i],
                        'exit_price': exit_exec,
                        'profit_usd': net_pnl,                # NET
                        'gross_pnl_usd': gross_pnl,
                        'commission_exit_usd': commission_exit,
                        'commission_total_usd': active_trade.get('commission_entry_usd', 0.0) + commission_exit,
                        'status': 'MARGIN CALL',
                        'reason_exit': 'margin_call'
                    })
                    _augment_trade_fields(
                        side=current_position,
                        exit_i=i,
                        spr_pts_exit=spr_pts,
                        close_bid_exit=close_bid,
                        commission_exit=commission_exit,
                        net_pnl_exec_based=net_pnl
                    )
                    active_trade.update({
                        'side': current_position,
                        'exit_ts_epoch_ms': _to_epoch_ms(df.index[exit_i]),
                        'entry_ts_epoch_ms': _to_epoch_ms(active_trade['entry_time'])
                    })
                    completed_trades.append(active_trade)
                    current_position = None
                    active_trade = None
                break

            candle_sekarang = df.iloc[i]
            candle_sebelumnya = df.iloc[i-1]
            is_in_trading_session = _in_session(df.index[i])

            close_bid_now = float(candle_sekarang['close'])
            unreal = _unrealized_pnl(current_position, active_trade['entry_price'] if active_trade else 0.0, close_bid_now, lot_size)
            equity_t = realized_balance + unreal
            eq_ds.add(_to_epoch_ms(df.index[i]), float(equity_t), is_event=False)

            if current_position is not None and active_trade is not None:
                entry_bid = float(active_trade['entry_price_ref_close_bid'])
                hi = float(candle_sekarang['high'])
                lo = float(candle_sekarang['low'])
                if current_position == 'BUY':
                    mfe_usd = max(0.0, (hi - entry_bid) * float(lot_size) * float(contract_size))
                    mae_usd = max(0.0, (entry_bid - lo) * float(lot_size) * float(contract_size))
                else:
                    mfe_usd = max(0.0, (entry_bid - lo) * float(lot_size) * float(contract_size))
                    mae_usd = max(0.0, (hi - entry_bid) * float(lot_size) * float(contract_size))
                active_trade['mfe_usd'] = max(float(active_trade.get('mfe_usd', 0.0)), float(mfe_usd))
                active_trade['mae_usd'] = max(float(active_trade.get('mae_usd', 0.0)), float(mae_usd))

            if current_position is not None and use_stop_loss:
                exit_price = None
                sl_buy = active_trade['entry_price'] - stop_loss_points
                sl_sell = active_trade['entry_price'] + stop_loss_points
                if current_position == 'BUY' and candle_sekarang['low'] <= sl_buy:
                    exit_price = sl_buy
                elif current_position == 'SELL' and candle_sekarang['high'] >= sl_sell:
                    exit_price = sl_sell
                
                if exit_price is not None:
                    spr_pts = _spread_pts(i)
                    close_bid = float(candle_sekarang['close'])
                    exit_exec = _exec_price(current_position, close_bid, spr_pts, leg='exit', is_market=False, level_price=exit_price)
                    commission_exit = _commission_leg_usd(lot_size)

                    gross_pnl = _pnl_usd(current_position, active_trade['entry_price'], exit_exec, lot_size)
                    net_pnl = gross_pnl - (active_trade.get('commission_entry_usd', 0.0) + commission_exit)

                    realized_balance += net_pnl
                    current_balance = realized_balance
                    eq_ds.add(_to_epoch_ms(df.index[i]), float(current_balance), is_event=True)
                    equity_curve.append((df.index[i], current_balance))

                    active_trade.update({
                        'exit_time': df.index[i],
                        'exit_price': exit_exec,
                        'profit_usd': net_pnl,                # NET PnL (dipakai downstream)
                        'gross_pnl_usd': gross_pnl,
                        'commission_exit_usd': commission_exit,
                        'commission_total_usd': active_trade.get('commission_entry_usd', 0.0) + commission_exit,
                        'reason_exit': 'sl'
                    })
                    _augment_trade_fields(
                        side=current_position,
                        exit_i=i,
                        spr_pts_exit=spr_pts,
                        close_bid_exit=close_bid,
                        commission_exit=commission_exit,
                        net_pnl_exec_based=net_pnl
                    )
                    active_trade.update({
                        'side': current_position,
                        'exit_ts_epoch_ms': _to_epoch_ms(df.index[i]),
                        'entry_ts_epoch_ms': _to_epoch_ms(active_trade['entry_time'])
                    })
                    completed_trades.append(active_trade)

                    if self.config.get('plot_individual_trades'):
                        trade_df_slice = df.loc[active_trade['entry_time']:active_trade['exit_time']]
                        chart_folder = os.path.join(run_directory, "Individual_Charts")
                        self._plot_completed_trade(trade_df_slice, active_trade, len(completed_trades), chart_folder)

                    current_position = None; active_trade = None
                    continue

            # Logika Sinyal
            is_bullish_cross = candle_sebelumnya['close'] < candle_sebelumnya[middle_band_col] and candle_sekarang['close'] > candle_sekarang[middle_band_col]
            is_bearish_cross = candle_sebelumnya['close'] > candle_sebelumnya[middle_band_col] and candle_sekarang['close'] < candle_sekarang[middle_band_col]
            signal_is_valid = not use_adx_filter or (use_adx_filter and candle_sekarang[adx_col] > adx_threshold)

            # Close and Reverse Logic
            if (is_bullish_cross and current_position == 'SELL') or (is_bearish_cross and current_position == 'BUY'):
                spr_pts = _spread_pts(i)
                close_bid = float(candle_sekarang['close'])
                exit_exec = _exec_price(current_position, close_bid, spr_pts, leg='exit', is_market=True)
                commission_exit = _commission_leg_usd(lot_size)

                gross_pnl = _pnl_usd(current_position, active_trade['entry_price'], exit_exec, lot_size)
                net_pnl = gross_pnl - (active_trade.get('commission_entry_usd', 0.0) + commission_exit)

                current_balance += net_pnl
                realized_balance += net_pnl
                current_balance = realized_balance
                eq_ds.add(_to_epoch_ms(df.index[i]), float(current_balance), is_event=True)
                equity_curve.append((df.index[i], current_balance))

                active_trade.update({
                    'exit_time': df.index[i],
                    'exit_price': exit_exec,
                    'profit_usd': net_pnl,                # NET
                    'gross_pnl_usd': gross_pnl,
                    'commission_exit_usd': commission_exit,
                    'commission_total_usd': active_trade.get('commission_entry_usd', 0.0) + commission_exit,
                    'reason_exit': 'reverse'
                })
                _augment_trade_fields(
                    side=current_position,
                    exit_i=i,
                    spr_pts_exit=spr_pts,
                    close_bid_exit=close_bid,
                    commission_exit=commission_exit,
                    net_pnl_exec_based=net_pnl
                )
                active_trade.update({
                    'side': current_position,
                    'exit_ts_epoch_ms': _to_epoch_ms(df.index[i]),
                    'entry_ts_epoch_ms': _to_epoch_ms(active_trade['entry_time'])
                })
                completed_trades.append(active_trade)

                if self.config.get('plot_individual_trades'):
                    trade_df_slice = df.loc[active_trade['entry_time']:active_trade['exit_time']]
                    chart_folder = os.path.join(run_directory, "Individual_Charts")
                    self._plot_completed_trade(trade_df_slice, active_trade, len(completed_trades), chart_folder)

                current_position = None; active_trade = None

            # Entry Logic
            if current_position is None and is_in_trading_session and signal_is_valid:
                if is_bullish_cross:
                    current_position = 'BUY'
                elif is_bearish_cross:
                    current_position = 'SELL'
                
                if current_position:
                    spr_pts = _spread_pts(i)
                    close_bid = float(candle_sekarang['close'])
                    entry_exec = _exec_price(current_position, close_bid, spr_pts, leg='entry', is_market=True)
                    commission_entry = _commission_leg_usd(lot_size)

                    trade_seq += 1
                    features_at_entry = {}
                    # Snapshot fitur yang tersedia pada saat ENTRY (no look-ahead):
                    # BB bands
                    features_at_entry['bb_len'] = bb_length
                    features_at_entry['bb_m'] = float(candle_sekarang[middle_band_col])
                    for nm in (f'BBU_{bb_length}_2.0', f'BBL_{bb_length}_2.0'):
                        if nm in df.columns:
                            features_at_entry[nm] = float(candle_sekarang[nm])
                    # ADX (jika ada)
                    if use_adx_filter and adx_col in df.columns:
                        features_at_entry['adx'] = float(candle_sekarang[adx_col])
                    # Spread points & harga close_bid saat entry
                    features_at_entry['spread_points'] = float(spr_pts)
                    features_at_entry['close_bid'] = float(close_bid)

                    active_trade = {
                        'trade_id': int(trade_seq),
                        'type': current_position,
                        'entry_time': df.index[i],
                        'entry_index': i,
                        'entry_price': entry_exec,          # harga EKSEKUSI
                        'entry_price_ref_close_bid': close_bid,  # referensi (optional)
                        'entry_spread_points': spr_pts,
                        'entry_slippage_points': slippage_pts,
                        'commission_entry_usd': commission_entry,
                        'features_at_entry': features_at_entry,
                        'mfe_usd': 0.0,
                        'mae_usd': 0.0
                    }
                    eq_ds.add(_to_epoch_ms(df.index[i]), float(realized_balance), is_event=True)

        if not margin_called and current_position is not None and active_trade is not None:
            last_i = len(df) - 1
            spr_pts = _spread_pts(last_i)
            close_bid = float(df.iloc[last_i]['close'])
            exit_exec = _exec_price(current_position, close_bid, spr_pts, leg='exit', is_market=True)
            commission_exit = _commission_leg_usd(lot_size)

            gross_pnl = _pnl_usd(current_position, active_trade['entry_price'], exit_exec, lot_size)
            net_pnl = gross_pnl - (active_trade.get('commission_entry_usd', 0.0) + commission_exit)

            current_balance += net_pnl
            realized_balance += net_pnl
            current_balance = realized_balance
            eq_ds.add(_to_epoch_ms(df.index[last_i]), float(current_balance), is_event=True)
            equity_curve.append((df.index[last_i], current_balance))

            active_trade.update({
                'exit_time': df.index[last_i],
                'exit_price': exit_exec,
                'profit_usd': net_pnl,                # NET
                'gross_pnl_usd': gross_pnl,
                'commission_exit_usd': commission_exit,
                'commission_total_usd': active_trade.get('commission_entry_usd', 0.0) + commission_exit,
                'reason_exit': 'forced_close'
            })
            _augment_trade_fields(
                side=current_position,
                exit_i=last_i,
                spr_pts_exit=spr_pts,
                close_bid_exit=close_bid,
                commission_exit=commission_exit,
                net_pnl_exec_based=net_pnl
            )
            active_trade.update({
                'side': current_position,
                'exit_ts_epoch_ms': _to_epoch_ms(df.index[last_i]),
                'entry_ts_epoch_ms': _to_epoch_ms(active_trade['entry_time'])
            })
            completed_trades.append(active_trade)

            current_position = None
            active_trade = None

        equity_curve_ds = eq_ds.finalize()  # list[(t_ms:int, equity:float)]
        equity_curve_json = [(t, round(float(e), 2)) for (t, e) in equity_curve_ds]

        # Hitung max DD % dari curve downsampled
        peak = equity_curve_ds[0][1] if equity_curve_ds else initial_balance
        max_dd_val, peak_after, trough_after = 0.0, peak, peak
        peak_ts, trough_ts = (pd.to_datetime(equity_curve_ds[0][0], unit='ms', utc=True),)*2 if equity_curve_ds else (start_time, start_time)
        for t_ms, eq in equity_curve_ds:
            if eq > peak:
                peak = eq
                peak_ts = pd.to_datetime(t_ms, unit='ms', utc=True)
            dd = peak - eq
            if dd > max_dd_val:
                max_dd_val = dd
                trough_after = eq
                trough_ts = pd.to_datetime(t_ms, unit='ms', utc=True)
        max_drawdown_percentage = (max_dd_val / peak) * 100 if peak > 0 else 0

        tuw = 0.0
        prev_below_peak = False
        prev_ts = None
        cur_peak = equity_curve_ds[0][1] if equity_curve_ds else initial_balance
        for t_ms, eq in equity_curve_ds:
            ts = pd.to_datetime(t_ms, unit='ms', utc=True)
            if eq >= cur_peak:
                if prev_below_peak and prev_ts is not None:
                    tuw += (ts - prev_ts).total_seconds()
                prev_below_peak = False
                cur_peak = eq
                prev_ts = ts
            else:
                if not prev_below_peak:
                    prev_ts = ts
                prev_below_peak = True
        time_under_water_days = round(tuw / 86400.0, 2)

        # Perbarui peak/trough balance setelah loop
        for date, balance in equity_curve:
            if balance > peak_balance: peak_balance, peak_balance_date = balance, date
            if balance < trough_balance: trough_balance, trough_balance_date = balance, date

        gross_profit = sum(t['profit_usd'] for t in completed_trades if t['profit_usd'] > 0)
        gross_loss = sum(t['profit_usd'] for t in completed_trades if t['profit_usd'] < 0)

        final_balance = current_balance if not margin_called else 0
        total_profit = final_balance - initial_balance

        monthly_wins = [t for t in completed_trades if t['profit_usd'] > 0]
        monthly_losses = [t for t in completed_trades if t['profit_usd'] < 0]

        max_single_win = max(t['profit_usd'] for t in monthly_wins) if monthly_wins else 0
        max_single_loss = min(t['profit_usd'] for t in monthly_losses) if monthly_losses else 0

        avg_win = sum(t['profit_usd'] for t in monthly_wins) / len(monthly_wins) if monthly_wins else 0
        avg_loss = sum(t['profit_usd'] for t in monthly_losses) / len(monthly_losses) if monthly_losses else 0

        max_consecutive_losses = 0
        current_consecutive_losses = 0
        for t in completed_trades:
            if t['profit_usd'] <= 0:
                current_consecutive_losses += 1
            else:
                max_consecutive_losses = max(max_consecutive_losses, current_consecutive_losses)
                current_consecutive_losses = 0
        max_consecutive_losses = max(max_consecutive_losses, current_consecutive_losses)

        report_details = {
            "symbol": self.symbol,
            "period": f"Laporan untuk: {self.symbol} ({start_date_str} s/d {end_date_str})",
            "trading_session_info": f"Jam Trading: {self.start_trade_time.strftime('%H:%M')} - {self.end_trade_time.strftime('%H:%M')}",
            "time_str": time_str_for_filename, "period_for_filename": f"{start_date_str}_to_{end_date_str}",
            "server_tz": server_tz_name,
            "session_base_tz": session_base,
            "session_hours": f"{self.start_trade_time.strftime('%H:%M')}-{self.end_trade_time.strftime('%H:%M')}",
            "param_str": param_str, "run_directory": run_directory,
            "adx_filter_info": f"Filter ADX Aktif: P={adx_period}, T={adx_threshold}" if use_adx_filter else None,
            "sl_info": f"Stop Loss Aktif: {stop_loss_points} points" if use_stop_loss else None,
            "initial_balance": initial_balance, "final_balance": final_balance,
            "peak_balance": peak_balance, "peak_date": peak_balance_date.strftime('%Y-%m-%d %H:%M'),
            "trough_balance": trough_balance, "trough_date": trough_balance_date.strftime('%Y-%m-%d %H:%M'),
            "total_profit": total_profit,
            "roi": (total_profit / initial_balance * 100) if initial_balance > 0 else 0,
            "total_trades": len(completed_trades),
            "win_rate": (len([t for t in completed_trades if t['profit_usd'] > 0]) / len(completed_trades)) * 100 if completed_trades else 0,
            "max_consecutive_losses": max_consecutive_losses,
            "max_single_win": max_single_win,
            "max_single_loss": max_single_loss,
            "average_win": avg_win,
            "average_loss": abs(avg_loss)
        }
        report_details['monthly_drawdown_details'] = {
            "percentage": max_drawdown_percentage,
            "value": -max_dd_val,
            "peak_equity": float(peak),
            "trough_equity": float(trough_after),
            "start_date": peak_ts.strftime('%Y-%m-%d'),
            "end_date": trough_ts.strftime('%Y-%m-%d'),
            # opsional
            "time_under_water_days": time_under_water_days if 'time_under_water_days' in locals() else None,
        }
        report_details["market_features"] = self._compute_market_features(
            df, self.start_trade_time, self.end_trade_time
        )
        report_details['equity_curve'] = equity_curve

        report_details['completed_trades'] = completed_trades

        eq_df = pd.DataFrame(equity_curve_ds, columns=['ts_epoch_ms', 'equity'])
        run_directory = report_details['run_directory']
        os.makedirs(run_directory, exist_ok=True)
        eq_base = os.path.join(run_directory, f"equity_compact_{report_details['period_for_filename']}")
        saved_files = []
        try:
            if self.eq_write_parquet:
                _df = eq_df.copy()
                _df['equity'] = _df['equity'].astype('float32')
                _df.to_parquet(eq_base + '.parquet', index=False)
                saved_files.append(eq_base + '.parquet')
        except Exception:
            self.eq_write_csv = True
        if self.eq_write_csv:
            _df = eq_df.copy()
            _df['equity'] = _df['equity'].astype('float32')
            _df.to_csv(eq_base + '.csv', index=False)
            saved_files.append(eq_base + '.csv')

        report_details['equity_curve'] = equity_curve_json
        report_details['equity_curve_files'] = saved_files
        report_details["symbol_point"] = float(point)
        report_details["contract_size"] = float(contract_size)
        try:
            self._plot_equity_curve(report_details['equity_curve'], report_details)
        except Exception as e:
            print(f"Gagal membuat gambar equity bulanan: {e}", file=sys.stderr)
        return report_details
    
    def _get_full_equity_curve(self, monthly_reports: list) -> list:
        """Menggabungkan semua equity curve dari laporan bulanan menjadi satu."""
        if not monthly_reports:
            return []
        
        full_curve = []
        # Ambil data lengkap dari bulan pertama
        full_curve.extend(monthly_reports[0]['equity_curve'])
        # Untuk bulan-bulan berikutnya, lewati titik awal (karena sama dengan titik akhir bulan sebelumnya)
        for report in monthly_reports[1:]:
            full_curve.extend(report['equity_curve'][1:])
        return full_curve
    
    def _resample_equity_to_session_grid(self, full_equity_curve: list, minutes: int = 5) -> list:
        """
        full_equity_curve: list[(epoch_ms:int, balance:float)]
        return: list[(epoch_ms:int, balance:float)] di-grid per `minutes`
                hanya pada jam trading (config start/end).
        """
        if not full_equity_curve:
            return []

        # Ambil jam sesi + TZ dari config
        server_tz_name = str(self.config.get('server_tz', 'UTC'))
        session_base   = str(self.config.get('session_base_tz', 'UTC')).upper()
        local_tz = ZoneInfo(server_tz_name) if session_base == 'SERVER' else timezone.utc

        start_t = self.start_trade_time
        end_t   = self.end_trade_time

        # Series ekuitas di UTC
        ts_utc = pd.to_datetime([int(t) for t, _ in full_equity_curve], unit='ms', utc=True)
        vals   = [float(b) for _, b in full_equity_curve]
        s_utc  = pd.Series(vals, index=ts_utc)

        # Kumpulan tanggal (di TZ sesi)
        idx_local   = s_utc.index.tz_convert(local_tz)
        unique_days = sorted({d.date() for d in idx_local})

        grids = []
        for d in unique_days:
            start_local = pd.Timestamp.combine(d, start_t).tz_localize(local_tz)
            end_local   = pd.Timestamp.combine(d, end_t).tz_localize(local_tz)
            if end_local < start_local:  # sesi nyebrang midnight
                end_local += pd.Timedelta(days=1)

            # FIX 1: 'T' -> 'min'
            grid_local = pd.date_range(start_local, end_local, freq=f"{int(minutes)}min")
            grids.append(grid_local.tz_convert('UTC'))

        if not grids:
            return []

        # FIX 2: ganti union_many -> union berantai (compatible di semua pandas)
        grid_utc = grids[0]
        for gi in grids[1:]:
            grid_utc = grid_utc.union(gi)

        # Forward-fill tanpa look-ahead, drop sebelum titik pertama
        out = s_utc.reindex(grid_utc).ffill().dropna()

        # Kembalikan epoch-ms + balance
        return [(int(ts.timestamp()*1000), round(float(v), 2)) for ts, v in out.items()]
    
    def _compute_market_features(self, df: pd.DataFrame, start_time: time, end_time: time) -> dict:
        # Pastikan ada kolom close
        if df.empty:
            return {}

        # ATR & ADX (hitungan cepat)
        df_calc = df.copy()
        if not {'ATRr_14','ATR_14'}.intersection(df_calc.columns):
            df_calc.ta.atr(length=14, append=True)
        if not any(c.startswith('ADX_') for c in df_calc.columns):
            df_calc.ta.adx(length=14, append=True)

        atr_col = next((c for c in ['ATRr_14','ATR_14'] if c in df_calc.columns), None)
        adx_col = next((c for c in df_calc.columns if c.startswith('ADX_') and not c.endswith('D')), None)

        # Log returns untuk volatilitas lain
        ret = np.log(df_calc['close']).diff().dropna()

        # Filter jam sesi trading
        in_session = (df_calc.index.time >= start_time) & (df_calc.index.time <= end_time)
        session_ratio = float(np.mean(in_session)) if len(df_calc) else 0.0

        price_change = (df_calc['close'].iloc[-1] - df_calc['close'].iloc[0]) / df_calc['close'].iloc[0] * 100.0

        return {
            "market_price_change_pct": float(price_change),
            "atr_mean": float(df_calc[atr_col].mean()) if atr_col else None,
            "atr_std": float(df_calc[atr_col].std()) if atr_col else None,
            "adx_mean": float(df_calc[adx_col].mean()) if adx_col else None,
            "ret_std_log": float(ret.std()) if len(ret) else None,
            "ret_skew": float(ret.skew()) if len(ret) else None,
            "ret_kurt": float(ret.kurt()) if len(ret) else None,
            "session_coverage_ratio": session_ratio
        }
    
    def run_advanced_simulation(self, equity_curve: list, initial_balance: float, all_completed_trades: list, sl_percent: float, tp_percent: float, reset_rule: dict = None):
        """
        Versi 3.0: Menjalankan simulasi canggih dengan sistem state (TRADING/STOPPED) dan aturan reset dinamis.
        """
        if not equity_curve:
            return {'status': 'Data Kosong', 'net_profit': 0, 'trades': 0, 'max_drawdown': 0, 'win_rate': 0, 'profit_factor': 0, 'end_date': 'N/A', 'reset_count': 0, 'gross_profit': 0, 'gross_loss': 0, 'num_wins': 0}

        timestamps = [item[0] for item in equity_curve]
        balances = [item[1] for item in equity_curve]
        equity_series = pd.Series(balances, index=pd.to_datetime(timestamps ,unit='ms', utc=True))
        
        sim_balance = initial_balance
        sim_peak_balance = initial_balance
        sim_max_drawdown = 0.0
        phase_start_balance = initial_balance
        last_known_balance = initial_balance

        current_state = "TRADING"
        restart_date = None
        reset_count = 0
        
        status = "Completed"
        final_stop_date = equity_series.index[-1]

        for date, actual_balance in equity_series.items():
            if current_state == "STOPPED":
                if date.date() >= restart_date:
                    current_state = "TRADING"
                    phase_start_balance = sim_balance
                    restart_date = None
                    reset_count += 1
                else:
                    last_known_balance = actual_balance
                    continue 

            if current_state == "TRADING":
                daily_pnl = actual_balance - last_known_balance
                sim_balance += daily_pnl
                
                sim_peak_balance = max(sim_peak_balance, sim_balance)
                drawdown = (sim_peak_balance - sim_balance) / sim_peak_balance if sim_peak_balance > 0 else 0
                sim_max_drawdown = max(sim_max_drawdown, drawdown)

                tp_level = phase_start_balance * (1 + tp_percent / 100)
                sl_level = phase_start_balance * (1 - sl_percent / 100)
                
                if sim_balance >= tp_level:
                    status = f"TP {tp_percent:.1f}% Hit"
                    final_stop_date = date
                    break

                if sim_balance <= sl_level:
                    final_stop_date = date
                    if reset_rule and reset_rule.get('value', 0) > 0:
                        current_state = "STOPPED"
                        period_map = {'days': pd.Timedelta(days=1), 'weeks': pd.Timedelta(weeks=1), 'months': pd.Timedelta(days=30)}
                        delta = period_map.get(reset_rule['period'], pd.Timedelta(days=1)) * reset_rule['value']
                        restart_date = (date + delta).date()
                        status = "SL Hit, Resetting"
                    else:
                        status = f"SL {sl_percent:.1f}% Hit & Stop"
                        break

            last_known_balance = actual_balance

        trades_in_sim = [t for t in all_completed_trades if t['exit_time'].date() <= final_stop_date.date()]
        trade_count = len(trades_in_sim)
        wins = [t for t in trades_in_sim if t['profit_usd'] > 0]
        num_wins = len(wins) # <-- DATA BARU
        win_rate = (num_wins / trade_count) * 100 if trade_count > 0 else 0
        
        gross_profit = sum(t['profit_usd'] for t in wins) # <-- DATA BARU
        gross_loss = sum(t['profit_usd'] for t in trades_in_sim if t['profit_usd'] < 0) # <-- DATA BARU
        profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else 999.9

        return {
            'status': status,
            'net_profit': sim_balance - initial_balance,
            'trades': trade_count,
            'max_drawdown': sim_max_drawdown * 100,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'end_date': final_stop_date.strftime('%Y-%m-%d'),
            'reset_count': reset_count,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'num_wins': num_wins
        }
    
    def _format_simulation_table(self, simulation_results: list) -> str:
        header = (
            f"| {'Skenario':<30} | {'Net Profit ($)':>15} | {'WinRate(%)':>11} | {'P. Factor':>9} | "
            f"{'MaxDD(%)':>10} | {'Trades':>7} | {'Resets':>8} |\n"
        )
        separator = "-" * len(header)
        
        table_string = "--- Ringkasan Tahunan Simulasi Manajemen Risiko ---\n" # Judul diubah
        table_string += separator + "\n"
        table_string += header
        table_string += separator + "\n"

        for result in simulation_results:
            name = result.get('name', 'N/A')
            profit_str = f"${result.get('net_profit', 0):>13,.2f}"
            win_rate_str = f"{result.get('win_rate', 0):>9.2f}%"
            pf_str = f"{result.get('profit_factor', 0):>9.2f}"
            dd_str = f"{result.get('max_drawdown', 0):>8.2f}%"
            trades_str = f"{result.get('trades', 0):>7}"
            reset_str = f"{result.get('reset_count', 0):>6}x"
            
            table_string += (
                f"| {name:<30} | {profit_str} | {win_rate_str} | {pf_str} | "
                f"{dd_str} | {trades_str} | {reset_str} |\n"
            )

        table_string += separator
        return table_string
    
    def _generate_adaptive_scenarios(self, equity_curve: list) -> list:
        """
        Menghasilkan berbagai skenario simulasi, termasuk aturan reset yang eksplisit.
        """
        scenarios = [
            # Skenario Tanpa Reset (Stop permanen jika kena SL)
            {'name': 'Sangat Konservatif (SL 35%)', 'sl': 35.0, 'tp': 70.0, 'reset_rule': None},
            {'name': 'Konservatif (SL 25%)', 'sl': 25.0, 'tp': 50.0, 'reset_rule': None},
            {'name': 'Seimbang (SL 15%)', 'sl': 15.0, 'tp': 30.0, 'reset_rule': None},
            {'name': 'Agresif (SL 10%)', 'sl': 10.0, 'tp': 20.0, 'reset_rule': None},
            
            # Skenario dengan Reset
            {'name': 'Agresif, Reset Harian', 'sl': 7.5, 'tp': 15.0, 'reset_rule': {'period': 'days', 'value': 1}},
            {'name': 'Agresif, Reset Mingguan', 'sl': 10.0, 'tp': 20.0, 'reset_rule': {'period': 'weeks', 'value': 1}},
            {'name': 'Seimbang, Reset 2-Mingguan', 'sl': 15.0, 'tp': 30.0, 'reset_rule': {'period': 'weeks', 'value': 2}},
            {'name': 'Seimbang, Reset Bulanan', 'sl': 20.0, 'tp': 40.0, 'reset_rule': {'period': 'months', 'value': 1}},
        ]
        
        # Catatan: Logika 'Adaptif' yang kompleks bisa ditambahkan kembali di sini jika diperlukan,
        # dengan output yang juga menyertakan 'reset_rule'. Untuk saat ini, kita gunakan fixed scenarios.

        return scenarios

    def _create_summary_content_image(self, monthly_reports: list, config: dict, output_filename: str):
        """Membuat gambar yang HANYA berisi teks rekapitulasi dan grafik batang P/L."""
        # PERUBAHAN: Figure lebih tinggi & rasio diubah agar chart lebih besar
        fig = plt.figure(figsize=(16, 22))
        gs = fig.add_gridspec(2, 1, height_ratios=[3, 7])
        fig.suptitle("Laporan Kinerja Strategi", fontsize=24, weight='bold')

        # --- Bagian Teks Rekapitulasi ---
        ax_text = fig.add_subplot(gs[0, 0])
        ax_text.axis('off')

        # ... (Logika untuk membuat report_string tidak ada yang berubah) ...
        total_profit = sum(r['total_profit'] for r in monthly_reports)
        total_trades = sum(r['total_trades'] for r in monthly_reports)
        total_wins = sum(r['win_rate']/100 * r['total_trades'] for r in monthly_reports)
        overall_win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0
        all_completed_trades = [trade for r in monthly_reports for trade in r['completed_trades']]
        gross_profit = sum(t['profit_usd'] for t in all_completed_trades if t['profit_usd'] > 0)
        gross_loss = sum(t['profit_usd'] for t in all_completed_trades if t['profit_usd'] < 0)
        profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else 999.9
        
        initial_balance = config.get('initial_balance', 1000.0)
        full_equity_curve = []
        full_equity_curve = self._get_full_equity_curve(monthly_reports)

        peak_equity_total = initial_balance
        max_drawdown_value_total = 0.0
        for _, balance in full_equity_curve:
            peak_equity_total = max(peak_equity_total, balance)
            max_drawdown_value_total = max(max_drawdown_value_total, peak_equity_total - balance)
        total_drawdown_percent = (max_drawdown_value_total / peak_equity_total) * 100 if peak_equity_total > 0 else 0

        param_str = monthly_reports[0]['param_str']
        year = monthly_reports[0]['period_for_filename'][:4]
        
        report_string = "--- Rekapitulasi Backtest Tahunan ---\n"
        report_string += f"Simbol: {config.get('symbol')} | Initial Balance: ${initial_balance:,.2f} | Lot Size: {config.get('fixed_lot_size')} | Periode: {year}\n"
        report_string += f"Jam Trading: {config.get('trade_start_time')} - {config.get('trade_end_time')} | Parameter: {param_str}\n"
        report_string += "----------------------------------------------------------------------------------\n"
        report_string += "PERFORMA KESELURUHAN\n"
        report_string += f"Total Profit/Loss: ${total_profit:,.2f} | Win Rate: {overall_win_rate:,.2f}% | Total Trades: {total_trades}\n"
        report_string += f"Max Drawdown: {total_drawdown_percent:,.2f}% | Profit Factor: {profit_factor:,.2f}\n"
        report_string += "----------------------------------------------------------------------------------\n"
        report_string += "DETAIL PERFORMA BULANAN\n"
        header = (
            f"{'Bulan':<8} | {'P/L ($)':>12} | {'WinRate(%)':>11} | {'MaxDD(%)':>10} | "
            f"{'Cons.Loss':>9} | {'AvgWin($)':>12} | {'AvgLoss($)':>12} | {'MaxWin($)':>12} | {'MaxLoss($)':>12}\n"
        )
        report_string += header
        report_string += "-"*len(header) + "\n"
        for r in monthly_reports:
            month_name = datetime.strptime(r['period_for_filename'].split('_to_')[0], '%Y-%m-%d').strftime('%b %Y')
            dd_percent = r.get('monthly_drawdown_details', {}).get('percentage', 0)
            
            cons_loss = r.get('max_consecutive_losses', 0)
            avg_win = r.get('average_win', 0)
            avg_loss = r.get('average_loss', 0)
            max_win = r.get('max_single_win', 0)
            max_loss = r.get('max_single_loss', 0)

            report_string += (
                f"{month_name:<8} | ${r['total_profit']:>10,.2f} | {r['win_rate']:>9.2f}% | {dd_percent:>8.2f}% | "
                f"{cons_loss:>9} | ${avg_win:>10,.2f} | ${avg_loss:>10,.2f} | ${max_win:>10,.2f} | ${max_loss:>10,.2f}\n"
            )

        ax_text.text(0.5, 0.98, report_string,
             fontname='Courier New', fontsize=16,
             va='top', ha='center', linespacing=1.4,
             transform=ax_text.transAxes,
             multialignment='center')

        initial_balance = config.get('initial_balance', 1000.0)
        full_equity_curve = self._get_full_equity_curve(monthly_reports)
        all_completed_trades = [trade for r in monthly_reports for trade in r['completed_trades']]

        # aggregated_sim_results = {}
        # # Kumpulkan data dari setiap bulan
        # for report in monthly_reports:
        #     if 'simulation_results' in report:
        #         for sim_result in report['simulation_results']:
        #             name = sim_result['name']
        #             if name not in aggregated_sim_results:
        #                 aggregated_sim_results[name] = {
        #                     'net_profit': 0, 'trades': 0, 'num_wins': 0,
        #                     'gross_profit': 0, 'gross_loss': 0, 'reset_count': 0,
        #                     'max_drawdowns': []
        #                 }
                    
        #             aggregated_sim_results[name]['net_profit'] += sim_result.get('net_profit', 0)
        #             aggregated_sim_results[name]['trades'] += sim_result.get('trades', 0)
        #             aggregated_sim_results[name]['num_wins'] += sim_result.get('num_wins', 0)
        #             aggregated_sim_results[name]['gross_profit'] += sim_result.get('gross_profit', 0)
        #             aggregated_sim_results[name]['gross_loss'] += sim_result.get('gross_loss', 0)
        #             aggregated_sim_results[name]['reset_count'] += sim_result.get('reset_count', 0)
        #             aggregated_sim_results[name]['max_drawdowns'].append(sim_result.get('max_drawdown', 0))

        # # Hitung metrik final dari data yang sudah diagregasi
        # final_simulation_summary = []
        # for name, data in aggregated_sim_results.items():
        #     total_trades = data['trades']
        #     win_rate = (data['num_wins'] / total_trades) * 100 if total_trades > 0 else 0
        #     profit_factor = abs(data['gross_profit'] / data['gross_loss']) if data['gross_loss'] != 0 else 999.9
        #     max_drawdown = max(data['max_drawdowns']) if data['max_drawdowns'] else 0
            
        #     final_simulation_summary.append({
        #         'name': name,
        #         'net_profit': data['net_profit'],
        #         'win_rate': win_rate,
        #         'profit_factor': profit_factor,
        #         'max_drawdown': max_drawdown,
        #         'trades': total_trades,
        #         'reset_count': data['reset_count']
        #     })
            
        # table_output_string = self._format_simulation_table(final_simulation_summary)
        
        # ax_text.text(0.5, 0.1, table_output_string, fontname='Courier New', fontsize=16, va='top', ha='center')

        # --- Bagian Grafik Batang Bawah ---
        ax_bar = fig.add_subplot(gs[1, 0])
        month_names = [datetime.strptime(r['period_for_filename'].split('_to_')[0], '%Y-%m-%d').strftime('%b') for r in monthly_reports]
        monthly_pnl = [r['total_profit'] for r in monthly_reports]
        colors = ['g' if p > 0 else 'r' for p in monthly_pnl]
        ax_bar.bar(month_names, monthly_pnl, color=colors)
        ax_bar.set_title("Profit/Loss Bulanan", fontsize=16)
        ax_bar.set_ylabel("Profit/Loss ($)")
        
        # ### PERUBAHAN 3: Logika Sumbu-Y Adaptif ###
        y_min_limit = -1 * initial_balance
        max_pnl_value = max(monthly_pnl) if any(p > 0 for p in monthly_pnl) else 0

        y_max_final = 0
        # Kondisi jika profitnya kecil atau tidak ada sama sekali
        if max_pnl_value <= (initial_balance / 2):
            y_max_final = initial_balance
            upward_step = 2000 # Gunakan step default yang fix
        else:
            # --- Logika pembulatan ke atas sesuai permintaan ---
            # Tentukan basis pembulatan (misal: ke 1.000, 10.000, atau 100.000 terdekat)
            if max_pnl_value <= 10000:
                rounding_base = 1000
            elif max_pnl_value <= 100000:
                rounding_base = 10000
            else:
                rounding_base = 20000

            # Bulatkan max_pnl_value KE ATAS ke kelipatan rounding_base terdekat
            # Contoh: 24rb dibulatkan ke 30rb (jika base 10rb), 51rb ke 60rb
            y_max_final = math.ceil(max_pnl_value / rounding_base) * rounding_base
            
            # --- Langkah (step) adalah 1/10 dari batas atas ---
            upward_step = y_max_final / 10

        # Atur batas atas agar ada sedikit ruang (misal 5% buffer)
        final_y_limit = y_max_final * 1.05
        ax_bar.set_ylim(y_min_limit, final_y_limit)
        downward_ticks = np.arange(0, y_min_limit - 1, -2000)
        upward_ticks = np.arange(0, y_max_final + 1, upward_step)
        all_ticks = np.concatenate([downward_ticks, upward_ticks])
        all_ticks = all_ticks[(all_ticks >= y_min_limit) & (all_ticks <= final_y_limit)]
        ax_bar.set_yticks(sorted(all_ticks))
            
        ax_bar.grid(True, linestyle='--', alpha=0.7)
        ax_bar.axhline(0, color='black', linewidth=0.8)

        plt.subplots_adjust(top=0.95, hspace=0.6)
        plt.savefig(output_filename)
        plt.close(fig)

    def _create_mini_equity_pages_images(self, monthly_reports: list, output_dir: str) -> list:
        """Membuat satu atau lebih gambar, di mana setiap gambar berisi 8 grafik ekuitas kecil."""
        image_paths = []
        # PERUBAHAN: 8 grafik per halaman
        charts_per_page = 8
        num_pages = math.ceil(len(monthly_reports) / charts_per_page)

        for page_num in range(num_pages):
            start_index = page_num * charts_per_page
            end_index = start_index + charts_per_page
            report_chunk = monthly_reports[start_index:end_index]

            # PERUBAHAN: Grid 4x2 dan ukuran figure lebih tinggi
            fig, axes = plt.subplots(4, 2, figsize=(16, 18))
            axes = axes.flatten()
            fig.suptitle(f"Ringkasan Ekuitas Bulanan (Halaman {page_num + 1} dari {num_pages})", fontsize=20, weight='bold')

            for i, report in enumerate(report_chunk):
                ax_mini = axes[i]
                # ... (Logika plotting per grafik tidak ada yang berubah) ...
                equity_data = report['equity_curve']
                timestamps_ms = [int(item[0]) for item in equity_data]
                balances      = [float(item[1]) for item in equity_data]
                ts_dt = pd.to_datetime(timestamps_ms, unit='ms', utc=True)
                ax_mini.plot(ts_dt, balances, linewidth=1.5,
                            color=('g' if report['total_profit'] > 0 else 'r'))
                month_name = datetime.strptime(report['period_for_filename'].split('_to_')[0], '%Y-%m-%d').strftime('%B %Y')
                ax_mini.set_title(f"Ekuitas {month_name}", fontsize=12)
                ax_mini.grid(True, linestyle='--', alpha=0.5)
                ax_mini.tick_params(axis='x', rotation=30)
                ax_mini.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))

            # Sembunyikan subplot yang tidak terpakai
            for i in range(len(report_chunk), len(axes)):
                axes[i].set_visible(False)
            
            # PERUBAHAN: Menambah jarak vertikal antar grafik
            plt.subplots_adjust(top=0.95, hspace=0.5)

            output_filename = os.path.join(output_dir, f"temp_mini_curves_page_{page_num + 1}.png")
            plt.savefig(output_filename, bbox_inches='tight')
            plt.close(fig)
            image_paths.append(output_filename)

        return image_paths

    def create_final_pdf_report(self, monthly_reports: list, config: dict):
    # delegasi penuh ke modul reporting, tapi tetap memanggil util gambar milik self
        return create_final_pdf_report_impl(
            monthly_reports, config,
            self._create_summary_content_image,
            self._create_mini_equity_pages_images
        )

# ==============================================================================
#  BAGIAN UTAMA YANG DIUBAH UNTUK MENERIMA PERINTAH
# ==============================================================================
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Menjalankan satu instance backtest Poseidon Wave.")
    parser.add_argument('--symbol', type=str, default='XAUUSD', help='Simbol trading')
    parser.add_argument('--wave_period', type=int, default=36, help='Periode Bollinger Bands')
    parser.add_argument('--lot_size', type=float, default=0.2, help='Ukuran lot trading')
    parser.add_argument('--start_time', type=str, default='14:30', help='Jam mulai trading (HH:MM)')
    parser.add_argument('--end_time', type=str, default='19:30', help='Jam selesai trading (HH:MM)')
    parser.add_argument('--use_adx', action='store_true', help='Gunakan filter ADX')
    parser.add_argument('--adx_period', type=int, default=14, help='Periode ADX')
    parser.add_argument('--adx_threshold', type=int, default=15, help='Threshold ADX')
    parser.add_argument('--use_sl', action='store_true', help='Gunakan Stop Loss')
    parser.add_argument('--sl_points', type=float, default=10.0, help='Poin Stop Loss')
    parser.add_argument('--commission_per_lot_roundturn', type=float, default=7.0, help='Komisi round-turn per 1.0 lot dalam USD (dibagi 2 per leg)')
    parser.add_argument('--slippage_points', type=float, default=2.0, help='Slippage (points) per leg, diterapkan merugikan')
    parser.add_argument('--use_dynamic_spread', action='store_true', help='Jika True, pakai kolom spread dari MT5 rates bila tersedia')
    parser.add_argument('--avg_spread_points', type=float, default=20.0, help='Fallback spread (points) jika data historis tidak sediakan spread')
    parser.add_argument('--equity_mode', type=str, choices=['per_month','rolling'], default='per_month', help='Perhitungan saldo: per_month (reset tiap bulan) atau rolling (nyambung)')
    parser.add_argument('--server_tz', type=str, default='UTC', help='Time zone server/broker, contoh: UTC, Europe/London, Etc/GMT-3')
    parser.add_argument('--session_base_tz', type=str, choices=['UTC','server'], default='UTC', help='Jam sesi dihitung di UTC atau mengikuti zona waktu server')
    parser.add_argument('--year', type=int, default=2025, help='Tahun backtest')
    parser.add_argument('--start_month', type=int, default=1, help='Bulan mulai')
    parser.add_argument('--end_month', type=int, default=7, help='Bulan selesai')
    parser.add_argument('--initial_balance', type=float, default=1000.0, help='Modal awal backtest')
    parser.add_argument('--plot_trades', action='store_true', help='Aktifkan untuk menyimpan gambar chart per transaksi')
    parser.add_argument('--equity_every_n_bars', type=int, default=5)
    parser.add_argument('--equity_window_size', type=int, default=20)
    parser.add_argument('--equity_max_points', type=int, default=20000)
    parser.add_argument('--equity_write_parquet', action='store_true')
    parser.add_argument('--equity_write_csv', action='store_true')
    
    args = parser.parse_args()

    send_status({"status": "Inisialisasi MT5...", "progress": 0, "total": 1})
    if not mt5.initialize():
        print("initialize() gagal, error code =", mt5.last_error(), file=sys.stderr)
        quit()
    send_status({"status": "Koneksi MT5 OK", "progress": 1, "total": 1})

    # PERUBAHAN: Masukkan semua argumen relevan ke config
    config = {
        'symbol': args.symbol,
        'year': args.year,
        'initial_balance': args.initial_balance,
        'timeframe_str': 'm5',
        'timeframe_int': mt5.TIMEFRAME_M5,
        'equity_mode': args.equity_mode,
        'server_tz': args.server_tz,
        'session_base_tz': args.session_base_tz,
        'wave_period': args.wave_period,
        'fixed_lot_size': args.lot_size,
        'trade_start_time': args.start_time,
        'trade_end_time': args.end_time,
        'use_adx_filter': args.use_adx,
        'adx_period': args.adx_period,
        'adx_threshold': args.adx_threshold,
        'use_stop_loss': args.use_sl,
        'stop_loss_points': args.sl_points,
        'commission_per_lot_roundturn_usd': args.commission_per_lot_roundturn,
        'slippage_points': args.slippage_points,
        'use_dynamic_spread': args.use_dynamic_spread,
        'avg_spread_points': args.avg_spread_points,
        'equity_every_n_bars': args.equity_every_n_bars,
        'equity_window_size': args.equity_window_size,
        'equity_max_points': args.equity_max_points,
        'equity_write_parquet': args.equity_write_parquet,
        'equity_write_csv': args.equity_write_csv,
        'plot_individual_trades': args.plot_trades
    }

    strategy = PoseidonWave(mt5, config)

    monthly_reports = []
    total_months = (args.end_month - args.start_month) + 1
    rolling_balance = args.initial_balance
    
    for i, month in enumerate(range(args.start_month, args.end_month + 1)):
        num_days = calendar.monthrange(args.year, month)[1]
        start_date = f"{args.year}-{month:02d}-01"
        end_date = f"{args.year}-{month:02d}-{num_days}"
        month_name = calendar.month_name[month]
        send_status({"status": f"Backtest {month_name}...", "progress": i, "total": total_months})

        # pilih initial_balance per kebijakan equity_mode
        init_bal_for_month = rolling_balance if args.equity_mode == 'rolling' else args.initial_balance

        report = strategy.backtest(
            start_date_str=start_date,
            end_date_str=end_date,
            initial_balance=init_bal_for_month
        )

        if report:
            monthly_reports.append(report)
            if args.equity_mode == 'rolling':
                # pakai final_balance dari report (yang sudah handle margin call → 0)
                rolling_balance = float(report.get('final_balance', rolling_balance))
        
            # # Langkah 2: Jika backtest berhasil, langsung jalankan simulasi HANYA untuk data bulan ini
            # monthly_equity_curve = report.get('equity_curve', [])
            # monthly_trades = report.get('completed_trades', [])
            
            # if monthly_equity_curve:
            #     # Dapatkan daftar skenario yang akan diuji
            #     scenarios_to_run = strategy._generate_adaptive_scenarios(monthly_equity_curve)
                
            #     monthly_simulation_results = []
            #     for scenario in scenarios_to_run:
            #         # Jalankan simulasi dengan data bulan ini
            #         result = strategy.run_advanced_simulation(
            #             monthly_equity_curve, 
            #             args.initial_balance, 
            #             monthly_trades, 
            #             scenario['sl'], 
            #             scenario['tp'], 
            #             scenario.get('reset_rule')
            #         )
            #         result['name'] = scenario['name']
            #         monthly_simulation_results.append(result)
                
            #     # Langkah 3: Simpan hasil simulasi ke dalam laporan bulanan
            #     report['simulation_results'] = monthly_simulation_results
    
    send_status({"status": "Membuat Laporan PDF...", "progress": total_months, "total": total_months})
    
    if monthly_reports:
        total_profit = sum(r['total_profit'] for r in monthly_reports)
        total_trades = sum(r['total_trades'] for r in monthly_reports)
        all_completed_trades = [trade for r in monthly_reports for trade in r['completed_trades']]
        total_wins = len([t for t in all_completed_trades if t['profit_usd'] > 0])
        overall_win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0
        trading_dynamics = {}
        pdf_path = strategy.create_final_pdf_report(monthly_reports, config)
        if pdf_path:
            if all_completed_trades:
                # --- 1. Kalkulasi Gross Profit & Loss ---
                gross_profit = sum(t['profit_usd'] for t in all_completed_trades if t['profit_usd'] > 0)
                gross_loss = sum(t['profit_usd'] for t in all_completed_trades if t['profit_usd'] < 0)

                # --- 2. Hitung Profit Factor ---
                if gross_loss == 0:
                    trading_dynamics['profit_factor'] = 999.9
                else:
                    trading_dynamics['profit_factor'] = abs(gross_profit / gross_loss)

                # --- 3. Hitung Payoff Ratio ---
                total_losses = total_trades - total_wins
                if total_wins > 0 and total_losses > 0:
                    avg_win = gross_profit / total_wins
                    avg_loss = abs(gross_loss / total_losses)
                    trading_dynamics['payoff_ratio'] = avg_win / avg_loss
                else:
                    trading_dynamics['payoff_ratio'] = 0

                # --- 4. Hitung Max Consecutive Losses ---
                max_consecutive_losses = 0
                current_consecutive_losses = 0
                for t in all_completed_trades:
                    if t['profit_usd'] <= 0:
                        current_consecutive_losses += 1
                    else:
                        max_consecutive_losses = max(max_consecutive_losses, current_consecutive_losses)
                        current_consecutive_losses = 0
                trading_dynamics['max_consecutive_losses'] = max(max_consecutive_losses, current_consecutive_losses)

                # --- 5. Hitung Average Trade Duration ---
                total_duration_seconds = sum((t['exit_time'] - t['entry_time']).total_seconds() for t in all_completed_trades)
                trading_dynamics['average_trade_duration_minutes'] = (total_duration_seconds / 60) / total_trades

                # --- 6. Hitung Sharpe Ratio ---
                trade_returns = [t['profit_usd'] for t in all_completed_trades]
                std_dev_returns = np.std(trade_returns)
                if std_dev_returns > 0:
                    trading_dynamics['sharpe_ratio'] = np.mean(trade_returns) / std_dev_returns
                else:
                    trading_dynamics['sharpe_ratio'] = 0
            else:
                trading_dynamics = {
                    'profit_factor': 0, 'payoff_ratio': 0, 'max_consecutive_losses': 0,
                    'average_trade_duration_minutes': 0, 'sharpe_ratio': 0
                }
        
            initial_balance = monthly_reports[0]['initial_balance']
            full_equity_curve = strategy._get_full_equity_curve(monthly_reports)

            if full_equity_curve:
                # 1. Ubah list of tuples menjadi pandas Series dengan DatetimeIndex
                timestamps = [item[0] for item in full_equity_curve]
                balances   = [item[1] for item in full_equity_curve]
                idx = pd.to_datetime(timestamps, unit='ms', utc=True)
                equity_series = pd.Series(balances, index=idx)

                # 2. Resample ke data harian, ambil nilai terakhir setiap hari
                session_minutes = int(config.get('equity_session_sampling_minutes', 5))
                session_curve = strategy._resample_equity_to_session_grid(full_equity_curve, minutes=session_minutes)

                # Supaya variabel downstream tetap jalan (pakai pasangan (Timestamp, float))
                resampled_equity_curve = [
                    (pd.to_datetime(t_ms, unit='ms', utc=True), bal) for t_ms, bal in session_curve
                ]
            else:
                resampled_equity_curve = []

            # --- KALKULASI TOTAL DRAWDOWN BERDASARKAN DATA HARIAN YANG SUDAH DIRINGKAS ---
            peak_equity_total = initial_balance
            trough_after_peak_total = initial_balance
            # Gunakan tanggal dari data yang sudah di-resample jika ada
            peak_date_total = resampled_equity_curve[0][0] if resampled_equity_curve else datetime.now()
            trough_date_total = resampled_equity_curve[0][0] if resampled_equity_curve else datetime.now()
            max_drawdown_value_total = 0.0

            # Loop melalui data harian yang jauh lebih sedikit
            for date, balance in resampled_equity_curve:
                if balance > peak_equity_total:
                    peak_equity_total = balance
                    trough_after_peak_total = balance
                    peak_date_total = date
                
                drawdown = peak_equity_total - balance
                if drawdown > max_drawdown_value_total:
                    max_drawdown_value_total = drawdown
                    trough_after_peak_total = balance
                    trough_date_total = date

            max_drawdown_percentage_total = (max_drawdown_value_total / peak_equity_total) * 100 if peak_equity_total > 0 else 0

            total_drawdown_details = {
                "percentage": max_drawdown_percentage_total,
                "value": -max_drawdown_value_total,
                "peak_equity": peak_equity_total,
                "trough_equity": trough_after_peak_total,
                "start_date": peak_date_total.strftime('%Y-%m-%d'),
                "end_date": trough_date_total.strftime('%Y-%m-%d')
            }

            # --- Siapkan data kurva yang ringkas untuk disimpan ke JSON ---
            serializable_curve = session_curve

            trade_pnls = [t['profit_usd'] for t in all_completed_trades] if all_completed_trades else []
            if trade_pnls:
                pnl_series = pd.Series(trade_pnls)
                median_trade_pnl = float(pnl_series.median())
                pnl_std = float(pnl_series.std())
                pnl_p05 = float(pnl_series.quantile(0.05))
                pnl_p95 = float(pnl_series.quantile(0.95))
                # VaR & ES (95%)
                var_95 = float(pnl_series.quantile(0.05))
                es_95 = float(pnl_series[pnl_series <= var_95].mean()) if (pnl_series <= var_95).any() else var_95
            else:
                median_trade_pnl = pnl_std = pnl_p05 = pnl_p95 = var_95 = es_95 = None

            # --- Max consecutive wins ---
            max_consecutive_wins = 0
            _curr = 0
            for t in all_completed_trades:
                if t['profit_usd'] > 0:
                    _curr += 1
                    max_consecutive_wins = max(max_consecutive_wins, _curr)
                else:
                    _curr = 0

            # --- Stabilitas antar bulan ---
            monthly_profit = [r['total_profit'] for r in monthly_reports]
            monthly_winrate = [r['win_rate'] for r in monthly_reports]
            monthly_profit_std = float(np.std(monthly_profit)) if monthly_profit else 0.0
            monthly_winrate_std = float(np.std(monthly_winrate)) if monthly_winrate else 0.0

            # --- Time under water (hari dalam drawdown) ---
            def _time_under_water_days(curve):
                if not curve: return 0
                peak = curve[0][1]; tuw = 0
                for _, bal in curve:
                    if bal < peak: tuw += 1
                    else: peak = bal
                return int(tuw)

            time_under_water_days = _time_under_water_days(resampled_equity_curve)

            # --- CAGR, Calmar, Sortino ---
            def _annualized_cagr(curve, initial):
                if not curve or initial <= 0: return 0.0
                start_dt, end_dt = curve[0][0], curve[-1][0]
                years = max((end_dt - start_dt).days / 365.25, 1e-9)
                final = curve[-1][1]
                return (final / initial) ** (1/years) - 1 if final > 0 else -1.0

            cagr = _annualized_cagr(resampled_equity_curve, initial_balance)
            max_dd_pct = total_drawdown_details["percentage"] if "percentage" in total_drawdown_details else 0.0
            calmar = (cagr * 100) / max_dd_pct if max_dd_pct > 0 else None

            # Downside deviation (pakai trade returns negatif)
            neg_returns = [x for x in trade_pnls if x < 0]
            downside_std = float(np.std(neg_returns)) if neg_returns else 0.0
            sortino = (np.mean(trade_pnls) / downside_std) if downside_std > 0 and trade_pnls else None

            agg_market = {}
            if monthly_reports and 'market_features' in monthly_reports[0]:
                keys = monthly_reports[0]['market_features'].keys()
                for k in keys:
                    vals = [r['market_features'].get(k) for r in monthly_reports if r.get('market_features') and r['market_features'].get(k) is not None]
                    agg_market[k] = float(np.mean(vals)) if vals else None
            else:
                agg_market = {}

            ml_features = {
                "median_trade_pnl": median_trade_pnl,
                "pnl_std": pnl_std,
                "pnl_p05": pnl_p05,
                "pnl_p95": pnl_p95,
                "var_95": var_95,
                "es_95": es_95,
                "max_consecutive_wins": int(max_consecutive_wins),
                "monthly_profit_std": monthly_profit_std,
                "monthly_winrate_std": monthly_winrate_std,
                "time_under_water_days": time_under_water_days,
                "cagr_annualized_pct": float(cagr * 100.0),
                "calmar_ratio": calmar,
                "sortino_ratio": sortino,
                **{f"mkt_{k}": v for k, v in agg_market.items()},
            }

            labels = {
                "label_profitable": bool(total_profit > 0),
                "label_consistent": bool((overall_win_rate >= 55.0) and (max_dd_pct <= 30.0)),  # threshold bisa kamu sesuaikan
                "risk_class": (
                    "low" if max_dd_pct <= 20 else
                    "med" if max_dd_pct <= 40 else
                    "high"
                )
            }

            # Metadata
            import uuid
            metadata = {
                "run_id": str(uuid.uuid4()),
                "created_at": datetime.now().isoformat(timespec='seconds'),
                "backtest_version": "v1.0.0"
            }

            final_result_data = {
                'parameters': config,
                'total_profit': total_profit,
                'overall_win_rate': overall_win_rate,
                'total_trades': total_trades,
                'total_drawdown_details': total_drawdown_details, # <-- KEY BARU
                'pdf_report_path': pdf_path,
                'equity_curve_data': serializable_curve,
                'trading_dynamics': trading_dynamics,
                'ml_features': ml_features,
                'labels': labels,
                'metadata': metadata
            }
            params_alias = {
                'lot_size':       config.get('fixed_lot_size'),
                'start_time':     config.get('trade_start_time'),
                'end_time':       config.get('trade_end_time'),
                'use_adx':        config.get('use_adx_filter'),
                'use_sl':         config.get('use_stop_loss'),
                'sl_points':      config.get('stop_loss_points'),
                # yang sudah sama namanya:
                'wave_period':    config.get('wave_period'),
                'adx_threshold':  config.get('adx_threshold'),
            }
            final_result_data['parameters'] = {**config, **params_alias}

            final_result_data["ml_features"] = ml_features
            final_result_data["labels"] = labels
            final_result_data["metadata"] = metadata
            
            output_dir = os.path.dirname(pdf_path)
            result_json_path = os.path.join(output_dir, 'result.json')
            def _ts_ms(ts):
                import pandas as pd
                if isinstance(ts, pd.Timestamp):
                    return int(ts.tz_convert('UTC').timestamp() * 1000)
                return int(pd.to_datetime(ts, utc=True).timestamp() * 1000)

            trades_out = []
            for t in all_completed_trades:
                trades_out.append({
                    "trade_id": int(t.get("trade_id")),
                    "side": t.get("type"),  # BUY/SELL
                    "entry_ts": _ts_ms(t.get("entry_time")),
                    "exit_ts": _ts_ms(t.get("exit_time")),
                    "entry_price": float(t.get("entry_price")),
                    "exit_price": float(t.get("exit_price")),
                    "lot": float(t.get("lot", args.lot_size)),
                    "gross_pnl_usd": float(t.get("gross_pnl_usd")),         # murni gerak harga
                    "commission_usd": float(t.get("commission_usd", t.get("commission_total_usd", 0.0))),
                    "slippage_usd": float(t.get("slippage_usd", 0.0)),
                    "spread_cost_usd": float(t.get("spread_cost_usd", 0.0)),
                    "net_pnl_usd": float(t.get("net_pnl_usd", t.get("profit_usd", 0.0))),
                    "bars_held": int(t.get("bars_held", 0)),
                    "reason_exit": t.get("reason_exit", ""),
                    # Opsional ML
                    "mfe_usd": float(t.get("mfe_usd", 0.0)),
                    "mae_usd": float(t.get("mae_usd", 0.0)),
                    "spread_points_at_entry": float(t.get("entry_spread_points", 0.0)),
                    "features_at_entry": t.get("features_at_entry", {})
                })

            # Metadata biaya untuk transparansi downstream
            cost_metadata = {
                "commission_per_lot_roundturn_usd": float(args.commission_per_lot_roundturn),
                "slippage_points_per_leg": float(args.slippage_points),
                "spread_source": "dynamic" if args.use_dynamic_spread else "fallback_avg",
                "fallback_spread_points": float(args.avg_spread_points)
            }

            final_result_data["trades"] = trades_out
            final_result_data["net_pnl_total_usd"] = float(sum(x["net_pnl_usd"] for x in trades_out))
            final_result_data["cost_metadata"] = cost_metadata
            with open(result_json_path, 'w') as f:
                json.dump(final_result_data, f, indent=4)
            send_status({"status": "Menyimpan hasil JSON...", "progress": 1, "total": 1})
        else:
            print("PERINGATAN: Laporan PDF gagal dibuat, file result.json tidak akan disimpan.", file=sys.stderr)

    send_status({"status": "Selesai", "progress": 1, "total": 1})
    mt5.shutdown()