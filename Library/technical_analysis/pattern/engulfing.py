# File: Library/technical_analysis/patterns/candlesticks.py

import pandas as pd

def check_engulfing(df: pd.DataFrame, index: int = -2):
    if len(df) <= abs(index):
        return None

    try:
        current_candle = df.iloc[index]
        previous_candle = df.iloc[index - 1]

        # Cek Bullish Engulfing
        is_bullish = (previous_candle['open'] >= previous_candle['close'] and
                      current_candle['open'] < current_candle['close'] and
                      current_candle['close'] > previous_candle['open'])

        if is_bullish:
            return "bullish"

        # Cek Bearish Engulfing
        is_bearish = (previous_candle['open'] <= previous_candle['close'] and
                      current_candle['open'] > current_candle['close'] and
                      current_candle['close'] < previous_candle['open'])
        
        if is_bearish:
            return "bearish"

    except IndexError:
        # Jika terjadi error indeks karena data tidak cukup
        return None
        
    return None # Tidak ditemukan pola engulfing

def check_engulfing_strong(df: pd.DataFrame, index: int = -2):
    if len(df) <= abs(index):
        return None

    try:
        current_candle = df.iloc[index]
        previous_candle = df.iloc[index - 1]

        is_bullish_strong = (previous_candle['open'] >= previous_candle['close'] and
                      current_candle['open'] < current_candle['close'] and
                      current_candle['close'] > previous_candle['high'])

        if is_bullish_strong:
            return "bullish_strong"

        # Cek Bearish Engulfing
        is_bearish_strong = (previous_candle['open'] <= previous_candle['close'] and
                      current_candle['open'] > current_candle['close'] and
                      current_candle['close'] < previous_candle['low'])
        
        if is_bearish_strong:
            return "bearish_strong"

    except IndexError:
        # Jika terjadi error indeks karena data tidak cukup
        return None
        
    return None # Tidak ditemukan pola engulfing