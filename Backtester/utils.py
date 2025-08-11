from __future__ import annotations
import json
from datetime import datetime
from typing import Iterable, Tuple, Union
from typing import Optional
from zoneinfo import ZoneInfo
import pandas as pd

def send_status(data: dict) -> None:
    """Kirim status (dict) sebagai JSON ke stdout (langsung flush)."""
    print(json.dumps(data), flush=True)

def to_epoch_ms(ts) -> int:
    """
    Konversi timestamp ke epoch milliseconds.
    - Menerima pandas.Timestamp, datetime, numpy datetime64, string datetime, atau int/float (anggap ms).
    - Naive datetime akan dilokalisasi sebagai UTC.
    """
    if isinstance(ts, (int, float)):
        return int(ts)
    t = pd.Timestamp(ts)
    if t.tzinfo is None or t.tz is None:
        t = t.tz_localize('UTC')
    else:
        t = t.tz_convert('UTC')
    return int(t.timestamp() * 1000)

def simulate_equity_stops(
    equity_curve: Iterable[Tuple[Union[int, float, str, datetime], float]],
    initial_balance: float,
    gain_target_percent: float,
    loss_limit_percent: float,
) -> str:
    """
    Scan kurva ekuitas dan laporkan kapan TP/SL equity tercapai.
    equity_curve: iterable [(ts, balance)] diurutkan waktu (ts bisa epoch-ms/int/float, ISO str, datetime, dll.)
    """
    if not equity_curve:
        return "Data kurva ekuitas tidak tersedia."

    def _to_dt(x):
        try:
            return pd.to_datetime(x, utc=True).to_pydatetime()
        except Exception:
            return None

    eq = [(_to_dt(t), float(b)) for t, b in equity_curve]
    if any(t is None for t, _ in eq):
        return "Format data kurva ekuitas tidak valid."

    gain_abs = initial_balance * (1 + gain_target_percent / 100.0)
    loss_abs = initial_balance * (1 - loss_limit_percent / 100.0)

    for dt, bal in eq:
        if bal >= gain_abs:
            return f"✅ TP {gain_target_percent}% Equity Tercapai: {dt:%Y-%m-%d}"
        if bal <= loss_abs:
            return f"❌ SL {loss_limit_percent}% Equity Tersentuh: {dt:%Y-%m-%d}"
    return "Equity tidak menyentuh target TP/SL."

def spread_pts(i: int, df, use_dyn_spread: bool, fallback_spread_pts: float) -> float:
    """Ambil spread (dalam points) untuk bar ke-i, dengan fallback aman."""
    if use_dyn_spread and 'spread' in getattr(df, 'columns', []):
        try:
            return float(df.iloc[i]['spread'])
        except Exception:
            return float(fallback_spread_pts)
    return float(fallback_spread_pts)

def exec_price(
    side: str,
    close_bid: float,
    spr_pts: float,
    leg: str,  # 'entry' | 'exit'
    point: float,
    slippage_pts: float,
    is_market: bool = True,
    level_price: Optional[float] = None,
) -> float:
    """Hitung harga eksekusi (ASK/BID + spread + slippage) untuk BUY/SELL, entry/exit."""
    s = float(spr_pts) * float(point)
    slip = float(slippage_pts) * float(point)

    if is_market:
        if side == 'BUY':
            if leg == 'entry':
                return float(close_bid) + s + slip   # BUY masuk di ASK
            else:
                return float(close_bid) - slip       # BUY keluar di BID
        else:  # SELL
            if leg == 'entry':
                return float(close_bid) - slip       # SELL masuk di BID
            else:
                return float(close_bid) + s + slip   # SELL keluar di ASK
    else:
        # eksekusi pada level (SL/TP) yang didefinisikan di BID
        px = float(level_price if level_price is not None else close_bid)
        if side == 'BUY':
            return px - slip                         # keluar BUY -> SELL di BID
        else:
            return px + s + slip                     # keluar SELL -> BUY di ASK

def commission_leg_usd(commission_rt_usd: float, lot: float) -> float:
    """Komisi per leg (setengah dari round-turn)."""
    return float(commission_rt_usd) * float(lot) * 0.5

def pnl_usd(side: str, entry_px: float, exit_px: float, lot: float, contract_size: float) -> float:
    """PnL USD berbasis harga eksekusi (sudah net spread/slippage di harga)."""
    diff = (float(exit_px) - float(entry_px)) if side == 'BUY' else (float(entry_px) - float(exit_px))
    return diff * float(lot) * float(contract_size)

def unrealized_pnl(side: Optional[str], entry_px: float, close_bid: float, lot: float, contract_size: float) -> float:
    """PnL belum terealisasi (mark-to-market) di BID."""
    if not side:
        return 0.0
    diff = (float(close_bid) - float(entry_px)) if side == 'BUY' else (float(entry_px) - float(close_bid))
    return diff * float(lot) * float(contract_size)

def in_session(
    ts_utc,                           # pandas.Timestamp tz-aware (UTC)
    start_trade_time, end_trade_time, # datetime.time
    session_base: str,                # 'UTC' | 'server'
    server_tz_name: str,              # e.g. 'Europe/London'
) -> bool:
    """Cek apakah timestamp UTC berada di dalam jam trading yang ditentukan."""
    try:
        if session_base == 'UTC':
            t = ts_utc.tz_convert('UTC').time()
        else:
            t = ts_utc.tz_convert(ZoneInfo(server_tz_name)).time()
    except Exception:
        # fallback aman
        t = ts_utc.tz_convert('UTC').time()
    return start_trade_time <= t <= end_trade_time