# sync_multiasset_metadata.py ver 2026-03-17_001
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

try:
    from src.metadata.etf_meta_store import EtfMetaStore
    from src.metadata.instrument_master import InstrumentMasterStore
except Exception:
    CURRENT = Path(__file__).resolve()
    ROOT = next((p for p in [CURRENT] + list(CURRENT.parents) if (p / 'src').exists()), CURRENT.parent)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.metadata.etf_meta_store import EtfMetaStore
    from src.metadata.instrument_master import InstrumentMasterStore

PROJECT_ROOT = Path(r"D:\Quant")


def _latest(path_pattern: str) -> Path:
    files = sorted((PROJECT_ROOT / 'data' / 'universe').glob(path_pattern))
    if not files:
        raise FileNotFoundError(path_pattern)
    return files[-1]


def _build_stock_master(price_db: Path, asof: str) -> pd.DataFrame:
    universe_files = [
        PROJECT_ROOT / 'data' / 'universe' / 'universe_mix_top400_latest.csv',
        PROJECT_ROOT / 'data' / 'universe' / 'universe_top200_kospi_latest.csv',
        PROJECT_ROOT / 'data' / 'universe' / 'universe_top200_kosdaq_latest.csv',
    ]
    frames = []
    for path in universe_files:
        if path.exists():
            df = pd.read_csv(path, dtype={'ticker': 'string'})
            keep = [c for c in ['ticker', 'name', 'market'] if c in df.columns]
            frames.append(df[keep].copy())
    universe_df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=['ticker']) if frames else pd.DataFrame(columns=['ticker','name','market'])
    with sqlite3.connect(str(price_db)) as con:
        price_tickers = pd.read_sql_query("SELECT ticker, MIN(date) AS first_seen, MAX(date) AS last_seen FROM prices_daily GROUP BY ticker", con)
    price_tickers['ticker'] = price_tickers['ticker'].astype(str).str.zfill(6)
    merged = price_tickers.merge(universe_df, on='ticker', how='left')
    merged['name'] = merged['name'].fillna('')
    merged['market'] = merged['market'].fillna('KRX')
    merged['asset_type'] = 'STOCK'
    merged['is_active'] = 1
    merged['asof'] = asof
    merged['source'] = 'stock_universe_latest+price_db'
    return merged[['ticker','name','asset_type','market','is_active','first_seen','last_seen','asof','source']]


def _build_etf_instrument_master(etf_master_csv: Path, asof: str) -> pd.DataFrame:
    df = pd.read_csv(etf_master_csv, dtype={'ticker': 'string'}).copy()
    df['ticker'] = df['ticker'].astype(str).str.zfill(6)
    df['asset_type'] = 'ETF'
    df['market'] = 'ETF'
    df['is_active'] = 1
    df['first_seen'] = asof
    df['last_seen'] = asof
    df['asof'] = asof
    df['source'] = 'etf_master'
    return df[['ticker','name','asset_type','market','is_active','first_seen','last_seen','asof','source']]


def _build_etf_meta(etf_meta_csv: Path, etf_core_csv: Path, asof: str) -> pd.DataFrame:
    meta = pd.read_csv(etf_meta_csv, dtype={'ticker':'string'}).copy()
    core = pd.read_csv(etf_core_csv, dtype={'ticker':'string'}).copy()
    core_tickers = set(core['ticker'].astype(str).str.zfill(6).tolist())
    meta['ticker'] = meta['ticker'].astype(str).str.zfill(6)
    meta['core_eligible'] = meta['ticker'].isin(core_tickers)
    meta['meta_source'] = 'task02_core_meta'
    meta['rule_version'] = '2026-03-17_001'
    meta['asof'] = asof
    keep = ['ticker','asset_class','group_key','currency_exposure','is_inverse','is_leveraged','core_eligible','liquidity_20d_value','asof','meta_source','rule_version']
    return meta[keep]


def main() -> None:
    ap = argparse.ArgumentParser(description='Sync multi-asset metadata into instrument_master and etf_meta.')
    ap.add_argument('--asof', required=True, help='YYYYMMDD or YYYY-MM-DD')
    ap.add_argument('--db', default=str(PROJECT_ROOT / r'data\db\price.db'))
    ap.add_argument('--export-csv', action='store_true')
    args = ap.parse_args()

    asof = str(args.asof).strip().replace('-', '')
    db_path = Path(args.db)
    etf_master_csv = PROJECT_ROOT / 'data' / 'universe' / 'universe_etf_master_latest.csv'
    etf_meta_csv = PROJECT_ROOT / 'data' / 'universe' / f'etf_meta_{asof}.csv'
    etf_core_csv = PROJECT_ROOT / 'data' / 'universe' / f'universe_etf_core_{asof}.csv'

    instrument_store = InstrumentMasterStore(db_path)
    etf_store = EtfMetaStore(db_path)

    stock_df = _build_stock_master(db_path, f'{asof[0:4]}-{asof[4:6]}-{asof[6:8]}')
    etf_inst_df = _build_etf_instrument_master(etf_master_csv, asof)
    etf_meta_df = _build_etf_meta(etf_meta_csv, etf_core_csv, asof)

    etf_tickers = set(etf_inst_df['ticker'].tolist())
    stock_df = stock_df[~stock_df['ticker'].isin(etf_tickers)].copy()

    stock_n = instrument_store.upsert(stock_df)
    etf_n = instrument_store.upsert(etf_inst_df)
    meta_n = etf_store.upsert(etf_meta_df)

    print(f'[INFO] stock_instruments_upserted={stock_n}')
    print(f'[INFO] etf_instruments_upserted={etf_n}')
    print(f'[INFO] etf_meta_upserted={meta_n}')

    if args.export_csv:
        outdir = PROJECT_ROOT / 'data' / 'universe'
        inst_path = outdir / f'instrument_master_{asof}.csv'
        meta_path = outdir / f'etf_meta_store_{asof}.csv'
        instrument_store.export_csv(inst_path)
        etf_store.export_csv(meta_path, asof)
        print(f'[INFO] instrument_master_csv={inst_path}')
        print(f'[INFO] etf_meta_store_csv={meta_path}')


if __name__ == '__main__':
    main()
