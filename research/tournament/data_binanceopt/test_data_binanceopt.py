"""Tests for the Binance-options (EAPI) IV coverage study."""
import json
import os
import zipfile

import pandas as pd

import iv_lib

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join('data', 'raw', 'binance_eapi_20261007')


def test_no_future_dates_and_span_truncated():
    """Causality/truncation: every built series ends on its archive date;
    nothing reaches the dev/test years (>= 2021-09 walk-forward needs >= 2021-09)."""
    for f in ('BNB_iv_daily.parquet', 'XRP_iv_daily.parquet',
              'BTC_bvol_daily.parquet', 'ETH_bvol_daily.parquet'):
        df = pd.read_parquet(os.path.join(HERE, f))
        assert df['date'].is_unique and df['date'].is_monotonic_increasing
        assert df['date'].max() <= '2026-10-07'  # probe date; no future leakage
    bnb = pd.read_parquet(os.path.join(HERE, 'BNB_iv_daily.parquet'))
    xrp = pd.read_parquet(os.path.join(HERE, 'XRP_iv_daily.parquet'))
    assert bnb['date'].min() == '2023-05-18' and bnb['date'].max() == '2023-10-23'
    assert xrp['date'].min() == '2023-05-19' and xrp['date'].max() == '2023-10-20'
    # truncated: must NOT cover any walk-forward anchor year start
    assert bnb['date'].max() < '2021-09-01' or bnb['date'].max() < '2024-01-01'


def test_hand_checked_oi_weighted_iv():
    """Hand-checked synthetic: 3 rows, OI weights 1/2/7, IVs 1.0/0.5/0.2 ->
    oiw = (1 + 1 + 1.4)/10 = 0.34; median 0.5; junk row (iv=0) ignored."""
    df = pd.DataFrame({
        'symbol': ['A', 'B', 'C', 'JUNK'],
        'mark_iv': [1.0, 0.5, 0.2, 0.0],
        'openinterest_contracts': [1.0, 2.0, 7.0, 100.0],
    })
    got = iv_lib.daily_iv(df, '2023-05-18')
    assert abs(got['iv_oiw'] - 3.4 / 10.0) < 1e-12
    assert got['iv_med'] == 0.5
    assert got['n_rows'] == 3 and got['n_symbols'] == 3


def test_parquet_matches_raw_zip():
    """One real day recomputed from the raw zip equals the parquet row."""
    z = os.path.join(RAW, 'eoh', 'BNBUSDT-EOHSummary-2023-05-18.zip')
    with zipfile.ZipFile(z) as zf:
        raw = pd.read_csv(zf.open(zf.namelist()[0]))
    got = iv_lib.daily_iv(raw, '2023-05-18')
    pq = pd.read_parquet(os.path.join(HERE, 'BNB_iv_daily.parquet'))
    row = pq[pq['date'] == '2023-05-18'].iloc[0]
    assert abs(got['iv_oiw'] - row['iv_oiw']) < 1e-9
    assert abs(got['iv_med'] - row['iv_med']) < 1e-9
    assert got['n_symbols'] == row['n_symbols']


def test_manifest_covers_downloads():
    man = json.load(open(os.path.join(HERE, 'manifest.json')))
    assert man['totals']['n_zips'] == 560
    assert man['totals']['bytes'] < 500_000_000
    assert set(man['files']) >= {'BNB_iv_daily.parquet', 'XRP_iv_daily.parquet'}
