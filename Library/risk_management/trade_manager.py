# Library/risk_management/trade_manager.py

import MetaTrader5 as mt5
from datetime import datetime, timedelta, time
import pytz
import logging
import time as time_mod
from Library.reporting.report_generator import ReportGenerator
from PyQt6.QtCore import QObject, QThread, pyqtSignal

# --- Konfigurasi Logger ---
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

class TradeManager:
    """
    [VERSI FINAL LENGKAP] Mesin status untuk melacak dan merekonsiliasi setiap order secara aktif,
    mengelola risiko akun secara global, dan memicu laporan yang akurat.
    """
    def __init__(self, config, mt5_instance, broker_module, bot_worker_ref):

        """
        Inisialisasi Trade Manager.

        Args:
            config (dict): Dictionary konfigurasi dari UI (settings_window.py).
            mt5_instance: Instance MetaTrader5 yang aktif.
            broker_module: Modul kustom Anda (mt5_broker.py) untuk eksekusi.
        """
        self.config = config
        self.mt5 = mt5_instance
        self.broker = broker_module
        self.bot_worker_ref = bot_worker_ref
        self.report_generator = ReportGenerator(reports_dir='reports')

        # Jurnal utama yang melacak status setiap order
        self.tracked_orders = {}  # Format: {order_ticket: {'status': '...', 'details': {...}}}

        # Status Sesi Global
        self.session_start_time = datetime.now(pytz.utc)
        self.account_info = self._get_account_info()
        self.initial_balance = self.account_info.get('balance', 0)
        self.peak_equity_session = self.account_info.get('equity', 0)
        self.status_message = "Sesi dimulai. Monitoring normal."
        
        # Bendera (Flags) Kontrol Sesi
        self.session_ending = False
        self.report_generated = False
        self.is_cooldown = False
        self.cooldown_end_time = None
        
        login = self.account_info.get('login', 'N/A')
        logger.info(f"TradeManager (Stateful) untuk Akun {login} telah diinisialisasi.")
        self.is_closing_actively = False
        self.closer_thread = None
        self.closer_worker = None
        self.last_global_order_time = 0

    # --- 1. METODE PUBLIK (Untuk dipanggil oleh BotWorker) ---
    def can_place_new_trade(self, entry_price_to_check: float) -> tuple[bool, str]:
        """
        Memeriksa semua kondisi sebelum mengizinkan penempatan trade baru.
        Mengembalikan (Boleh/Tidak, Alasan).
        """
        # 1. Cek Batas Trade Berjalan
        max_trades = self.config.get('max_concurrent_trades', 1)
        active_trades = sum(1 for o in self.tracked_orders.values() if o.get('status') == 'ACTIVE')
        if active_trades >= max_trades:
            return (False, f"Batas {max_trades} trade berjalan tercapai.")

        # 2. Cek Jeda Waktu Antar Order
        cooldown = self.config.get('order_cooldown_seconds', 1.0)
        if time_mod.time() - self.last_global_order_time < cooldown:
            return (False, f"Jeda antar order ({cooldown} detik) aktif.")

        # 3. Cek Duplikasi Harga Entri pada Pending Order
        for order in self.tracked_orders.values():
            if order.get('status') == 'PENDING_LIVE':
                pending_entry_price = order.get('entry_price')
                # Gunakan toleransi sangat kecil untuk perbandingan float
                if pending_entry_price and abs(pending_entry_price - entry_price_to_check) < 0.000001:
                    return (False, f"Order dengan harga entri {entry_price_to_check} sudah ada.")
        
        return (True, "Diizinkan untuk menempatkan trade baru.")

    def register_new_pending_order(self, order_ticket, symbol, magic_number, entry_price, strategy_info: dict):
        """Dipanggil oleh BotWorker setiap kali berhasil menempatkan pending order."""
        if order_ticket not in self.tracked_orders:
            self.tracked_orders[order_ticket] = {
                'status': 'PENDING_LIVE',
                'symbol': symbol,
                'magic_number': magic_number,
                'order_ticket': order_ticket,
                'position_id': None,
                'entry_deal': None,
                'closing_deal': None,
                'time_registered': time_mod.time(),
                'entry_price': entry_price,
                'strategy_info': strategy_info # <-- TAMBAHKAN BARIS INI
            }
            self.last_global_order_time = time_mod.time()
            logger.info(f"Order baru #{order_ticket} ({symbol}) @ {entry_price} berhasil didaftarkan.")

    def reconcile_state(self):
        """
        [JANTUNG UTAMA] Loop rekonsiliasi yang dipanggil secara periodik (misal: setiap 15 detik).
        Mencocokkan jurnal internal dengan data live dari MT5 untuk memvalidasi status setiap trade.
        """
        if not self.tracked_orders:
            return

        try:
            live_orders = self.mt5.orders_get() or []
            live_positions = self.mt5.positions_get() or []
            history_deals = self.mt5.history_deals_get(self.session_start_time, datetime.now(pytz.utc)) or []

            live_order_tickets = {o.ticket for o in live_orders}
            live_position_ids = {p.ticket for p in live_positions}
            
            deals_by_position = {}
            for deal in history_deals:
                if deal.position_id not in deals_by_position: deals_by_position[deal.position_id] = []
                deals_by_position[deal.position_id].append(deal)

            for ticket, order_data in list(self.tracked_orders.items()):
                status = order_data['status']
                
                if status == 'PENDING_LIVE':
                    if ticket not in live_order_tickets:
                        found_position = next((p for p in live_positions if p.order == ticket), None)
                        if found_position:
                            order_data.update({'status': 'ACTIVE', 'position_id': found_position.ticket})
                            logger.info(f"Order #{ticket} tereksekusi menjadi posisi #{found_position.ticket}.")
                        else:
                            order_data['status'] = 'CANCELED'
                            logger.info(f"Order #{ticket} dibatalkan atau kedaluwarsa.")
                
                elif status == 'ACTIVE':
                    if order_data['position_id'] not in live_position_ids:
                        order_data['status'] = 'FINALIZE_PENDING'
                        logger.warning(f"Posisi #{order_data['position_id']} telah ditutup. Menunggu konfirmasi deal...")
                
                elif status == 'FINALIZE_PENDING':
                    deals = deals_by_position.get(order_data['position_id'], [])
                    for d in deals:
                        if d.entry == 1:
                            order_data.update({
                                'closing_deal': d._asdict(),
                                'entry_deal': self._find_entry_deal(deals),
                                'status': 'CLOSED_COMPLETE'
                            })
                            logger.info(f"Finalisasi berhasil untuk posisi #{order_data['position_id']}.")
                            break

        except Exception as e:
            logger.error(f"Error dalam rekonsiliasi: {e}", exc_info=True)

    def close_all_positions_and_orders(self, reason=""):
        """
        [VERSI BARU] Fungsi sinkron yang memblokir untuk menutup semua trade.
        Aman karena dipanggil dari dalam thread BotWorker.
        """
        logger.info(f"Proses penutupan dimulai. Alasan: {reason}")
        timeout_seconds = 60
        start_time = time_mod.time()

        while time_mod.time() - start_time < timeout_seconds:
            try:
                positions = self.mt5.positions_get() or []
                pending_orders = [o for o in (self.mt5.orders_get() or []) if o.state == mt5.ORDER_STATE_PLACED]

                if not positions and not pending_orders:
                    logger.info("Verifikasi berhasil: Semua posisi dan order ditutup.")
                    return # Langsung keluar jika sudah bersih

                for pos in positions:
                    self.mt5.Close(symbol=pos.symbol, ticket=pos.ticket)
                for order in pending_orders:
                    self.broker.cancel_order(order.ticket)
                
                time_mod.sleep(1) # Beri jeda 1 detik sebelum memeriksa kembali
            except Exception as e:
                logger.error(f"Error saat menutup posisi/order: {e}")
                time_mod.sleep(2)
        
        logger.error("TIMEOUT saat proses penutupan. Mungkin masih ada posisi/order tersisa.")

    def check_pnl_rules(self):
        """Fungsi yang dipanggil secara cepat untuk memantau P/L dan drawdown."""
        if self.session_ending or self.is_cooldown: return

        self.account_info = self._get_account_info()
        equity = self.account_info.get('equity', 0)
        self.peak_equity_session = max(self.peak_equity_session, equity)

        # Cek Batas Loss & Target Profit
        loss_target = self._loss_threshold()
        profit_target = self._profit_threshold()

        if equity <= loss_target:
            self.bot_worker_ref.enter_stopping_mode(f"Batas Drawdown Tercapai (di ${loss_target:,.2f})")
            return # Hentikan pengecekan lebih lanjut
        elif equity >= profit_target:
            self.bot_worker_ref.enter_stopping_mode(f"Target Profit Tercapai (di ${profit_target:,.2f})")
            return
        
        # Cek Stop Ekuitas Absolut
        stop_config = self.config.get('absolute_equity_stop', {})
        if stop_config.get('value', 0) > 0: # Hanya cek jika nilainya diatur
            stop_level = 0
            stop_type = stop_config.get('type', 'amount')
            if stop_type == 'amount':
                stop_level = stop_config.get('value', 0)
            else: # type == 'percent'
                stop_level = self.initial_balance * (stop_config.get('value', 0) / 100.0)

            if stop_level > 0 and equity <= stop_level:
                # --- [PERBAIKAN] Gunakan state machine ---
                self.bot_worker_ref.enter_stopping_mode(f"Stop Darurat Ekuitas ({stop_type}) Tercapai pada ${stop_level:,.2f}")
                return

        # Cek Kerugian Beruntun
        if self.config.get('use_consecutive_loss_stop', False):
            max_losses = self.config.get('max_consecutive_losses', 99)
            if max_losses > 0:
                consecutive_losses = self._calculate_consecutive_losses()
                if consecutive_losses >= max_losses:
                    # --- [PERBAIKAN] Gunakan state machine ---
                    self.bot_worker_ref.enter_stopping_mode("Kerugian Beruntun Maksimal Tercapai")
                    return
                
        # Cek Gradual Stop
        if self.config.get('use_gradual_stop', False):
            if equity <= self._gradual_stop_threshold():
                self.status_message = "PERINGATAN: Gradual stop aktif. Dilarang buka posisi baru."
            else:
                self.status_message = "Monitoring normal."
        else:
            self.status_message = "Monitoring normal."

    def check_session_completion_and_report(self):
        logger.info(">>> TradeManager: FUNGSI check_session_completion_and_report DIMULAI.")
        # if not self.session_ending or self.report_generated:
        #     return

        # [PERBAIKAN] Anggap sesi selesai setelah upaya penutupan, 
        # tidak peduli apakah semua posisi berhasil ditutup (misal karena masalah koneksi).
        # Ini memastikan bot selalu masuk mode cooldown.
        logger.info("Sesi telah berakhir. Membuat laporan akhir sesi.")
        final_report_data = self._build_final_report_data()
        self.report_generator.generate_session_report(final_report_data)
        self.report_generated = True
        
        # Aktifkan mode cooldown
        self.is_cooldown = True
        self.cooldown_end_time = self._calculate_cooldown_end_time()
        end_time_str = self.cooldown_end_time.strftime('%A, %d %B %Y jam %H:%M:%S')
        self.status_message = f"Laporan Dibuat. Cooldown hingga {end_time_str}"
        log_message = f"FLAG COOLDOWN DIAKTIFKAN. Mode cooldown akan berjalan hingga: {end_time_str}"
        logger.info(log_message)

    def get_status_for_ui(self):
        """Membangun dictionary status ringkas untuk ditampilkan di UI."""
        active_positions = 0
        pending_orders = 0
        for order in self.tracked_orders.values():
            if order['status'] == 'ACTIVE':
                active_positions += 1
            elif order['status'] == 'PENDING_LIVE':
                pending_orders += 1

        self.account_info = self._get_account_info()
        equity = self.account_info.get('equity', 0)
        balance = self.account_info.get('balance', 0)
        pnl_percent = ((equity - self.initial_balance) / self.initial_balance) * 100 if self.initial_balance > 0 else 0
        loss_thresh = self._loss_threshold()
        profit_thresh = self._profit_threshold()

        # Update peak equity
        if self.config.get('drawdown_mode') == 'peak_equity':
            self.peak_equity_session = max(self.peak_equity_session, equity)

        return {
            'status_message': self.status_message,
            'is_cooldown': self.is_cooldown,
            'cooldown_until': self.cooldown_end_time.strftime('%Y-%m-%d %H:%M:%S') if self.is_cooldown else "N/A",
            'cooldown_end_dt': self.cooldown_end_time,
            'equity': equity,
            'balance': balance,
            'pnl_percent': f"{pnl_percent:.2f}%",
            'loss_threshold': loss_thresh,
            'profit_threshold': profit_thresh
        }
    
    def close_specific_positions(self, tickets: list, reason: str):
        """[VERSI BARU] Menutup daftar posisi tertentu menggunakan mt5.Close()."""
        if not tickets:
            return

        logger.info(f"Menerima permintaan Smart Exit untuk tiket: {tickets}. Alasan: {reason}")
        
        # Ambil semua posisi live untuk difilter
        all_positions = self.mt5.positions_get()
        if not all_positions:
            return

        for position in all_positions:
            if position.ticket in tickets:
                logger.info(f"Smart Exit: Mencoba menutup posisi #{position.ticket} ({position.symbol})...")
                # Gunakan fungsi mt5.Close() yang lebih andal
                result = self.mt5.Close(symbol=position.symbol, ticket=position.ticket)
                if result != True:
                    error_code = self.mt5.last_error()
                    logger.error(f"Gagal menutup posisi #{position.ticket} (Smart Exit): {error_code}")
    
    def reset_session(self):
        """Mereset status manajer untuk memulai sesi trading baru setelah cooldown."""
        self.tracked_orders = {}
        self.session_start_time = datetime.now(pytz.utc)
        self.account_info = self._get_account_info()
        self.initial_balance = self.account_info.get('balance', 0)
        self.peak_equity_session = self.account_info.get('equity', 0)
        
        self.session_ending = False
        self.report_generated = False
        self.is_cooldown = False
        self.cooldown_end_time = None
        
        self.status_message = "Sesi baru dimulai. Monitoring normal."
        logger.info(f"Sesi untuk Akun {self.account_info.get('login')} telah di-reset.")

    # --- 2. METODE HELPER INTERNAL ---

    def _get_account_info(self):
        info = self.mt5.account_info()
        return info._asdict() if info else {}

    def _calculate_consecutive_losses(self):
        count = 0
        closed_trades = sorted([o for o in self.tracked_orders.values() if o['status'] == 'CLOSED_COMPLETE'], 
                               key=lambda x: x['closing_deal']['time'])
        for trade in closed_trades:
            if trade['closing_deal']['profit'] < 0:
                count += 1
            else:
                count = 0
        return count

    def _find_entry_deal(self, deal_list):
        for deal in deal_list:
            if deal.entry == 0: return deal._asdict()
        return None

    def _calculate_cooldown_end_time(self):
        """Menghitung waktu berakhirnya cooldown berdasarkan konfigurasi secara lengkap."""
        try:
            tz = pytz.timezone(self.config.get('timezone', 'UTC')) # [MODIFIKASI] Ambil timezone dari config
            now = datetime.now(tz)
        except Exception as e:
            logger.error(f"Timezone tidak valid: {self.config.get('timezone')}. Menggunakan UTC. Error: {e}")
            tz = pytz.utc
            now = datetime.now(tz)

        cooldown_cfg = self.config.get('cooldown_config', {})
        mode = cooldown_cfg.get('mode', 'duration')
        initial_cooldown_time = now
        was_adjusted_for_weekend = False

        if mode == 'duration':
            hours = cooldown_cfg.get('hours', 1)
            minutes = cooldown_cfg.get('minutes', 0)
            initial_cooldown_time = now + timedelta(hours=hours, minutes=minutes)
            
        elif mode == 'next_day_at':
            target_time_str = cooldown_cfg.get('time', '09:00')
            target_time = datetime.strptime(target_time_str, '%H:%M').time()
            next_day = now.date() + timedelta(days=1)
            initial_cooldown_time = tz.localize(datetime.combine(next_day, target_time))
            
        elif mode == 'next_candle':
            timeframe_map = {
                mt5.TIMEFRAME_M1: 60, mt5.TIMEFRAME_M5: 300, mt5.TIMEFRAME_M15: 900,
                mt5.TIMEFRAME_M30: 1800, mt5.TIMEFRAME_H1: 3600, mt5.TIMEFRAME_H4: 14400,
                mt5.TIMEFRAME_D1: 86400
            }
            tf_seconds = timeframe_map.get(cooldown_cfg.get('timeframe'), 3600)
            current_timestamp = int(now.timestamp())
            next_candle_timestamp = ((current_timestamp // tf_seconds) + 1) * tf_seconds
            initial_cooldown_time = datetime.fromtimestamp(next_candle_timestamp, tz=tz)
        
        final_cooldown_time = initial_cooldown_time
        
        if initial_cooldown_time.weekday() >= 5:
            was_adjusted_for_weekend = True
            days_to_monday = 7 - initial_cooldown_time.weekday()
            next_monday = initial_cooldown_time.date() + timedelta(days=days_to_monday)
            
            # Asumsikan pasar buka jam 8 pagi waktu lokal di hari Senin
            preserved_time = initial_cooldown_time.time()
            final_cooldown_time = tz.localize(datetime.combine(next_monday, preserved_time))
            
        day_name = final_cooldown_time.strftime('%A')
        time_str = final_cooldown_time.strftime('%H:%M:%S')

        if was_adjusted_for_weekend:
            log_message = f"Mode Cooldown: Awalnya jatuh di akhir pekan, disesuaikan ke hari {day_name} jam {time_str}."
        elif final_cooldown_time.date() > now.date():
            log_message = f"Mode Cooldown: Hingga hari berikutnya ({day_name}) jam {time_str}."
        else:
            log_message = f"Mode Cooldown: Hingga hari ini jam {time_str}."
        
        logger.info(log_message)
        return final_cooldown_time
        
    def _loss_threshold(self):
        loss_config = self.config.get('loss_target', {})
        value = loss_config.get('value', 5)
        type = loss_config.get('type', 'percent')
        
        if type == 'amount':
            return self.initial_balance - value
        else: # type == 'percent'
            base = self.peak_equity_session if self.config.get('drawdown_mode') == 'peak_equity' else self.initial_balance
            return base * (1 - value / 100)

    def _profit_threshold(self):
        profit_config = self.config.get('profit_target', {})
        value = profit_config.get('value', 10)
        type = profit_config.get('type', 'percent')

        if type == 'amount':
            return self.initial_balance + value
        else: # type == 'percent'
            return self.initial_balance * (1 + value / 100)

    def _gradual_stop_threshold(self):
        base = self.peak_equity_session if self.config.get('drawdown_mode') == 'peak_equity' else self.initial_balance
        return base * (1 - self.config.get('gradual_stop_percent', 3) / 100)

    def _build_final_report_data(self):
        completed_trades = []
        for order in self.tracked_orders.values():
            if order['status'] == 'CLOSED_COMPLETE' and order['closing_deal']:
                trade_record = order['closing_deal'].copy()
                if order['entry_deal']:
                    trade_record['price_open'] = order['entry_deal']['price']
                if 'strategy_info' in order:
                    trade_record['strategy'] = order['strategy_info'].get('entry_strategy', 'N/A')
                completed_trades.append(trade_record)

        return {
            "account_info": self.account_info, "config": self.config,
            "session_start_time": self.session_start_time, "session_end_time": datetime.now(pytz.utc),
            "initial_balance": self.initial_balance, "final_equity": self.account_info.get('equity', 0),
            "trades": completed_trades
        }
    
    def modify_positions_sl(self, sl_modifications: dict):
        """Menerima dictionary {tiket: new_sl} dan memodifikasi SL posisi."""
        if not sl_modifications:
            return

        for ticket, new_sl in sl_modifications.items():
            # Buat request modifikasi SL/TP
            request = {
                "action":   self.mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "sl":       new_sl,
            }
            result = self.mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"Berhasil memodifikasi SL untuk posisi #{ticket} ke {new_sl}.")
                # [PENTING] Tandai di jurnal bahwa breakeven sudah diterapkan
                journal_entry = next((o for o in self.tracked_orders.values() if o.get('position_id') == ticket), None)
                if journal_entry:
                    journal_entry['breakeven_applied'] = True
            else:
                logger.error(f"Gagal memodifikasi SL untuk posisi #{ticket}. Error: {self.mt5.last_error()}")