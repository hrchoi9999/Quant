# create_dim_corp_listed.py ver 2025-12-11_005

import sqlite3
from pathlib import Path

# ✅ 실제 DART DB 파일 경로 (inspect_corp_fs.py와 동일하게)
DB_PATH = Path(r"D:\Quant\data\db\dart_main.db")


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB 파일을 찾을 수 없습니다: {DB_PATH}")

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # dim_corp 컬럼 구조 확인
    cur.execute("PRAGMA table_info(dim_corp);")
    cols_info = cur.fetchall()
    if not cols_info:
        raise RuntimeError("dim_corp 테이블이 없습니다. 테이블 이름을 다시 확인해 주세요.")

    cols = [row[1] for row in cols_info]
    has_corp_cls = "corp_cls" in cols
    has_modify_date = "modify_date" in cols

    print("[1] dim_corp_listed 테이블 삭제 후 재생성")
    cur.execute("DROP TABLE IF EXISTS dim_corp_listed;")

    # SELECT 컬럼 구성
    select_cols = ["corp_code", "corp_name", "stock_code"]
    if has_corp_cls:
        select_cols.append("corp_cls")
    if has_modify_date:
        select_cols.append("modify_date")

    select_cols_sql = ", ".join(select_cols)

    # WHERE 조건 (상장사 필터)
    where_sql = """
        stock_code IS NOT NULL
        AND stock_code <> ''
        AND LENGTH(stock_code) = 6
        AND stock_code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'
    """
    if has_corp_cls:
        where_sql += " AND corp_cls IN ('Y', 'K', 'N')"

    create_sql = f"""
        CREATE TABLE dim_corp_listed AS
        SELECT {select_cols_sql}
        FROM dim_corp
        WHERE {where_sql};
    """

    cur.execute(create_sql)

    # 인덱스 생성
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_dim_corp_listed_corp_code "
        "ON dim_corp_listed(corp_code);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_dim_corp_listed_stock_code "
        "ON dim_corp_listed(stock_code);"
    )

    cur.execute("SELECT COUNT(*) FROM dim_corp_listed;")
    cnt = cur.fetchone()[0]

    con.commit()
    con.close()

    print(f"[2] dim_corp_listed 생성 완료. 상장사 수: {cnt:,}개")


if __name__ == "__main__":
    main()
