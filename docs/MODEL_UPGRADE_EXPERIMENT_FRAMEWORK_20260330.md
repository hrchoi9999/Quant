# Model Upgrade Experiment Framework

### 1. Scope
This framework is for stock-model upgrade experiments focused on:
- S2
- S3
- S3 Core2

### 2. Evaluation layers
#### Layer A. Universe-relative stock-selection test
Compare:
- selected names
- not-selected names
inside the same universe.

Primary horizons:
- 3M
- 6M
- 1Y

Metrics:
- average forward return
- median forward return
- average path MDD
- median path MDD
- return delta = selected minus not-selected
- MDD delta = selected minus not-selected

#### Layer B. Portfolio-level model test
Compare the actual portfolio result using:
- 3M
- 6M
- 1Y
- 2Y
- 3Y

Metrics:
- CAGR
- MDD
- Sharpe
- total return
- turnover
- rebalance count

### 3. Interpretation rules
- Layer A tells us whether stock selection is improving.
- Layer B tells us whether the model as a portfolio is improving.
- A candidate should not be promoted if Layer A stays weak, even if a short portfolio window looks better by chance.

### 4. Standard output files
Recommended per experiment:
- reports/model_upgrade_research/<stamp>/<experiment_id>_selection_summary.csv
- reports/model_upgrade_research/<stamp>/<experiment_id>_selection_detail.csv
- reports/model_upgrade_research/<stamp>/<experiment_id>_portfolio_summary.csv
- reports/model_upgrade_research/<stamp>/<experiment_id>_review.md

### 5. Registry fields
Each experiment entry should define:
- experiment_id
- model_code
- priority
- status
- objective
- hypothesis
- knobs
- success_rules

### 6. Initial governance
- Do not replace production models from one result alone.
- Require repeated horizon improvement and a written review note.
- Treat S2 and S3 Core2 as redesign targets, S3 as risk-adjustment target.
