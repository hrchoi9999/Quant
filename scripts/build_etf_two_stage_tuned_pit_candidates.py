from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

PROJECT_ROOT = Path(r"D:\Quant")
TRANSITION_PATH = PROJECT_ROOT / r"reports\model_upgrade_research\20260401\ETF_T_SERIES_PIT_BACKFILL_V1\etf_tseries_pit_transition_panel.csv"
FEATURE_PATH = PROJECT_ROOT / r"reports\model_upgrade_research\20260401\ETF_T_SERIES_PIT_BACKFILL_V1\etf_tseries_pit_feature_panel.csv"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260401\ETF_TWO_STAGE_DISCOVERY_TUNED_PIT"
OUTDIR.mkdir(parents=True, exist_ok=True)

CAT_FEATURES = ["asset_class", "group_key", "currency_exposure"]
LOWER_BUCKETS = ["OUTSIDE", "ET50_ex_ET30", "ET30_ex_ET10"]
STAGE1_FEATURES = ["ret_60d","ret_120d","ret_240d","dist_ma60","dist_ma120","ma20_ma60_gap","ma60_ma120_gap","rsi20"]
STAGE2_FEATURES = ["vol_20d","vol_60d","dist_ma20","dist_ma60","dist_ma120","ma20_ma60_gap","ma60_ma120_gap"]
STAGE1_TOP_RATIO = 0.08
STAGE2_CONF_THRESHOLD = 0.65
STAGE2_NEAR_THRESHOLD = 0.60
LATEST_SIGNAL_DATE = "2026-03-25"


def build_pipeline(num_features: list[str]) -> Pipeline:
    pre = ColumnTransformer([
        ("num", StandardScaler(), num_features),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
    ])
    clf = LogisticRegression(max_iter=2000, class_weight="balanced")
    return Pipeline([("pre", pre), ("clf", clf)])


def main() -> None:
    trans = pd.read_csv(TRANSITION_PATH, dtype={"ticker": str})
    trans["ticker"] = trans["ticker"].astype(str).str.zfill(6)
    trans["signal_date"] = pd.to_datetime(trans["signal_date"])
    features = pd.read_csv(FEATURE_PATH, dtype={"ticker": str})
    features["ticker"] = features["ticker"].astype(str).str.zfill(6)
    features["signal_date"] = pd.to_datetime(features["signal_date"])

    latest = features[features["signal_date"] == pd.Timestamp(LATEST_SIGNAL_DATE)].copy()

    stage1_panel = trans[trans["current_bucket"].isin(LOWER_BUCKETS)].copy()
    stage1_panel = stage1_panel.dropna(subset=STAGE1_FEATURES)
    stage1_panel["label"] = stage1_panel["label_to_et10"].astype(int)
    s1_model = build_pipeline(STAGE1_FEATURES)
    s1_model.fit(stage1_panel[STAGE1_FEATURES + CAT_FEATURES], stage1_panel["label"])

    latest_s1 = latest.dropna(subset=STAGE1_FEATURES).copy()
    latest_s1["stage1_prob"] = s1_model.predict_proba(latest_s1[STAGE1_FEATURES + CAT_FEATURES])[:, 1]
    latest_s1 = latest_s1.sort_values(["stage1_prob", "ticker"], ascending=[False, True]).reset_index(drop=True)
    stage1_n = max(1, int(math.ceil(len(latest_s1) * STAGE1_TOP_RATIO)))
    stage1_candidates = latest_s1.head(stage1_n).copy()

    stage2_panel = trans[trans["current_bucket"] == "ET10_ex_ET3"].copy()
    stage2_panel = stage2_panel.dropna(subset=STAGE2_FEATURES)
    stage2_panel["label"] = stage2_panel["label_to_et3"].astype(int)
    s2_model = build_pipeline(STAGE2_FEATURES)
    s2_model.fit(stage2_panel[STAGE2_FEATURES + CAT_FEATURES], stage2_panel["label"])

    stage2_input = stage1_candidates.dropna(subset=STAGE2_FEATURES).copy()
    stage2_input["stage2_prob"] = s2_model.predict_proba(stage2_input[STAGE2_FEATURES + CAT_FEATURES])[:, 1]
    stage2_input = stage2_input.sort_values(["stage2_prob", "stage1_prob", "ticker"], ascending=[False, False, True]).reset_index(drop=True)

    confirmed = stage2_input[stage2_input["stage2_prob"] >= STAGE2_CONF_THRESHOLD].copy()
    near = stage2_input[(stage2_input["stage2_prob"] >= STAGE2_NEAR_THRESHOLD) & (stage2_input["stage2_prob"] < STAGE2_CONF_THRESHOLD)].copy()

    summary = pd.DataFrame([
        {
            "stage1_feature_set": "momentum_trend",
            "stage1_selection": f"top_ratio={STAGE1_TOP_RATIO}",
            "stage2_feature_set": "vol_trend_compact",
            "stage2_confirmed_rule": f"threshold>={STAGE2_CONF_THRESHOLD}",
            "stage2_near_rule": f"{STAGE2_NEAR_THRESHOLD}<=threshold<{STAGE2_CONF_THRESHOLD}",
            "latest_universe_n": len(latest_s1),
            "latest_stage1_n": len(stage1_candidates),
            "latest_confirmed_n": len(confirmed),
            "latest_near_n": len(near),
        }
    ])

    latest_s1.to_csv(OUTDIR / 'etf_two_stage_tuned_pit_full_rank_2026-03-31.csv', index=False, encoding='utf-8-sig')
    stage1_candidates.to_csv(OUTDIR / 'etf_two_stage_tuned_pit_stage1_candidates_2026-03-31.csv', index=False, encoding='utf-8-sig')
    confirmed.to_csv(OUTDIR / 'etf_two_stage_tuned_pit_stage2_confirmed_2026-03-31.csv', index=False, encoding='utf-8-sig')
    near.to_csv(OUTDIR / 'etf_two_stage_tuned_pit_stage2_near_2026-03-31.csv', index=False, encoding='utf-8-sig')
    summary.to_csv(OUTDIR / 'etf_two_stage_tuned_pit_summary_2026-03-31.csv', index=False, encoding='utf-8-sig')

    lines = [
        '# ETF Two-Stage Discovery Tuned PIT',
        '',
        '- stage1 model: momentum_trend',
        f'- stage1 rule: top {STAGE1_TOP_RATIO:.0%} of latest PIT universe',
        '- stage2 model: vol_trend_compact',
        f'- confirmed rule: stage2_prob >= {STAGE2_CONF_THRESHOLD:.2f}',
        f'- near rule: {STAGE2_NEAR_THRESHOLD:.2f} <= stage2_prob < {STAGE2_CONF_THRESHOLD:.2f}',
        '',
        f'- stage1 candidates: {len(stage1_candidates)}',
        f'- stage2 confirmed: {len(confirmed)}',
        f'- stage2 near: {len(near)}',
    ]
    (OUTDIR / 'etf_two_stage_tuned_pit_2026-03-31.md').write_text('\n'.join(lines), encoding='utf-8')

    print(summary.to_string(index=False))
    print('confirmed=' + ','.join(confirmed['name'].astype(str).tolist()))
    print('near=' + ','.join(near['name'].astype(str).tolist()))


if __name__ == '__main__':
    main()
