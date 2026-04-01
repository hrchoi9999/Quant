from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_BUCKET_TRANSITION_RESEARCH"
DOC_PATH = PROJECT_ROOT / r"docs\S3_BUCKET_TRANSITION_RESEARCH_PLAN_20260331.md"


def read_sql(con: sqlite3.Connection, query: str, parse_dates=None) -> pd.DataFrame:
    return pd.read_sql_query(query, con, parse_dates=parse_dates)


def build_panel(con: sqlite3.Connection) -> pd.DataFrame:
    base = read_sql(
        con,
        """
        SELECT model_code, horizon, signal_date, end_date, ticker, name, market,
               selected, score, fwd_ret, path_mdd, top_50pct_flag
        FROM universe_top_50pct_candidates
        WHERE model_code='S3'
        """,
        parse_dates=["signal_date", "end_date"],
    )
    t3 = read_sql(con, "SELECT model_code, horizon, signal_date, end_date, ticker, top_3pct_flag FROM universe_top_3pct_candidates WHERE model_code='S3'", parse_dates=["signal_date", "end_date"])
    t10 = read_sql(con, "SELECT model_code, horizon, signal_date, end_date, ticker, top_10pct_flag FROM universe_top_10pct_candidates WHERE model_code='S3'", parse_dates=["signal_date", "end_date"])
    t30 = read_sql(con, "SELECT model_code, horizon, signal_date, end_date, ticker, top_30pct_flag FROM universe_top_30pct_candidates WHERE model_code='S3'", parse_dates=["signal_date", "end_date"])
    for df in (base, t3, t10, t30):
        df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    keys = ["model_code", "horizon", "signal_date", "end_date", "ticker"]
    panel = base.merge(t3, on=keys, how="left").merge(t10, on=keys, how="left").merge(t30, on=keys, how="left")
    for c in ["top_3pct_flag", "top_10pct_flag", "top_30pct_flag", "top_50pct_flag", "selected"]:
        panel[c] = pd.to_numeric(panel[c], errors="coerce").fillna(0).astype(int)
    panel["bucket"] = "OUTSIDE"
    panel.loc[(panel["top_50pct_flag"] == 1) & (panel["top_30pct_flag"] == 0), "bucket"] = "T50_ex_T30"
    panel.loc[(panel["top_30pct_flag"] == 1) & (panel["top_10pct_flag"] == 0), "bucket"] = "T30_ex_T10"
    panel.loc[(panel["top_10pct_flag"] == 1) & (panel["top_3pct_flag"] == 0), "bucket"] = "T10_ex_T3"
    panel.loc[panel["top_3pct_flag"] == 1, "bucket"] = "T3"
    panel = panel.sort_values(["horizon", "ticker", "signal_date"]).reset_index(drop=True)
    return panel


def build_transitions(panel: pd.DataFrame) -> pd.DataFrame:
    gcols = ["horizon", "ticker"]
    panel = panel.copy()
    panel["next_signal_date"] = panel.groupby(gcols)["signal_date"].shift(-1)
    panel["next_bucket"] = panel.groupby(gcols)["bucket"].shift(-1)
    panel["next_fwd_ret"] = panel.groupby(gcols)["fwd_ret"].shift(-1)
    panel["next_path_mdd"] = panel.groupby(gcols)["path_mdd"].shift(-1)
    panel["entered_t3_next"] = panel["next_bucket"].eq("T3").astype(int)
    panel["entered_t10_next"] = panel["next_bucket"].isin(["T3", "T10_ex_T3"]).astype(int)
    return panel


def summarize_transitions(transitions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    valid = transitions[transitions["next_bucket"].notna()].copy()
    matrix = (
        valid.groupby(["horizon", "bucket", "next_bucket"], as_index=False)
        .agg(obs_count=("ticker", "size"), unique_tickers=("ticker", "nunique"), avg_next_ret=("next_fwd_ret", "mean"), avg_next_mdd=("next_path_mdd", "mean"))
    )
    totals = valid.groupby(["horizon", "bucket"], as_index=False).agg(bucket_obs=("ticker", "size"))
    matrix = matrix.merge(totals, on=["horizon", "bucket"], how="left")
    matrix["transition_rate"] = matrix["obs_count"] / matrix["bucket_obs"]

    t3prob = (
        valid.groupby(["horizon", "bucket"], as_index=False)
        .agg(
            obs_count=("ticker", "size"),
            unique_tickers=("ticker", "nunique"),
            next_t3_prob=("entered_t3_next", "mean"),
            next_t10_prob=("entered_t10_next", "mean"),
            avg_curr_ret=("fwd_ret", "mean"),
            avg_curr_mdd=("path_mdd", "mean"),
            avg_next_ret=("next_fwd_ret", "mean"),
            avg_next_mdd=("next_path_mdd", "mean"),
        )
    )

    t3_hits = transitions[transitions["bucket"] == "T3"].copy()
    first_t3 = t3_hits.sort_values(["horizon", "ticker", "signal_date"]).groupby(["horizon", "ticker"], as_index=False).head(1)
    examples = []
    for r in first_t3.itertuples(index=False):
        hist = transitions[(transitions["horizon"] == r.horizon) & (transitions["ticker"] == r.ticker) & (transitions["signal_date"] <= r.signal_date)].sort_values("signal_date").tail(5)
        path = " -> ".join(hist["bucket"].tolist())
        examples.append({
            "horizon": r.horizon,
            "ticker": r.ticker,
            "name": r.name,
            "market": r.market,
            "first_t3_date": r.signal_date,
            "path_last_5": path,
            "curr_fwd_ret": r.fwd_ret,
            "curr_path_mdd": r.path_mdd,
        })
    examples_df = pd.DataFrame(examples).sort_values(["horizon", "first_t3_date", "ticker"]).reset_index(drop=True)
    return matrix, t3prob, examples_df


def upsert_tables(con: sqlite3.Connection, panel: pd.DataFrame, matrix: pd.DataFrame, t3prob: pd.DataFrame, examples_df: pd.DataFrame) -> None:
    panel.to_sql("s3_bucket_transition_panel", con, if_exists="replace", index=False)
    matrix.to_sql("s3_bucket_transition_matrix", con, if_exists="replace", index=False)
    t3prob.to_sql("s3_bucket_transition_prob_summary", con, if_exists="replace", index=False)
    examples_df.to_sql("s3_bucket_t3_path_examples", con, if_exists="replace", index=False)


def write_doc() -> None:
    text = """# S3 Bucket Transition Research Plan

## 목적

정적인 T3/T10/T30/T50 특성 분석을 넘어서, 종목이 `universe` 안에서 어떤 전이 과정을 거쳐 `T3`까지 올라가는지 관찰한다.

핵심 질문:

1. 종목은 `OUTSIDE -> T50_ex_T30 -> T30_ex_T10 -> T10_ex_T3 -> T3`로 실제로 이동하는가
2. 각 그룹에서 다음 시점에 상위 그룹으로 이동할 확률은 얼마인가
3. `T3`까지 올라간 종목들은 직전 3~5개 시점에서 어떤 경로를 밟는가
4. 이 전이 히스토리를 기반으로 새로운 discovery 모델을 만들 수 있는가

## 전이 상태 정의

- `OUTSIDE`: top 50% 밖
- `T50_ex_T30`: 30~50%
- `T30_ex_T10`: 10~30%
- `T10_ex_T3`: 3~10%
- `T3`: 0~3%

## 이번 산출물

- `s3_bucket_transition_panel`
- `s3_bucket_transition_matrix`
- `s3_bucket_transition_prob_summary`
- `s3_bucket_t3_path_examples`

모두 `D:\\Quant\\data\\db\\model_research.db`에 저장한다.

## 해석 원칙

- 이번 연구는 `S3`와 동일한 universe, 동일한 future-label 구조 안에서 본다.
- `T%`는 실제 시장 데이터 기반 사후 라벨이며, 포트폴리오 백테스트가 아니라 종목 단위 정답지다.
- 따라서 전이 확률은 `미래 상위 그룹 진입 가능성` 연구에 사용한다.
"""
    DOC_PATH.write_text(text, encoding="utf-8")


def render_md(matrix: pd.DataFrame, t3prob: pd.DataFrame, examples_df: pd.DataFrame) -> str:
    lines = ["# S3 Bucket Transition Research", ""]
    lines.append("## Next-step probabilities")
    lines.append("| Horizon | Bucket | Next T3 Prob | Next Top10 Prob | Avg Current Return | Avg Next Return |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for r in t3prob.sort_values(["horizon", "bucket"]).itertuples(index=False):
        lines.append(f"| {r.horizon} | {r.bucket} | {r.next_t3_prob:.2%} | {r.next_t10_prob:.2%} | {r.avg_curr_ret:.2%} | {r.avg_next_ret:.2%} |")
    lines.append("")
    lines.append("## Selected transition matrix rows")
    lines.append("| Horizon | From | To | Transition Rate | Obs | Avg Next Return |")
    lines.append("|---|---|---|---:|---:|---:|")
    for r in matrix.sort_values(["horizon", "bucket", "transition_rate"], ascending=[True, True, False]).groupby(["horizon", "bucket"]).head(3).itertuples(index=False):
        lines.append(f"| {r.horizon} | {r.bucket} | {r.next_bucket} | {r.transition_rate:.2%} | {r.obs_count} | {r.avg_next_ret:.2%} |")
    lines.append("")
    lines.append("## Example first-T3 paths")
    lines.append("| Horizon | Ticker | Name | First T3 Date | Path (last 5 states) |")
    lines.append("|---|---|---|---|---|")
    for r in examples_df.head(20).itertuples(index=False):
        lines.append(f"| {r.horizon} | {r.ticker} | {r.name} | {pd.to_datetime(r.first_t3_date).date()} | {r.path_last_5} |")
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    write_doc()
    con = sqlite3.connect(str(RESEARCH_DB))
    try:
        panel = build_panel(con)
        transitions = build_transitions(panel)
        matrix, t3prob, examples_df = summarize_transitions(transitions)
        upsert_tables(con, transitions, matrix, t3prob, examples_df)
    finally:
        con.close()

    transitions.to_csv(OUTDIR / "s3_bucket_transition_panel.csv", index=False, encoding="utf-8-sig")
    matrix.to_csv(OUTDIR / "s3_bucket_transition_matrix.csv", index=False, encoding="utf-8-sig")
    t3prob.to_csv(OUTDIR / "s3_bucket_transition_prob_summary.csv", index=False, encoding="utf-8-sig")
    examples_df.to_csv(OUTDIR / "s3_bucket_t3_path_examples.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "s3_bucket_transition_research.md").write_text(render_md(matrix, t3prob, examples_df), encoding="utf-8")

    print("TRANSITION_PROB")
    print(t3prob.sort_values(["horizon", "bucket"]).to_string(index=False))
    print("\nEXAMPLES")
    print(examples_df.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
