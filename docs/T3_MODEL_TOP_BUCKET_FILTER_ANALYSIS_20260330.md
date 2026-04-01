# T3 Model Top-Bucket Filter Analysis (2026-03-30)

## Purpose
- Keep both Top10% and Top3% buckets for research.
- Add Top30% and Top50% buckets for broader sector/group analysis.
- Define a research-only `T3 model score` from Top3-entry characteristics and test whether it captures future high-performance groups.

## T3 model score definition
The T3 model score is a research score built from the signals that appeared around Top3 entry starts.

- Positive block:
  - revenue_yoy_pct
  - op_income_yoy_pct
  - fund_accel_score_pct
  - rev_delta_3m_pct
  - op_delta_3m_pct
  - ma_stack_gap_pct
- Crowdedness penalty:
  - mom20_pct
  - dist_ma60_pct
  - breakout60

Formula:
- t3_positive_score = mean(positive block)
- t3_crowded_score = mean(mom20_pct, dist_ma60_pct)
- t3_model_score = t3_positive_score - 0.35 * t3_crowded_score - 0.05 * breakout60

This is a discovery/research score, not a production portfolio score.

## Built tables
Stored in [model_research.db](D:/Quant/data/db/model_research.db):
- universe_top_3pct_candidates
- universe_top_3pct_summary
- universe_top_10pct_candidates
- universe_top_10pct_summary
- universe_top_30pct_candidates
- universe_top_30pct_summary
- universe_top_50pct_candidates
- universe_top_50pct_summary
- t3_model_filter_panel
- t3_model_filter_capture_summary
- t3_model_filter_capture_examples

## Bucket sizes
- Top10% summary: 2661 rows / 391 unique tickers
- Top30% summary: 3234 rows / 398 unique tickers
- Top50% summary: 3391 rows / 399 unique tickers

## Market split
- Top30%: KOSPI 200 / KOSDAQ 198
- Top50%: KOSPI 200 / KOSDAQ 199

## Interpretation
1. Yes, the T3 model does capture future high-performance names.
2. The capture quality is better in S3 horizons than in S2.
3. The lift is positive, but not dramatically high yet.
4. This means the T3 score is usable as a discovery signal, but it is not yet a standalone final ranking model.

## Best observed capture cases
- S3 6M: T3 Top10% filter vs actual Top10% group
  - precision ~11.37%
  - recall ~11.14%
  - precision lift ~1.12x
- S3 6M: T3 Top30% filter vs actual Top10% group
  - recall ~32.95%
- S3 1Y: T3 Top50% filter vs actual Top10% group
  - recall ~52.14%

## Practical use
- Main elite research group: Top3%
- Broad expansion group: Top10%
- Sector/group exploration: Top30% and Top50%
- T3 score should be used first as a discovery/filter signal, then combined with model-specific ranking logic.
