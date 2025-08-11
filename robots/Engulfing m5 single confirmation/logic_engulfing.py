import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import time
import math
from PyQt6.QtCore import QObject, pyqtSignal

class Worker(QObject):
    log_update = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._is_running = True
        self.active_m30_zone = None
        self.active_trade_info = {}
        self.initial_sl_for_pending_order = None

    def run(self):
        """Fungsi utama yang akan dijalankan di thread terpisah."""
        try:
            self.log_update.emit(f"✅ Bot Engine Dimulai. Magic Number: {self.config['magic_number']}")

            while self._is_running:
                open_positions = self._get_open_trades()
                
                if open_positions:
                    # --- JALUR 1: ADA TRADE YANG AKTIF ---
                    # Lakukan manajemen pada trade yang ditemukan.
                    self._manage_active_trade(open_positions[0])
                    
                    # Tentukan jeda waktu untuk pengecekan berikutnya.
                    wait_seconds = 20 
                    self.log_update.emit(f"   -> Pengecekan manajemen ulang dalam {wait_seconds} detik...")

                else:
                    # --- JALUR 2: TIDAK ADA TRADE YANG AKTIF ---
                    # Pertama, periksa apakah ada state trade lama yang perlu dibersihkan.
                    if self.active_trade_info:
                        self.log_update.emit("   Trade sebelumnya sudah tidak aktif. Mereset state...")
                        self.active_trade_info = {}
                        self.active_m30_zone = None

                    # Kedua, tunggu waktu yang tepat untuk mencari sinyal baru (di awal candle M5).
                    now = datetime.now()
                    wait_seconds = (5 - (now.minute % 5)) * 60 - now.second + 2
                    self.log_update.emit(f"[{now.strftime('%H:%M:%S')}] Tidak ada trade. Menunggu {wait_seconds:.0f} detik untuk candle M5 berikutnya...")
                    
                    # Lakukan jeda sesuai waktu di atas.
                    for _ in range(int(wait_seconds)):
                        if not self._is_running: break
                        time.sleep(1)
                    if not self._is_running: break

                    # Setelah menunggu, jalankan pencarian sinyal baru.
                    self.log_update.emit(f"--- WAKTU EKSEKUSI: {datetime.now().strftime('%H:%M:%S')} ---")
                    self._find_new_signal()
                    
                    # Setelah mencari sinyal, loop akan dimulai dari awal, jadi tidak perlu jeda tambahan.
                    continue # Lanjutkan ke iterasi loop berikutnya segera.

                # --- BAGIAN JEDA (SLEEP) UNIVERSAL ---
                # Jeda ini berlaku jika ada trade aktif (20 detik).
                # Loop akan langsung lanjut (continue) jika tidak ada trade, jadi ini tidak akan dijalankan di jalur itu.
                for _ in range(int(wait_seconds)):
                    if not self._is_running: break
                    time.sleep(1)

                if not self._is_running: break

        except Exception as e:
            self.log_update.emit(f"❌ Terjadi error fatal di thread bot: {e}")
        finally:
            self.log_update.emit("Thread bot telah berhenti.")
            self.finished.emit()

    def stop(self):
        self.log_update.emit("Menerima sinyal berhenti...")
        self._is_running = False

    # --- FUNGSI-FUNGSI PEMBANTU (HELPER METHODS) ---
    # DIUBAH: Semua fungsi menjadi method dengan 'self'
    
    def _get_rates(self, timeframe, count):
        rates = mt5.copy_rates_from_pos(self.config['symbol'], timeframe, 0, count)
        if rates is None or len(rates) == 0:
            self.log_update.emit(f"Tidak ada data untuk {self.config['symbol']} di {timeframe}.")
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def _is_engulfing(self, df, i, direction):
        if i < 1: return None
        current, previous = df.iloc[i], df.iloc[i-1]

        if direction == 'buy':
            # Syarat dasar: candle sebelumnya bearish (merah), candle sekarang bullish (hijau)
            if not (previous['open'] >= previous['close'] and current['open'] < current['close']):
                return None
            
            # DIUBAH: Cek kondisi AGGRESSIVE terlebih dahulu
            if current['close'] > previous['high']:
                return 'aggressive'
            # DIUBAH: Jika tidak aggressive, cek kondisi NORMAL
            elif current['close'] > previous['open']:
                return 'normal'

        elif direction == 'sell':
            # Syarat dasar: candle sebelumnya bullish (hijau), candle sekarang bearish (merah)
            if not (previous['open'] <= previous['close'] and current['open'] > current['close']):
                return None
            
            # DIUBAH: Cek kondisi AGGRESSIVE terlebih dahulu
            if current['close'] < previous['low']:
                return 'aggressive'
            # DIUBAH: Jika tidak aggressive, cek kondisi NORMAL
            elif current['close'] < previous['open']:
                return 'normal'
                
        return None

    def _get_open_trades(self):
        positions = mt5.positions_get(symbol=self.config['symbol'])
        if positions is None: return []
        return [p for p in positions if p.magic == self.config['magic_number']]

    def _get_pending_orders(self):
        orders = mt5.orders_get(magic=self.config['magic_number'])
        if orders is None: return []
        return [o for o in orders if o.state == mt5.ORDER_STATE_PLACED]

    def _calculate_lot_size(self, sl_level, entry_price):
        """Menghitung ukuran lot berdasarkan persentase risiko dari balance."""
        # DIUBAH: Mengambil nilai dari config
        risk_percent = self.config['risk_percent']
        symbol = self.config['symbol']

        account_info = mt5.account_info()
        if account_info is None:
            self.log_update.emit("❌ Gagal mendapatkan info akun.")
            return None
            
        balance = account_info.balance
        risk_amount = balance * (risk_percent / 100.0)
        sl_distance = abs(entry_price - sl_level)
        if sl_distance == 0:
            self.log_update.emit("⚠️ Jarak SL tidak boleh nol.")
            return None
            
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            self.log_update.emit(f"❌ Gagal mendapatkan info untuk simbol {symbol}")
            return None
            
        loss_per_lot = sl_distance * symbol_info.trade_contract_size
        if loss_per_lot == 0:
            self.log_update.emit("⚠️ Kerugian per lot adalah nol, tidak bisa menghitung lot size.")
            return None
            
        lot_size = risk_amount / loss_per_lot
        volume_step = symbol_info.volume_step
        lot_size = math.floor(lot_size / volume_step) * volume_step
        
        if lot_size < symbol_info.volume_min:
            self.log_update.emit(f"⚠️ Lot size terhitung ({lot_size}) lebih kecil dari minimum ({symbol_info.volume_min}). Trade dibatalkan.")
            return None
        if lot_size > symbol_info.volume_max:
            lot_size = symbol_info.volume_max
            
        return round(lot_size, 2)

    def _place_limit_order(self, direction, sl_level, limit_price):
        # DIUBAH: Menggunakan self.initial_sl_for_pending_order
        symbol = self.config['symbol']
        lot_size = self._calculate_lot_size(sl_level, limit_price)
        if lot_size is None or lot_size == 0:
            return False
            
        order_type = mt5.ORDER_TYPE_BUY_LIMIT if direction == 'buy' else mt5.ORDER_TYPE_SELL_LIMIT
        
        # Contoh jika ingin expiration time bisa diatur dari GUI
        # expiration_hours = self.config.get('order_expiration_hours', 8) 
        expiration_time = datetime.now() + timedelta(hours=8)

        self.log_update.emit(f"--- MENEMPATKAN {direction.upper()} LIMIT ORDER (STEALTH SL) ---")
        self.log_update.emit(f"   Limit Price: {limit_price:.5f}")
        self.log_update.emit(f"   (SL akan dimonitor pada level: {sl_level:.5f})")
        
        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": limit_price,
            "sl": 0.0,
            "tp": 0.0,
            "magic": self.config['magic_number'],
            "comment": "Bot Engulfing M5",
            "type_time": mt5.ORDER_TIME_SPECIFIED,
            "expiration": int(expiration_time.timestamp()),
            "type_filling": mt5.ORDER_FILLING_FOK
        }
        
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err_comment = result.comment if result else "Tidak ada respons."
            self.log_update.emit(f"❌ Gagal menempatkan order, retcode={result.retcode if result else 'N/A'} - {err_comment}")
            return False
            
        self.log_update.emit(f"✅ Order Limit berhasil ditempatkan, ticket #{result.order}")
        self.initial_sl_for_pending_order = sl_level # DIUBAH: Tanpa 'global'
        return True
    
    def _close_trade(self, position, comment):
        """Menutup posisi yang sedang terbuka."""
        self.log_update.emit(f"--- MENCOBA MENUTUP TRADE #{position.ticket} ({comment}) ---")
        close_type = mt5.ORDER_TYPE_SELL if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        symbol = self.config['symbol']
        price = mt5.symbol_info_tick(symbol).bid if close_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(symbol).ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": position.ticket,
            "symbol": symbol,
            "volume": position.volume,
            "type": close_type,
            "price": price,
            "magic": self.config['magic_number'],
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK
        }
        
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.log_update.emit(f"✅ Trade #{position.ticket} berhasil ditutup.")
            return True
        else:
            err_comment = result.comment if result else "Tidak ada respons."
            self.log_update.emit(f"❌ Gagal menutup trade, retcode={result.retcode if result else 'N/A'} - {err_comment}")
            return False

    def _cancel_order(self, ticket):
        """Membatalkan pending order."""
        self.log_update.emit(f"--- MENCOBA MEMBATALKAN ORDER #{ticket} ---")
        request = {"action": mt5.TRADE_ACTION_REMOVE, "order": ticket}
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.log_update.emit(f"✅ Order #{ticket} berhasil dibatalkan.")
            return True
        else:
            err_comment = result.comment if result else "Tidak ada respons."
            self.log_update.emit(f"❌ Gagal membatalkan order, retcode={result.retcode if result else 'N/A'} - {err_comment}")
            return False

    def _find_latest_m30_zone(self, df_m30):
        """Mencari zona engulfing M30 dari data yang diberikan."""
        # Loop dari candle terbaru (-2) ke belakang
        for i in range(len(df_m30) - 2, 0, -1):
            is_buy = self._is_engulfing(df_m30, i, 'buy')
            is_sell = self._is_engulfing(df_m30, i, 'sell')

            formatted_time = df_m30.iloc[i]['time'].strftime('%Y-%m-%d %H:%M')
            if is_buy:
                self.log_update.emit(f"   Ditemukan ZONA BUY M30 pada candle: {formatted_time}")
                current, prev = df_m30.iloc[i], df_m30.iloc[i-1]
                zone_low = min(current['low'], prev['low'])
                return {'type': 'm30_buy_zone', 'start_time': prev.name, 'high': max(current['high'], prev['high']), 'low': zone_low}
            
            if is_sell:
                self.log_update.emit(f"   Ditemukan ZONA SELL M30 pada candle: {formatted_time}")
                current, prev = df_m30.iloc[i], df_m30.iloc[i-1]
                zone_high = max(current['high'], prev['high'])
                return {'type': 'm30_sell_zone', 'start_time': prev.name, 'high': zone_high, 'low': min(current['low'], prev['low'])}
        return None
        
    def _find_new_signal(self):
        self.log_update.emit("--- Mencari sinyal trading baru ---")
        
        if self.active_trade_info:
            self.log_update.emit("   Trade sudah tidak aktif. Mereset state.")
            self.active_trade_info = {}
            self.active_m30_zone = None

        pending_orders = self._get_pending_orders()
        if pending_orders:
            self.log_update.emit(f"   Masih ada pending order #{pending_orders[0].ticket}. Pencarian ditunda.")
            return

        # 1. Cari Zona M30
        df_m30 = self._get_rates(mt5.TIMEFRAME_M30, 50)
        if df_m30.empty: return
        
        latest_market_zone = self._find_latest_m30_zone(df_m30)
        if not latest_market_zone: 
            self.log_update.emit("   Tidak ditemukan zona M30 yang valid saat ini.")
            self.active_m30_zone = None
            return
        
        if self.active_m30_zone is None or self.active_m30_zone['start_time'] != latest_market_zone['start_time']:
            self.log_update.emit(f"   Zona M30 baru teridentifikasi: {latest_market_zone['type']}")
            self.active_m30_zone = latest_market_zone
        
        # 2. Cek Harga di Dalam Zona
        df_m5 = self._get_rates(mt5.TIMEFRAME_M5, 50)
        if df_m5.empty: return
        latest_m5_candle_close = df_m5.iloc[-1]['close']
        
        is_price_in_zone = self.active_m30_zone['low'] <= latest_m5_candle_close <= self.active_m30_zone['high']
        if not is_price_in_zone:
            self.log_update.emit(f"   Harga ({latest_m5_candle_close:.5f}) di luar zona M30.")
            return

        # 3. Cari Sinyal Engulfing M5
        self.log_update.emit("   Harga di dalam zona M30. Mencari sinyal M5 dalam 3 candle terakhir...")
        direction = 'buy' if self.active_m30_zone['type'] == 'm30_buy_zone' else 'sell'

        engulfing_type = None
        engulfing_candle_index = -1

        # Loop untuk memeriksa 3 candle terakhir yang sudah ditutup (indeks -2, -3, -4)
        # Perulangan dimulai dari yang paling baru
        for i in range(len(df_m5) - 2, len(df_m5) - 5, -1):
            if i < 1:  # Pastikan tidak ada error index out of bounds
                break
            
            # Coba cari pola engulfing di candle saat ini
            temp_type = self._is_engulfing(df_m5, i, direction)
            
            if temp_type:
                engulfing_type = temp_type
                engulfing_candle_index = i
                # Menggunakan f-string untuk log yang lebih jelas
                candle_time = df_m5.iloc[i]['time'].strftime('%H:%M')
                self.log_update.emit(f"   --> Ditemukan sinyal M5 ({temp_type.upper()}) pada candle jam {candle_time}")
                break  # Jika sudah ketemu yang paling baru, hentikan pencarian

        if engulfing_type:
            direction = 'buy' if self.active_m30_zone['type'] == 'm30_buy_zone' else 'sell'

            self.log_update.emit(f"✅ SINYAL DIKONFIRMASI! Tipe: {engulfing_type.upper()}, Arah: {direction.upper()}")
            
            engulfing_candle = df_m5.iloc[engulfing_candle_index]
            engulfed_candle = df_m5.iloc[engulfing_candle_index - 1]
            
            point = mt5.symbol_info(self.config['symbol']).point
            sl_buffer_pips = self.config.get('sl_buffer_pips', 5.0)
            
            limit_price = 0.0

            if direction == 'buy':
                if engulfing_type == 'aggressive':
                    limit_price = engulfed_candle['high']
                    self.log_update.emit(f"   Entry Aggressive di High candle sebelumnya: {limit_price:.5f}")
                elif engulfing_type == 'normal':
                    limit_price = engulfed_candle['open']
                    self.log_update.emit(f"   Entry Normal di Open candle sebelumnya: {limit_price:.5f}")

                sl_level = min(engulfing_candle['low'], engulfed_candle['low']) - (sl_buffer_pips * 10 * point)
            
            else: # direction == 'sell'
                if engulfing_type == 'aggressive':
                    limit_price = engulfed_candle['low']
                    self.log_update.emit(f"   Entry Aggressive di Low candle sebelumnya: {limit_price:.5f}")
                elif engulfing_type == 'normal':
                    limit_price = engulfed_candle['open']
                    self.log_update.emit(f"   Entry Normal di Open candle sebelumnya: {limit_price:.5f}")

                sl_level = max(engulfing_candle['high'], engulfed_candle['high']) + (sl_buffer_pips * 10 * point)
                
            if limit_price > 0 and sl_level > 0:
                self._place_limit_order(direction, sl_level, limit_price)
                self.active_m30_zone = None

    def _initialize_trade_info(self, position):
        """Menginisialisasi dictionary active_trade_info saat trade ter-trigger."""
        self.log_update.emit(f"   Trade #{position.ticket} telah aktif. Menginisialisasi data manajemen...")

        # Pastikan kita memiliki SL awal yang tersimpan dari pending order
        if self.initial_sl_for_pending_order is None:
            self.log_update.emit("   ⚠️ Peringatan: Tidak ditemukan initial SL. Manajemen trade tidak dapat dimulai.")
            return

        entry_price = position.price_open
        initial_sl = self.initial_sl_for_pending_order
        direction = 'buy' if position.type == mt5.POSITION_TYPE_BUY else 'sell'
        risk_pips = abs(entry_price - initial_sl)

        self.active_trade_info = {
            'ticket': position.ticket,
            'entry_price': entry_price,
            'initial_sl': initial_sl,
            'current_sl': initial_sl,
            'direction': direction,
            'risk_pips': risk_pips,
            'be_activated': False,
            'trailing_activated': False
        }
        
        self.log_update.emit(f"   -> Info Trade: Entry={entry_price:.5f}, SL={initial_sl:.5f}, Risk={risk_pips:.5f} pts")
        
        # Penting: Reset SL awal agar tidak terpakai untuk trade berikutnya
        self.initial_sl_for_pending_order = None

    def _manage_active_trade(self, position):
        if not self.active_trade_info or self.active_trade_info.get('ticket') != position.ticket:
            self._initialize_trade_info(position)

        if not self.active_trade_info: return

        # --- Bagian Manajemen BE & Trailing ---
        info = self.active_trade_info
        direction = info['direction']
        symbol = self.config['symbol']
        rr_ratio = self.config['rr_ratio']
        live_price = mt5.symbol_info_tick(symbol).ask if direction == 'buy' else mt5.symbol_info_tick(symbol).bid
        
        self.log_update.emit(f"   [MANAJEMEN LIVE] SL: {info['current_sl']:.5f} | Entry: {info['entry_price']:.5f} | Live: {live_price:.5f}")

        # Logika Trailing (jika sudah aktif)
        if info.get('trailing_activated', False):
            new_sl = live_price - info['risk_pips'] if direction == 'buy' else live_price + info['risk_pips']
            if (direction == 'buy' and new_sl > info['current_sl']) or (direction == 'sell' and new_sl < info['current_sl']):
                self.log_update.emit(f"🚀 TRAILING STOP UPDATED! SL baru: {new_sl:.5f}")
                self.active_trade_info['current_sl'] = new_sl
        else: # Logika Aktivasi
            # Aktivasi Trailing di R:R target
            trailing_target = info['entry_price'] + (rr_ratio * info['risk_pips']) if direction == 'buy' else info['entry_price'] - (rr_ratio * info['risk_pips'])
            if (direction == 'buy' and live_price >= trailing_target) or (direction == 'sell' and live_price <= trailing_target):
                sl_at_rr2 = info['entry_price'] + (2 * info['risk_pips']) if direction == 'buy' else info['entry_price'] - (2 * info['risk_pips'])
                self.log_update.emit(f"🎉 R:R {rr_ratio} TERCAPAI! Trailing diaktifkan. SL dipindah ke +2R di {sl_at_rr2:.5f}")
                self.active_trade_info['current_sl'] = sl_at_rr2
                self.active_trade_info['trailing_activated'] = True
                self.active_trade_info['be_activated'] = True
            # Aktivasi BE di 2R
            elif not info.get('be_activated', False):
                be_target = info['entry_price'] + (2 * info['risk_pips']) if direction == 'buy' else info['entry_price'] - (2 * info['risk_pips'])
                if (direction == 'buy' and live_price >= be_target) or (direction == 'sell' and live_price <= be_target):
                    self.log_update.emit(f"✅ R:R 2 TERCAPAI! SL dipindah ke Break Even di {info['entry_price']:.5f}")
                    self.active_trade_info['current_sl'] = info['entry_price']
                    self.active_trade_info['be_activated'] = True

        # --- Bagian Cek Stealth SL ---
        df_m5 = self._get_rates(mt5.TIMEFRAME_M5, 5)
        if df_m5.empty or len(df_m5) < 2:
            return

        last_closed_candle = df_m5.iloc[-2]
        close_price = last_closed_candle['close']
        
        sl_hit = False
        if info['direction'] == 'buy' and close_price < info['current_sl']:
            sl_hit = True
        elif info['direction'] == 'sell' and close_price > info['current_sl']:
            sl_hit = True

        if sl_hit:
            self.log_update.emit(f"🔥 STEALTH SL HIT (berdasarkan Close Candle)! Menutup posisi...")
            if self._close_trade(position, "Stealth SL Hit (Close)"):
                self.active_trade_info = {}
                self.active_m30_zone = None