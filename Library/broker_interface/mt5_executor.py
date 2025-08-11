# D:\7FX Automation\Library\execution\trade_executor.py

import MetaTrader5 as mt5
from Library.risk_management.trade_manager import TradeManager
from PyQt6.QtWidgets import QApplication
from Library.broker_interface.mt5_broker import send_order, get_open_positions, get_pending_orders

def place_pending_order(symbol: str, order_type, volume: float, entry_price: float, 
                        sl_level: float, tp_level: float, magic_number: int, 
                        trade_manager: TradeManager = None): # <-- [REVISI] Jadikan opsional
    """
    Menempatkan pending order dengan filter duplikat yang kompatibel.
    """
    # [REVISI] Logika pengecekan duplikat yang baru
    if trade_manager:
        # MODE BARU: Cek ke jurnal internal yang cepat jika TM tersedia
        for order in trade_manager.tracked_orders.values():
            if (order['status'] == 'PENDING_LIVE' and order['symbol'] == symbol and 
                abs(order.get('entry_price', 0) - entry_price) < 0.00001):
                return (False, QApplication.translate("mt5_executor", "Duplicate order prevented by TM journal."))
    else:
        # MODE LAMA (KOMPATIBEL): Cek ke MT5 langsung jika TM tidak ada
        pending_orders = get_pending_orders(magic_number=magic_number)
        if pending_orders:
            for order in pending_orders:
                if order.symbol == symbol and abs(order.price_open - entry_price) < 0.00001:
                    return (False, QApplication.translate("mt5_executor", "Duplicate order found on MT5."))

    # Bangun request order
    request = {
        "action": mt5.TRADE_ACTION_PENDING, "symbol": symbol, "volume": volume,
        "type": order_type, "price": entry_price, "sl": sl_level, "tp": tp_level,
        "magic": magic_number, "comment": "7FX_pending_bot",
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_FOK,
    }
    
    return send_order(request)

def place_market_order(symbol: str, order_type, volume: float, sl_level: float, 
                       tp_level: float, magic_number: int):
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        return (False, "Failed to get symbol info.")
    
    if not symbol_info.visible:
        mt5.symbol_select(symbol, True)
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return (False, QApplication.translate("mt5_executor", "Failed to get current tick price."))

    price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return (False, "Failed to retrieve symbol info")

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       volume,
        "type":         order_type,
        "price":        price,
        "sl":           sl_level,
        "tp":           tp_level,
        "deviation":    20,
        "magic":        magic_number,
        "comment":      "7FX_market_bot",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": 2,
    }
    print("Available fill flags:", symbol_info.trade_fill_flags)
    print("=================================================")
    print(symbol_info)

    return send_order(request)

    