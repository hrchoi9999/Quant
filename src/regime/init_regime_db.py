import sqlite3
from pathlib import Path

DB = Path(r"D:\Quant\data\db\regime.db")
DB.parent.mkdir(parents=True, exist_ok=True)

con = sqlite3.connect(DB)
cur = con.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS regime_history (
    date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    horizon TEXT NOT NULL,          -- '1y','6m','3m'
    score REAL,
    regime INTEGER,                 -- 0..4
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (date, ticker, horizon)
);
""")

cur.execute("CREATE INDEX IF NOT EXISTS idx_regime_history_ticker_date ON regime_history(ticker, date);")

con.commit()

print("[DONE] created/verified regime.db and regime_history")
print("tables=", cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
print("schema=", cur.execute("PRAGMA table_info('regime_history')").fetchall())

con.close()
