# fix_regime_blob_to_int.py ver 2026-01-29_001
import argparse
import sqlite3
from pathlib import Path

def blob_to_int(v):
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray, memoryview)):
        b = bytes(v)
        # 대부분 케이스: 8바이트 little-endian 정수
        if len(b) in (1, 2, 4, 8):
            return int.from_bytes(b, byteorder="little", signed=True)
        # 혹시 ASCII 숫자 형태로 들어간 경우
        try:
            return int(b.decode("utf-8").strip())
        except Exception:
            return None
    # 이미 int/float 등으로 들어오는 경우
    try:
        return int(v)
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="path to sqlite db file")
    ap.add_argument("--table", default="regime_history")
    ap.add_argument("--batch", type=int, default=50000)
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()

        # 성능/안정 PRAGMA
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA temp_store=MEMORY;")
        cur.execute("PRAGMA cache_size=-200000;")  # 약 200MB 캐시(환경에 따라 조정 가능)

        # 사전 진단
        dist_before = cur.execute(
            f"SELECT typeof(regime), COUNT(*) FROM {args.table} GROUP BY 1"
        ).fetchall()
        print("[BEFORE] typeof(regime) dist:", dist_before)

        blob_total = cur.execute(
            f"SELECT COUNT(*) FROM {args.table} WHERE typeof(regime)='blob'"
        ).fetchone()[0]
        print(f"[INFO] blob rows = {blob_total:,}")

        if blob_total == 0:
            print("[DONE] nothing to fix.")
            return

        updated = 0
        while True:
            # rowid 기반으로 잡아서 UPDATE (PK 3컬럼보다 빠르고 단순)
            rows = cur.execute(
                f"""
                SELECT rowid, regime, length(regime)
                FROM {args.table}
                WHERE typeof(regime)='blob'
                LIMIT ?
                """,
                (args.batch,)
            ).fetchall()

            if not rows:
                break

            params = []
            for rowid, reg_blob, reg_len in rows:
                r = blob_to_int(reg_blob)
                if r is None:
                    continue
                params.append((r, rowid))

            cur.executemany(
                f"UPDATE {args.table} SET regime=? WHERE rowid=?",
                params
            )
            con.commit()

            updated += len(params)
            print(f"[PROGRESS] updated {updated:,}/{blob_total:,} (batch={len(params):,})")

        # 사후 검증
        dist_after = cur.execute(
            f"SELECT typeof(regime), COUNT(*) FROM {args.table} GROUP BY 1"
        ).fetchall()
        print("[AFTER] typeof(regime) dist:", dist_after)

        blob_left = cur.execute(
            f"SELECT COUNT(*) FROM {args.table} WHERE typeof(regime)='blob'"
        ).fetchone()[0]
        if blob_left != 0:
            sample = cur.execute(
                f"SELECT date,ticker,horizon,regime,length(regime) FROM {args.table} WHERE typeof(regime)='blob' LIMIT 5"
            ).fetchall()
            raise RuntimeError(f"[FATAL] still blob rows={blob_left}, samples={sample}")

        # 값 범위 sanity check (0..4 기대)
        minmax = cur.execute(
            f"SELECT MIN(regime), MAX(regime) FROM {args.table}"
        ).fetchone()
        print("[CHECK] regime min/max:", minmax)

        print("[DONE] blob -> integer conversion completed successfully.")
    finally:
        con.close()

if __name__ == "__main__":
    main()
