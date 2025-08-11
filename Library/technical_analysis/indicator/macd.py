import pandas as pd

# Fungsinya tetap sama persis, tidak perlu diubah
def calculate_macd(data, fast_period, slow_period, signal_period):
    """
    Menghitung dan menambahkan Indikator MACD ke DataFrame.
    Fungsi ini fleksibel dan menerima parameter periode.
    """
    # 1. Hitung EMA Cepat dan Lambat
    ema_fast = data['Close'].ewm(span=fast_period, adjust=False).mean()
    ema_slow = data['Close'].ewm(span=slow_period, adjust=False).mean()

    # 2. Hitung Garis MACD
    data['MACD'] = ema_fast - ema_slow

    # 3. Hitung Garis Sinyal (Signal Line)
    data['Signal_Line'] = data['MACD'].ewm(span=signal_period, adjust=False).mean()

    # 4. Hitung Histogram
    data['Histogram'] = data['MACD'] - data['Signal_Line']

    return data