import MetaTrader5 as mt5
import time

def get_open_positions(symbol: str, magic_number: int):
    """Mengambil posisi terbuka untuk simbol dan magic number tertentu."""
    try:
        # [PERBAIKAN] Ambil berdasarkan simbol, lalu filter manual dengan magic number
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return []
        return [p for p in positions if p.magic == magic_number]
    except Exception as e:
        print(f"Error saat mengambil posisi: {e}")
        return []

def get_pending_orders(magic_number: int):
    """Mengambil semua pending order yang cocok dengan magic number."""
    try:
        # [PERBAIKAN] Ambil SEMUA order, lalu filter manual dengan magic number dan status
        orders = mt5.orders_get()
        if orders is None:
            return []
        # Filter hanya order yang statusnya 'placed' (pending) dan magic numbernya cocok
        return [o for o in orders if o.magic == magic_number and o.state == mt5.ORDER_STATE_PLACED]
    except Exception as e:
        print(f"Error saat mengambil order: {e}")
        return []

def send_order(request: dict):
    """Fungsi dasar untuk mengirim request order ke MT5."""
    result = mt5.order_send(request)
    if result is None:
        return (False, "Gagal mengirim order, tidak ada respons dari server.")
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return (False, f"Gagal, retcode={result.retcode} - {result.comment}")
    return (True, f"Order #{result.order} berhasil.")

def cancel_order(ticket: int):
    """Membatalkan order berdasarkan nomor tiket."""
    request = {"action": mt5.TRADE_ACTION_REMOVE, "order": ticket}
    return send_order(request)

def cancel_order_by_ticket(ticket: int):
    """Membatalkan order berdasarkan nomor tiketnya."""
    request = {
        "action": mt5.TRADE_ACTION_REMOVE,
        "order": ticket,
        "comment": "Cancelled by new signal"
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return False, f"Gagal membatalkan: {result.comment} (retcode {result.retcode})"
    return True, "Order berhasil dibatalkan."

def cancel_expired_pending_orders(magic_number: int, expiration_seconds: int = 3600):
    """Membatalkan pending order yang usianya melebihi batas waktu."""
    pending_orders = get_pending_orders(magic_number)
    if not pending_orders: return
    current_time = int(time.time())
    for order in pending_orders:
        if (current_time - order.time_setup) > expiration_seconds:
            print(f"Membatalkan order #{order.ticket} karena kedaluwarsa (> 1 jam).")
            cancel_order(order.ticket)

def manage_trailing_stop(symbol: str, magic_number: int):
    """Manajemen Trailing Stop Cerdas (Breakeven)."""
    positions = get_open_positions(symbol=symbol, magic_number=magic_number)
    if not positions: return
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info: return
    point = symbol_info.point
    for position in positions:
        if (position.type == mt5.POSITION_TYPE_BUY and position.sl < position.price_open) or \
           (position.type == mt5.POSITION_TYPE_SELL and position.sl > position.price_open):
            initial_risk_points = abs(position.price_open - position.sl)
            tick = mt5.symbol_info_tick(symbol)
            if not tick: continue
            if position.type == mt5.POSITION_TYPE_BUY:
                current_profit_points = tick.bid - position.price_open
                if current_profit_points >= initial_risk_points:
                    new_sl = position.price_open + (2 * point)
                    request = {"action": mt5.TRADE_ACTION_SLTP, "position": position.ticket, "sl": new_sl, "tp": position.tp}
                    print(f"Posisi BUY #{position.ticket} BEP. Pindah SL ke {new_sl}")
                    send_order(request)
            elif position.type == mt5.POSITION_TYPE_SELL:
                current_profit_points = position.price_open - tick.ask
                if current_profit_points >= initial_risk_points:
                    new_sl = position.price_open - (2 * point)
                    request = {"action": mt5.TRADE_ACTION_SLTP, "position": position.ticket, "sl": new_sl, "tp": position.tp}
                    print(f"Posisi SELL #{position.ticket} BEP. Pindah SL ke {new_sl}")
                    send_order(request)

def close_position(position, comment: str):
    """Fungsi penutupan posisi yang tangguh dengan pengecekan hasil."""
    symbol = position.symbol
    
    # Tentukan tipe order penutupan yang berlawanan
    close_type = mt5.ORDER_TYPE_SELL if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    
    # Dapatkan harga yang TEPAT untuk penutupan
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"Gagal mendapatkan tick untuk {symbol} saat akan menutup posisi.")
        return None # Kembalikan None jika gagal

    price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
    
    # Siapkan request dengan slippage untuk toleransi harga
    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "position":     position.ticket,
        "symbol":       symbol,
        "volume":       position.volume,
        "type":         close_type,
        "price":        price,
        "deviation":    20, # Slippage dalam points
        "magic":        position.magic,
        "comment":      comment,
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC # IOC lebih fleksibel daripada FOK
    }

    # Kirim order dan LAKUKAN PENGECEKAN HASIL
    result = mt5.order_send(request)
    
    if result is None:
        print(f"Gagal mengirim perintah tutup untuk posisi #{position.ticket}. Tidak ada respons server.")
        return None

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"GAGAL MENUTUP posisi #{position.ticket}. Retcode: {result.retcode}, Comment: {result.comment}")
        return None
    
    print(f"BERHASIL menutup posisi #{position.ticket}. Deal #{result.deal}.")
    
    # Ambil dan kembalikan detail deal jika berhasil
    try:
        deal_details = mt5.history_deals_get(ticket=result.deal)
        if deal_details and len(deal_details) > 0:
            return deal_details[0]._asdict()
    except Exception as e:
        print(f"Berhasil menutup posisi, tetapi gagal mengambil detail deal #{result.deal}: {e}")
    
    return None