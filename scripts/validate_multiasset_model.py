# validate_multiasset_model.py ver 2026-03-17_002
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

try:
    from src.repositories.instrument_repository import InstrumentRepository
    from src.repositories.price_repository import PriceRepository
except Exception:
    CURRENT = Path(__file__).resolve()
    ROOT = next((p for p in [CURRENT] + list(CURRENT.parents) if (p / 'src').exists()), CURRENT.parent)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.repositories.instrument_repository import InstrumentRepository
    from src.repositories.price_repository import PriceRepository

PROJECT_ROOT = Path(r"D:\Quant")


def _pick_stock_sample(stocks: pd.DataFrame) -> list[str]:
    preferred = ['005930', '000660', '005935']
    existing = set(stocks['ticker'].astype(str).tolist())
    sample = [t for t in preferred if t in existing]
    if len(sample) >= 1:
        return sample
    return stocks['ticker'].astype(str).head(3).tolist()


def main() -> None:
    ap = argparse.ArgumentParser(description='Validate multi-asset metadata model.')
    ap.add_argument('--db', default=str(PROJECT_ROOT / r'data\db\price.db'))
    ap.add_argument('--asof', required=True, help='YYYYMMDD or YYYY-MM-DD')
    args = ap.parse_args()

    asof = str(args.asof).strip().replace('-', '')
    inst_repo = InstrumentRepository(Path(args.db))
    price_repo = PriceRepository(Path(args.db))

    instruments = inst_repo.get_instruments(active_only=True)
    required_cols = {'ticker','name','asset_type','market','is_active','first_seen','last_seen','asof','source'}
    missing = required_cols - set(instruments.columns)
    if missing:
        raise AssertionError(f'instrument_master missing columns: {sorted(missing)}')
    if instruments.empty:
        raise AssertionError('instrument_master is empty')

    etfs = inst_repo.get_instruments(asset_type='ETF', active_only=True)
    if etfs.empty:
        raise AssertionError('No ETF instruments registered with asset_type=ETF')

    stocks = inst_repo.get_instruments(asset_type='STOCK', active_only=True)
    if stocks.empty:
        raise AssertionError('No STOCK instruments returned; existing stock system may be broken')

    etf_core = inst_repo.get_etf_core_universe(asof=asof)
    if etf_core.empty:
        raise AssertionError('ETF core universe repository returned no rows')

    if not set(etf_core['ticker']).issubset(set(etfs['ticker'])):
        raise AssertionError('ETF core universe contains tickers not found in instrument_master ETF set')

    fx = inst_repo.get_etf_core_universe(asof=asof, group_key='fx_usd')
    if fx.empty:
        raise AssertionError('ETF core fx_usd group lookup failed')

    price_join_etf = price_repo.get_price_universe(asset_type='ETF', tickers=etf_core['ticker'].head(3).tolist(), start='2024-01-02', end='2024-01-10')
    if price_join_etf.empty:
        raise AssertionError('ETF price repository join returned no rows')
    meta_cols = {'asset_class','group_key','currency_exposure','is_inverse','is_leveraged'}
    if not meta_cols.issubset(set(price_join_etf.columns)):
        raise AssertionError('ETF price repository output missing ETF meta columns')

    stock_sample = _pick_stock_sample(stocks)
    price_join_stock = price_repo.get_price_universe(asset_type='STOCK', tickers=stock_sample, start='2026-03-01', end='2026-03-12')
    if price_join_stock.empty:
        raise AssertionError(f'Stock price repository join returned no rows for sample={stock_sample}')

    print(f'[OK] instrument_rows={len(instruments)} stock_rows={len(stocks)} etf_rows={len(etfs)}')
    print(f'[OK] etf_core_rows={len(etf_core)} fx_usd_rows={len(fx)}')
    print(f'[OK] etf_price_join_rows={len(price_join_etf)} stock_price_join_rows={len(price_join_stock)} stock_sample={stock_sample}')


if __name__ == '__main__':
    main()
