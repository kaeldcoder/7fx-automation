import MetaTrader5 as mt5
import pandas as pd

def get_rates(symbol: str, timeframe, count: int):
    """
    Mengambil data harga (candlestick) dari MT5.

    Returns:
        pd.DataFrame: DataFrame berisi data OHLC, atau DataFrame kosong jika gagal.
    """
    try:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0:
            print(f"Peringatan: Tidak ada data untuk {symbol} di {timeframe}.")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df
    except Exception as e:
        print(f"Error saat mengambil rates: {e}")
        return pd.DataFrame()

def get_account_info():
    """Mengambil informasi akun yang sedang terhubung."""
    try:
        return mt5.account_info()
    except Exception as e:
        print(f"Error saat mengambil info akun: {e}")
        return None

def get_symbol_info(symbol: str):
    """Mengambil informasi spesifik untuk sebuah simbol (misal: point, contract size)."""
    try:
        return mt5.symbol_info(symbol)
    except Exception as e:
        print(f"Error saat mengambil info simbol {symbol}: {e}")
        return None

def get_live_tick(symbol: str):
    """Mengambil data tick (harga bid/ask) terbaru untuk sebuah simbol."""
    try:
        return mt5.symbol_info_tick(symbol)
    except Exception as e:
        print(f"Error saat mengambil tick untuk {symbol}: {e}")
        return None

def get_all_symbols():
    """Mengambil daftar semua simbol yang tersedia di broker."""
    try:
        symbols = mt5.symbols_get()
        if symbols:
            return sorted([s.name for s in symbols])
        return []
    except Exception as e:
        print(f"Error saat mengambil daftar simbol: {e}")
        return []