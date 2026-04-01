from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Quant")
SCHEMA_PATH = PROJECT_ROOT / r"src\quant_service\schema_tseries_operational.sql"
DB_PATH = PROJECT_ROOT / r"data\db\tseries_operational.db"


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    con = sqlite3.connect(str(DB_PATH))
    try:
        con.executescript(schema_sql)
        con.commit()
        print(f"[OK] initialized {DB_PATH}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
