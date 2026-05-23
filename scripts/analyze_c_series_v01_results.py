from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(r"D:\Quant")
C_DB = ROOT / r"data\db\cseries_relationship.db"
REPORT_DIR = ROOT / r"reports\c_series"


def _rows(con: sqlite3.Connection, query: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    return con.execute(query, params).fetchall()


def _table(rows: list[tuple[Any, ...]], headers: list[str]) -> list[str]:
    if not rows:
        return ["_No rows._"]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join("" if value is None else str(value) for value in row) + " |")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description="Write C-series V01 interpretation and negative-relation diagnostic report.")
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()
    asof = args.asof
    token = asof.replace("-", "")

    con = sqlite3.connect(str(C_DB))
    try:
        quality_rows = _rows(
            con,
            """
            SELECT asset_type, data_quality_flag, COUNT(*)
            FROM c_return_series
            WHERE asof_date = ?
            GROUP BY asset_type, data_quality_flag
            ORDER BY asset_type, data_quality_flag
            """,
            (asof,),
        )
        edge_rows = _rows(
            con,
            """
            SELECT source_type, target_type, relation_type, COUNT(*)
            FROM c_relationship_edges
            WHERE asof_date = ?
            GROUP BY source_type, target_type, relation_type
            ORDER BY source_type, target_type, relation_type
            """,
            (asof,),
        )
        relation_counts = dict(
            _rows(
                con,
                """
                SELECT relation_type, COUNT(*)
                FROM c_relationship_edges
                WHERE asof_date = ?
                GROUP BY relation_type
                ORDER BY relation_type
                """,
                (asof,),
            )
        )
        overlay_rows = _rows(
            con,
            """
            SELECT scope, relationship_status, COUNT(*)
            FROM c_model_overlay_scores
            WHERE asof_date = ?
            GROUP BY scope, relationship_status
            ORDER BY scope, relationship_status
            """,
            (asof,),
        )
        positive_top = _rows(
            con,
            """
            SELECT source_name, target_name, target_type, ROUND(corr_60d, 4), persistence_days,
                   ROUND(persistence_ratio_120d, 4), ROUND(relationship_confidence_score, 4)
            FROM c_relationship_edges
            WHERE asof_date = ? AND relation_type = 'Positive'
            ORDER BY relationship_confidence_score DESC
            LIMIT 12
            """,
            (asof,),
        )
        negative_top = _rows(
            con,
            """
            SELECT source_name, target_name, target_type, ROUND(corr_60d, 4), persistence_days,
                   ROUND(persistence_ratio_120d, 4), ROUND(relationship_confidence_score, 4)
            FROM c_relationship_edges
            WHERE asof_date = ? AND relation_type = 'Negative'
            ORDER BY relationship_confidence_score DESC
            LIMIT 12
            """,
            (asof,),
        )
        overlay_top = _rows(
            con,
            """
            SELECT scope, base_model_code, ticker, name, relationship_status,
                   ROUND(c_overlay_score, 4), top_positive_etf, top_market_beta_proxy, top_negative_etf
            FROM c_model_overlay_scores
            WHERE asof_date = ?
            ORDER BY c_overlay_score DESC
            LIMIT 15
            """,
            (asof,),
        )
        insufficient_rows = _rows(
            con,
            """
            SELECT ticker, name, asset_type, data_quality_flag
            FROM c_return_series
            WHERE asof_date = ? AND data_quality_flag != 'ok'
            ORDER BY asset_type, ticker
            """,
            (asof,),
        )
    finally:
        con.close()

    total_edges = sum(relation_counts.values())
    negative_count = int(relation_counts.get("Negative", 0))
    negative_ratio = round((negative_count / total_edges) * 100, 2) if total_edges else 0.0

    summary = {
        "asof_date": asof,
        "total_edges": total_edges,
        "relation_counts": relation_counts,
        "negative_ratio_pct": negative_ratio,
        "quality_rows": quality_rows,
        "overlay_rows": overlay_rows,
        "insufficient_rows": insufficient_rows,
    }

    lines: list[str] = [
        "# C-series V01 Interpretation and Negative Diagnostic",
        "",
        f"- asof_date: {asof}",
        f"- total_edges: {total_edges}",
        f"- relation_counts: {relation_counts}",
        f"- negative_ratio_pct: {negative_ratio}",
        "",
        "## 1. Executive Interpretation",
        "",
        "- C-series V01 now works as a relationship layer over the full stock/ETF universe, not only over S/T selected names.",
        "- The model mainly captures strong market-beta and theme co-movement relationships, while also identifying hedge-like negative relationships through inverse/leveraged ETFs.",
        "- S/T overlay output is still shadow-only. It does not replace holdings or change model portfolios.",
        "",
        "## 2. Data Coverage",
        "",
        *_table(quality_rows, ["asset_type", "data_quality_flag", "count"]),
        "",
        "Insufficient history names:",
        "",
        *_table(insufficient_rows, ["ticker", "name", "asset_type", "flag"]),
        "",
        "## 3. Relationship Counts",
        "",
        *_table(edge_rows, ["source_type", "target_type", "relation_type", "count"]),
        "",
        "## 4. Top Positive Relationships",
        "",
        *_table(
            positive_top,
            ["source", "target", "target_type", "corr60", "persistence_days", "persistence_ratio", "confidence"],
        ),
        "",
        "## 5. Top Negative Relationships",
        "",
        *_table(
            negative_top,
            ["source", "target", "target_type", "corr60", "persistence_days", "persistence_ratio", "confidence"],
        ),
        "",
        "## 6. S/T Overlay Summary",
        "",
        *_table(overlay_rows, ["scope", "relationship_status", "count"]),
        "",
        "Top overlay names:",
        "",
        *_table(
            overlay_top,
            ["scope", "model", "ticker", "name", "status", "overlay", "thematic_pos", "market_beta", "negative"],
        ),
        "",
        "## 7. Negative Relation Diagnostic",
        "",
        "- Initial DB output showed no Negative relationships because the previous build used the global latest date row for `daily_return` quality filtering.",
        "- On 2026-04-21, stock prices had a newer latest row than most ETF prices. That made 873 assets, mostly ETFs including inverse ETFs, look like they had missing latest returns.",
        "- Since inverse ETFs were excluded by that filter, the model could not store negative stock-ETF relationships even though raw rolling correlations contained them.",
        "- The build now uses each ticker's latest valid return history and a minimum observation count filter. After the fix, Negative edges are generated normally.",
        "- Current Negative relationships are dominated by explicit inverse ETF hedge relationships. This is valid, but should be interpreted separately from organic negative relationships between ordinary themes.",
        "- Theme-theme relationships still show almost no Negative edges because theme baskets are broad averages and share common market beta. For pure hedge discovery, inverse ETF and asset-theme negative edges are more informative than theme-theme edges.",
        "",
        "## 8. Next Operating Notes",
        "",
        "- Keep `top_positive_etf` and `top_market_beta_proxy` separate so broad-market beta is not mistaken for thematic support.",
        "- Add a freshness gate that reports latest available price date by asset type, especially stock vs ETF.",
        "- Track explicit inverse/leveraged hedge relationships separately from ordinary negative relationships.",
        "- Use this report as the baseline for 4-8 week shadow tracking before allowing C overlay to influence S/T candidate ranking.",
        "",
    ]

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORT_DIR / f"c_series_v01_interpretation_diagnostic_{token}.md"
    json_path = REPORT_DIR / f"c_series_v01_interpretation_diagnostic_{token}.json"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "report": str(md_path), "summary": str(json_path), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
