import MetaTrader5 as mt5

def connect_to_mt5(login, password, server, path, timeout=10000):
    """
    Menghubungkan ke akun MT5 dengan timeout.
    Mengembalikan tuple: (is_success, result)
    - Jika sukses: (True, list_of_available_symbols)
    - Jika gagal: (False, error_message)
    """
    if not mt5.initialize(
        path=path,
        login=login,
        password=password,
        server=server,
        timeout=timeout  # Menggunakan timeout di sini
    ):
        error_code, error_desc = mt5.last_error()
        mt5.shutdown()
        return (False, f"Initialization Failed: {error_desc} (Code: {error_code})")

    account_info = mt5.account_info()
    if account_info is None:
        mt5.shutdown()
        return (False, "Connection successful, but failed to retrieve account info.")

    symbols = mt5.symbols_get()
    if symbols is None:
        mt5.shutdown()
        return (False, "Could not retrieve symbol list from the broker.")
        
    # Jika berhasil, langsung kembalikan daftar simbol
    available_symbols = [s.name for s in symbols]
    return (True, available_symbols)


def shutdown_connection():
    """Memutuskan koneksi dari terminal MT5."""
    mt5.shutdown()
    print("MT5 connection has been terminated.")