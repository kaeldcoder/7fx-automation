
import math
from ..data_handler.data_handler import get_account_info, get_symbol_info
from PyQt6.QtWidgets import QApplication

def calculate_lot_size(risk_percent: float, entry_price: float, sl_level: float, symbol: str):
    """
    Menghitung ukuran lot dengan logika baru untuk menangani lot minimum.
    """
    account_info = get_account_info()
    symbol_info = get_symbol_info(symbol)

    if not all([account_info, symbol_info]):
        return (None, QApplication.translate("position_sizer", "Failed to get account or symbol info."))

    balance = account_info.balance
    risk_amount = balance * (risk_percent / 100.0)

    sl_distance = abs(entry_price - sl_level)
    if sl_distance == 0:
        return (None, QApplication.translate("position_sizer", "Stop Loss distance cannot be zero."))

    # Periksa apakah nilai tick/point valid untuk menghindari pembagian dengan nol
    if symbol_info.trade_tick_value == 0 or symbol_info.point == 0:
         return (None, QApplication.translate("position_sizer", "Tick/Point value for {0} is invalid.").format(symbol))

    # Gunakan trade_tick_value untuk perhitungan yang lebih akurat, terutama untuk non-forex
    loss_per_lot = (sl_distance / symbol_info.point) * symbol_info.trade_tick_value
    
    if loss_per_lot == 0:
        return (None, QApplication.translate("position_sizer", "Loss per lot is zero, calculation cancelled."))

    lot_size = risk_amount / loss_per_lot
    
    # --- [UPGRADE LOGIKA] ---
    volume_min = symbol_info.volume_min
    volume_step = symbol_info.volume_step

    # Jika lot yang dihitung lebih kecil dari minimum, gunakan lot minimum
    if lot_size < volume_min:
        lot_size = volume_min
    else:
        # Jika lebih besar, bulatkan ke bawah sesuai volume step broker
        lot_size = math.floor(lot_size / volume_step) * volume_step
    
    # Pastikan tidak melebihi volume maksimum
    if lot_size > symbol_info.volume_max:
        lot_size = symbol_info.volume_max

    # Pembulatan akhir untuk memastikan format benar
    return (round(lot_size, 2), QApplication.translate("position_sizer", "Lot calculation successful."))