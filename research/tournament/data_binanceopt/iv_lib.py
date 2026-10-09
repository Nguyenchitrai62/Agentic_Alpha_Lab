"""Shared helpers for the Binance-options (EAPI) IV coverage study.

Daily IV convention (fixed before any outcome was computed): for each UTC
archive date, OI-weighted mean (iv_oiw) and median (iv_med) of `mark_iv`
over EOHSummary hourly rows with mark_iv > 0 and openinterest_contracts > 0.
"""
import pandas as pd

REQ_COLS = ('mark_iv', 'openinterest_contracts', 'symbol')


def daily_iv(rows: pd.DataFrame, date: str) -> dict:
    df = rows[(rows['mark_iv'] > 0) & (rows['openinterest_contracts'] > 0)]
    if len(df) == 0:
        return {'date': date, 'iv_oiw': float('nan'), 'iv_med': float('nan'),
                'n_rows': 0, 'n_symbols': 0, 'oi_contracts': 0.0}
    oi = df['openinterest_contracts'].astype(float)
    iv = df['mark_iv'].astype(float)
    return {'date': date, 'iv_oiw': float((iv * oi).sum() / oi.sum()),
            'iv_med': float(iv.median()), 'n_rows': int(len(df)),
            'n_symbols': int(df['symbol'].nunique()), 'oi_contracts': float(oi.sum())}
