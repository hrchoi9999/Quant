# clean_universe_by_krx_master.py ver 2026-01-27_002
import re
import argparse
from pathlib import Path
import pandas as pd


def normalize_ticker(x: str) -> str:
    """
    - 공백 제거, '.0' 제거
    - 숫자(1~6자리)면 6자리로 zfill(선행 0 복원)
    - 숫자+문자 혼합(예: 00680K, 0126Z0)은 그대로 둠(뒤에서 필터로 제거 가능)
    """
    if x is None:
        return ""
    s = str(x).strip()
    s = re.sub(r"\.0$", "", s)  # 엑셀/판다스 float 흔적 제거
    if re.fullmatch(r"\d{1,6}", s):
        return s.zfill(6)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--univ-in", required=True, help="입력 유니버스 CSV 경로")
    ap.add_argument("--krx-master", required=True, help="현재 상장 마스터 CSV 경로")
    ap.add_argument("--ticker-col", default="ticker", help="종목코드 컬럼명")
    ap.add_argument("--univ-out", default="", help="출력 CSV 경로(미지정 시 _clean.csv)")
    args = ap.parse_args()

    univ_in = Path(args.univ_in)
    krx_master = Path(args.krx_master)
    tcol = args.ticker_col

    # dtype을 강제하지 않더라도 normalize_ticker가 처리하지만,
    # read_csv 단계에서 숫자로 변환되는 걸 막기 위해 dtype=str 권장
    u = pd.read_csv(univ_in, dtype={tcol: "string"})
    m = pd.read_csv(krx_master, dtype={tcol: "string"})

    if tcol not in u.columns:
        raise ValueError(f"유니버스 파일에 '{tcol}' 컬럼이 없습니다. columns={list(u.columns)}")
    if tcol not in m.columns:
        raise ValueError(f"마스터 파일에 '{tcol}' 컬럼이 없습니다. columns={list(m.columns)}")

    # 1) ticker 정규화(선행 0 복원)
    u[tcol] = u[tcol].map(normalize_ticker)
    m[tcol] = m[tcol].map(normalize_ticker)

    # 2) 6자리 숫자만 남기기(특수코드 제거)
    u2 = u[u[tcol].str.match(r"^\d{6}$", na=False)].copy()
    m2 = m[m[tcol].str.match(r"^\d{6}$", na=False)].copy()

    # 3) 현재 상장 마스터에 존재하는 종목만 남기기
    u_clean = u2.merge(m2[[tcol]].drop_duplicates(), on=tcol, how="inner")

    # 4) 저장
    if args.univ_out.strip():
        univ_out = Path(args.univ_out)
    else:
        univ_out = univ_in.with_name(univ_in.stem + "_clean.csv")

    univ_out.parent.mkdir(parents=True, exist_ok=True)
    u_clean.to_csv(univ_out, index=False, encoding="utf-8-sig")

    print("IN :", univ_in, "rows=", len(u))
    print("AFTER format(6digits):", len(u2))
    print("OUT:", univ_out, "rows=", len(u_clean))


if __name__ == "__main__":
    main()
