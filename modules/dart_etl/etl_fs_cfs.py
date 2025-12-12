# etl_fs_cfs.py ver 2025-12-11_002

import sqlite3
from pathlib import Path
from datetime import datetime

import pandas as pd

DB_PATH = Path(r"D:\Quant\data\db\dart_main.db")
RAW_DIR = Path(r"D:\Quant\data\raw\dart")


def detect_fs_div(path: Path) -> str:
    """
    파일명에서 CFS / SEPARATE 구분.
    예: fs_00593032_2024_11014_CFS.parquet
    """
    name = path.stem.upper()
    if "CFS" in name:
        return "CFS"
    if "SEPARATE" in name or "SEPA" in name:
        return "SEPARATE"
    return "UNKNOWN"


def normalize_corp_code(val):
    """
    DART corp_code를 8자리 문자열로 강제 정규화.
    예: 593032 -> '00593032'
    """
    if pd.isna(val):
        return None
    try:
        return f"{int(val):08d}"
    except Exception:
        s = str(val).strip()
        if len(s) >= 8:
            return s[-8:]
        return s.zfill(8)


def to_float(val):
    """
    안전한 float 변환.
    - 빈 문자열, '-', NaN 등은 None으로 처리.
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    if s in ("", "-", "NaN", "nan", "None"):
        return None

    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def to_int(val):
    """
    안전한 int 변환. 변환 안 되면 None.
    """
    if val is None:
        return None
    if isinstance(val, int):
        return val

    s = str(val).strip()
    if s in ("", "-", "NaN", "nan", "None", ""):
        return None

    s = s.replace(",", "")
    try:
        return int(float(s))
    except ValueError:
        return None


def load_fs_parquet_to_main():
    print("### DEBUG: load_fs_parquet_to_main() 진입")

    if not RAW_DIR.exists():
        print(f"[ERROR] RAW_DIR 경로가 없습니다: {RAW_DIR}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    parquet_files = sorted(RAW_DIR.glob("fs_*.parquet"))
    print(f"[INFO] 발견된 fs_*.parquet 파일 수: {len(parquet_files)}")

    if not parquet_files:
        conn.close()
        print("[WARN] 처리할 parquet 파일이 없습니다.")
        return

    total_files = len(parquet_files)

    for idx, p in enumerate(parquet_files, start=1):
        fs_div = detect_fs_div(p)
        print(f"[INFO] ({idx}/{total_files}) 처리 시작: {p.name} (fs_div={fs_div})")

        try:
            df = pd.read_parquet(p)
        except Exception as e:
            print(f"[ERROR] parquet 읽기 실패: {p.name} - {e}")
            continue

        # 필수 컬럼 체크
        required_cols = {
            "corp_code", "bsns_year", "rcept_no", "reprt_code",
            "sj_div", "sj_nm", "account_id", "account_nm", "ord"
        }
        missing = required_cols - set(df.columns)
        if missing:
            print(f"[WARN] 필수 컬럼 누락으로 스킵: {p.name} (missing={missing})")
            continue

        # 기본 타입 정리
        df["corp_code"] = df["corp_code"].apply(normalize_corp_code)
        df["bsns_year"] = df["bsns_year"].astype(int)
        df["rcept_no"] = df["rcept_no"].astype(str)
        df["reprt_code"] = df["reprt_code"].astype(str)

        meta = df.iloc[0]
        rcept_no = meta["rcept_no"]
        reprt_code = meta["reprt_code"]
        bsns_year = int(meta["bsns_year"])
        corp_code = meta["corp_code"]

        # fact_report Upsert
        cur.execute(
            """
            INSERT INTO fact_report (rcept_no, reprt_code, bsns_year, corp_code, fs_div, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(rcept_no) DO UPDATE SET
                reprt_code = excluded.reprt_code,
                bsns_year  = excluded.bsns_year,
                corp_code  = excluded.corp_code,
                fs_div     = excluded.fs_div
            """,
            (
                rcept_no,
                reprt_code,
                bsns_year,
                corp_code,
                fs_div,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

        inserted = 0

        for row in df.itertuples(index=False):
            cur.execute(
                """
                INSERT INTO fact_fs_account (
                    rcept_no, corp_code, bsns_year, fs_div,
                    sj_div, sj_nm,
                    account_id, account_nm, account_detail,
                    ord, currency,
                    thstrm_nm, thstrm_amount,
                    frmtrm_nm, frmtrm_amount
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (rcept_no, fs_div, account_id, sj_div, ord)
                DO UPDATE SET
                    account_nm      = excluded.account_nm,
                    account_detail  = excluded.account_detail,
                    currency        = excluded.currency,
                    thstrm_nm       = excluded.thstrm_nm,
                    thstrm_amount   = excluded.thstrm_amount,
                    frmtrm_nm       = excluded.frmtrm_nm,
                    frmtrm_amount   = excluded.frmtrm_amount
                """,
                (
                    str(row.rcept_no),
                    normalize_corp_code(row.corp_code),
                    int(row.bsns_year),
                    fs_div,
                    str(row.sj_div),
                    str(row.sj_nm),
                    str(row.account_id),
                    str(row.account_nm),
                    getattr(row, "account_detail", None)
                    if pd.notna(getattr(row, "account_detail", None))
                    else None,
                    to_int(getattr(row, "ord", None)),
                    getattr(row, "currency", None)
                    if pd.notna(getattr(row, "currency", None))
                    else None,
                    getattr(row, "thstrm_nm", None)
                    if pd.notna(getattr(row, "thstrm_nm", None))
                    else None,
                    to_float(getattr(row, "thstrm_amount", None)),
                    getattr(row, "frmtrm_nm", None)
                    if pd.notna(getattr(row, "frmtrm_nm", None))
                    else None,
                    to_float(getattr(row, "frmtrm_amount", None)),
                ),
            )
            inserted += 1

        conn.commit()
        print(f"[INFO] 처리 완료: {p.name} (rows tried={inserted})")

    conn.close()
    print("[INFO] 모든 fs_*.parquet 처리 완료")


if __name__ == "__main__":
    print("### DEBUG: etl_fs_cfs.py __main__ 진입")
    load_fs_parquet_to_main()
