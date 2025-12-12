import pandas as pd
from pathlib import Path

base_dir = Path(r"D:\Quant\data\raw\dart")  # 실제 폴더 경로로 수정

files = [
    "fs_00593032_2024_11014_CFS.parquet",
    "corp_list.parquet",
]

for fname in files:
    parquet_path = base_dir / fname
    csv_path = base_dir / (parquet_path.stem + ".csv")

    df = pd.read_parquet(parquet_path)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"완료: {parquet_path.name} → {csv_path.name}")
