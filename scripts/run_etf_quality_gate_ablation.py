from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_etf_role_allocation_ai_v01_experiment import (
    MODEL_CODE,
    QUALITY_GATE_CONFIGS,
    REPORT_DIR,
    run_experiment as run_role_experiment,
)
from scripts.run_etf_role_weight_template_ai_v01_experiment import (
    TEMPLATE_MODEL_CODE,
    run_experiment as run_template_experiment,
)

DOC_PATH = ROOT / r"docs\AI_ETF_QUALITY_GATE_ABLATION_20260511.md"
DEFAULT_GATES = [
    "none",
    "no_wide_extreme",
    "no_watch_plus",
    "aum_p20",
    "tracking_gap_p90",
    "quality_combo",
    "strict_quality",
]


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _policy(payload: dict[str, Any], policy_name: str) -> dict[str, Any]:
    for row in payload.get("policy_summary", []):
        if row.get("policy") == policy_name:
            return row
    return {}


def _pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value) * 100:.2f}%"


def _write_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame) -> None:
    lines = [
        "# ETF Quality Gate Ablation",
        "",
        "## 목적",
        "",
        "ETF 전용 NAV/AUM/괴리율/tracking gap 데이터를 raw feature로 직접 넣는 대신, sleeve 후보를 거르는 quality gate로 썼을 때 성능이 개선되는지 검증한다.",
        "",
        "## 기준 조합",
        "",
        f"- role model: `{MODEL_CODE}`",
        f"- template model: `{TEMPLATE_MODEL_CODE}`",
        f"- as-of: `{payload['as_of_date']}`",
        f"- train end: `{payload['train_end']}`",
        f"- valid start: `{payload['valid_start']}`",
        f"- top N: `{payload['top_n']}`",
        f"- label: `{payload['label']}`",
        f"- regime map: `{payload['regime_map']}`",
        f"- selection mode: `{payload['selection_mode']}`",
        "",
        "## 결과",
        "",
        "| gate | role AUC | AI role risk adj | AI role worst | template AUC | AI template risk adj | AI template worst |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.to_dict("records"):
        lines.append(
            f"| `{row['quality_gate']}` | {row['role_auc']:.6f} | {_pct(row['role_ai_top1_risk_adj'])} | "
            f"{_pct(row['role_ai_top1_worst_1m'])} | {row['template_auc']:.6f} | "
            f"{_pct(row['template_ai_top1_risk_adj'])} | {_pct(row['template_ai_top1_worst_1m'])} |"
        )
    best_role = summary.sort_values("role_ai_top1_risk_adj", ascending=False).iloc[0].to_dict()
    best_template = summary.sort_values("template_ai_top1_risk_adj", ascending=False).iloc[0].to_dict()
    lines.extend(
        [
            "",
            "## 판단",
            "",
            f"- 역할 선택 기준 best gate: `{best_role['quality_gate']}`",
            f"  - AI role avg risk adj: `{_pct(best_role['role_ai_top1_risk_adj'])}`",
            f"  - AI role worst 1M: `{_pct(best_role['role_ai_top1_worst_1m'])}`",
            f"- 비중 템플릿 기준 best gate: `{best_template['quality_gate']}`",
            f"  - AI template avg risk adj: `{_pct(best_template['template_ai_top1_risk_adj'])}`",
            f"  - AI template worst 1M: `{_pct(best_template['template_ai_top1_worst_1m'])}`",
            "",
            "## Gate 정의",
            "",
        ]
    )
    for gate in payload["quality_gates"]:
        lines.append(f"- `{gate}`: {QUALITY_GATE_CONFIGS[gate]}")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- `{payload['outputs']['csv']}`",
            f"- `{payload['outputs']['json']}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_ablation(
    asof: str,
    train_end: str,
    valid_start: str,
    top_n: int,
    label: str,
    regime_map: str,
    selection_mode: str,
    quality_gates: list[str],
    rebuild_mart: bool,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for gate in quality_gates:
        if gate not in QUALITY_GATE_CONFIGS:
            raise SystemExit(f"unknown quality gate: {gate}")
        role_payload = run_role_experiment(
            asof=asof,
            train_end=train_end,
            valid_start=valid_start,
            top_n=top_n,
            label_key=label,
            regime_map=regime_map,
            selection_mode=selection_mode,
            quality_gate=gate,
            rebuild_mart=rebuild_mart,
        )
        template_payload = run_template_experiment(
            asof=asof,
            train_end=train_end,
            valid_start=valid_start,
            top_n=top_n,
            regime_map=regime_map,
            selection_mode=selection_mode,
            quality_gate=gate,
            rebuild_mart=False,
        )
        role_ai = _policy(role_payload, "ai_top1_role")
        role_rule = _policy(role_payload, "rule_mode_weight")
        role_oracle = _policy(role_payload, "oracle_best_role")
        template_ai = _policy(template_payload, "ai_top1_template")
        template_default = _policy(template_payload, "mode_default_template")
        template_oracle = _policy(template_payload, "oracle_best_template")
        rows.append(
            {
                "quality_gate": gate,
                "quality_gate_description": QUALITY_GATE_CONFIGS[gate],
                "role_auc": _safe_float(role_payload.get("auc")),
                "role_top_pick_label_rate": _safe_float(role_payload.get("top_pick_label_rate")),
                "role_sleeve_rows": role_payload.get("sleeve_rows"),
                "role_ai_top1_ret": _safe_float(role_ai.get("avg_1m_ret")),
                "role_ai_top1_risk_adj": _safe_float(role_ai.get("avg_1m_risk_adj")),
                "role_ai_top1_worst_1m": _safe_float(role_ai.get("worst_1m_ret")),
                "role_rule_ret": _safe_float(role_rule.get("avg_1m_ret")),
                "role_rule_risk_adj": _safe_float(role_rule.get("avg_1m_risk_adj")),
                "role_oracle_risk_adj": _safe_float(role_oracle.get("avg_1m_risk_adj")),
                "template_auc": _safe_float(template_payload.get("auc_best_template")),
                "template_top_pick_hit_rate": _safe_float(template_payload.get("top_pick_hit_rate")),
                "template_ai_top1_ret": _safe_float(template_ai.get("avg_1m_ret")),
                "template_ai_top1_risk_adj": _safe_float(template_ai.get("avg_1m_risk_adj")),
                "template_ai_top1_worst_1m": _safe_float(template_ai.get("worst_1m_ret")),
                "template_default_ret": _safe_float(template_default.get("avg_1m_ret")),
                "template_default_risk_adj": _safe_float(template_default.get("avg_1m_risk_adj")),
                "template_oracle_risk_adj": _safe_float(template_oracle.get("avg_1m_risk_adj")),
                "role_json": role_payload.get("outputs", {}).get("json"),
                "template_json": template_payload.get("outputs", {}).get("json"),
            }
        )

    summary = pd.DataFrame(rows)
    token = asof.replace("-", "")
    suffix = f"{token}_top{top_n}_{label}_{regime_map}_{selection_mode}"
    csv_path = REPORT_DIR / f"etf_quality_gate_ablation_{suffix}.csv"
    json_path = REPORT_DIR / f"etf_quality_gate_ablation_{suffix}.json"
    md_path = REPORT_DIR / f"etf_quality_gate_ablation_{suffix}.md"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(csv_path, index=False, encoding="utf-8-sig")
    payload = {
        "source_name": "etf_quality_gate_ablation",
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "train_end": train_end,
        "valid_start": valid_start,
        "top_n": top_n,
        "label": label,
        "regime_map": regime_map,
        "selection_mode": selection_mode,
        "quality_gates": quality_gates,
        "rows": json.loads(summary.replace({np.nan: None}).to_json(orient="records", force_ascii=False)),
        "outputs": {
            "csv": str(csv_path),
            "json": str(json_path),
            "md": str(md_path),
            "doc": str(DOC_PATH),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, payload, summary)
    _write_markdown(DOC_PATH, payload, summary)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ETF quality gate ablation.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--label", default="horizon_v2_top1")
    parser.add_argument("--regime-map", default="score_diff")
    parser.add_argument("--selection-mode", default="risk_adjusted")
    parser.add_argument("--quality-gates", nargs="*", default=DEFAULT_GATES, choices=sorted(QUALITY_GATE_CONFIGS))
    parser.add_argument("--rebuild-mart", action="store_true")
    args = parser.parse_args()
    payload = run_ablation(
        asof=args.asof,
        train_end=args.train_end,
        valid_start=args.valid_start,
        top_n=args.top_n,
        label=args.label,
        regime_map=args.regime_map,
        selection_mode=args.selection_mode,
        quality_gates=args.quality_gates,
        rebuild_mart=args.rebuild_mart,
    )
    summary = pd.DataFrame(payload["rows"])
    best_role = summary.sort_values("role_ai_top1_risk_adj", ascending=False).iloc[0]
    best_template = summary.sort_values("template_ai_top1_risk_adj", ascending=False).iloc[0]
    print(
        json.dumps(
            {
                "status": "ok",
                "as_of_date": args.asof,
                "best_role_gate": best_role["quality_gate"],
                "best_role_risk_adj": best_role["role_ai_top1_risk_adj"],
                "best_template_gate": best_template["quality_gate"],
                "best_template_risk_adj": best_template["template_ai_top1_risk_adj"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
