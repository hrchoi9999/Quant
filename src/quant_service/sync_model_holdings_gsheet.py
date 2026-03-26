from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
CORE_DB = PROJECT_ROOT / r"data\db\quant_service.db"
DETAIL_DB = PROJECT_ROOT / r"data\db\quant_service_detail.db"
DEFAULT_GSHEET_CRED = PROJECT_ROOT / r"config\quant-485814-0df3dc750a8d.json"
DEFAULT_GSHEET_ID = "1HAiebouwL6d_ikBd5l6M3t7OO2Zg8bz3uS0aOPwXfXs"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _log_sync(con: sqlite3.Connection, *, sync_id: str, batch_id: str | None, model_code: str, status: str, detail_text: str) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO ops_gsheet_sync_log (
          sync_id, batch_id, model_code, sync_target, status, started_at, finished_at, detail_text
        ) VALUES (?, ?, ?, 'published_holdings', ?, datetime('now'), datetime('now'), ?)
        """,
        (sync_id, batch_id, model_code, status, detail_text),
    )


def _published_models(con: sqlite3.Connection, asof_date: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT pmc.model_code, pmc.published_run_id, pmc.data_asof, pmc.signal_asof,
               pmc.display_name, pmc.latest_nav, pmc.latest_holdings_count, rr.batch_id
        FROM pub_model_current pmc
        JOIN run_runs rr ON rr.run_id = pmc.published_run_id
        WHERE pmc.data_asof = ?
        ORDER BY pmc.model_code
        """,
        con,
        params=[asof_date],
    )


def _artifact_df(core_con: sqlite3.Connection, run_id: str, model_code: str) -> pd.DataFrame | None:
    art = pd.read_sql_query(
        "SELECT artifact_path FROM run_artifacts WHERE run_id = ? ORDER BY artifact_path",
        core_con,
        params=[run_id],
    )
    if art.empty:
        return None
    paths = [Path(p) for p in art["artifact_path"].tolist()]
    chosen: Path | None = None
    if model_code == "S2":
        for p in paths:
            if p.name.startswith("regime_bt_snapshot_") and "__trades" not in p.name:
                chosen = p
                break
    else:
        for p in paths:
            if p.name.startswith("s3_holdings_last_top20"):
                chosen = p
                break
    if chosen and chosen.exists():
        return pd.read_csv(chosen, dtype={"ticker": str})
    return None


def _fallback_df(core_con: sqlite3.Connection, detail_con: sqlite3.Connection, model_code: str, run_id: str, asof_date: str) -> pd.DataFrame:
    pub = pd.read_sql_query(
        "SELECT * FROM pub_model_current_holdings WHERE model_code = ? AND asof_date = ? ORDER BY rank_no, ticker",
        core_con,
        params=[model_code, asof_date],
    )
    hist = pd.read_sql_query(
        "SELECT * FROM run_holdings_history WHERE run_id = ? ORDER BY date, rank_no, ticker",
        detail_con,
        params=[run_id],
    )
    if hist.empty:
        return pub
    latest_date = str(hist["date"].max())
    latest = hist[hist["date"].astype(str) == latest_date].copy()
    merged = pub.merge(
        latest[["ticker", "entry_date", "entry_price", "current_price", "cum_return_since_entry"]],
        on="ticker",
        how="left",
    )
    merged.insert(1, "signal_asof", latest_date)
    return merged


def _tab_name(model_code: str) -> str:
    if model_code == "S2":
        return "S2_snapshot"
    if model_code == "S3":
        return "S3_snapshot"
    return "S3_CORE2_snapshot"


def sync(asof_date: str, core_db_path: Path = CORE_DB, detail_db_path: Path = DETAIL_DB, cred_path: Path = DEFAULT_GSHEET_CRED, sheet_id: str = DEFAULT_GSHEET_ID, mode: str = "overwrite") -> None:
    from src.utils.gsheet_uploader import GSheetConfig, write_dataframe  # type: ignore

    core_con = sqlite3.connect(str(core_db_path))
    detail_con = sqlite3.connect(str(detail_db_path))
    try:
        models_df = _published_models(core_con, asof_date)
        if models_df.empty:
            raise RuntimeError(f"No published models found for asof={asof_date}")

        cfg = GSheetConfig(
            cred_path=str(cred_path),
            spreadsheet_id=str(sheet_id),
            mode=str(mode),
            start_cell="A1",
        )

        for row in models_df.itertuples(index=False):
            df = _artifact_df(core_con, row.published_run_id, row.model_code)
            source = "artifact_csv"
            if df is None or df.empty:
                df = _fallback_df(core_con, detail_con, row.model_code, row.published_run_id, asof_date)
                source = "db_fallback"

            if df.empty:
                _log_sync(
                    core_con,
                    sync_id=f"GSHEET__{row.model_code}__{asof_date.replace('-', '')}",
                    batch_id=row.batch_id,
                    model_code=row.model_code,
                    status="skipped",
                    detail_text="No holdings data available for upload",
                )
                continue

            if "ticker" in df.columns:
                df["ticker"] = df["ticker"].astype(str).str.zfill(6)

            write_dataframe(cfg, df, _tab_name(row.model_code))
            _log_sync(
                core_con,
                sync_id=f"GSHEET__{row.model_code}__{asof_date.replace('-', '')}",
                batch_id=row.batch_id,
                model_code=row.model_code,
                status="completed",
                detail_text=json.dumps({"rows": int(len(df)), "source": source, "tab": _tab_name(row.model_code)}, ensure_ascii=True),
            )

        core_con.commit()
    finally:
        core_con.close()
        detail_con.close()

    print(f"[OK] synced published holdings to Google Sheets for asof={asof_date}")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=date.today().strftime("%Y-%m-%d"), help="YYYY-MM-DD. Default: today")
    ap.add_argument("--core-db", default=str(CORE_DB))
    ap.add_argument("--detail-db", default=str(DETAIL_DB))
    ap.add_argument("--gsheet-cred", default=str(DEFAULT_GSHEET_CRED))
    ap.add_argument("--gsheet-id", default=DEFAULT_GSHEET_ID)
    ap.add_argument("--gsheet-mode", default="overwrite", choices=["overwrite", "new_sheet"])
    return ap.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sync(
        asof_date=args.asof,
        core_db_path=Path(args.core_db),
        detail_db_path=Path(args.detail_db),
        cred_path=Path(args.gsheet_cred),
        sheet_id=str(args.gsheet_id),
        mode=str(args.gsheet_mode),
    )
