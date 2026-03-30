# Model Upgrade Research Roadmap
## (Universe Relative 3M / 6M / 1Y Improvement Program)

### 1. Purpose
The first upgrade axis is to improve stock-selection models so that, within each model's own universe, selected names outperform non-selected names on the horizons that matter to our design intent.

Primary comparison horizons:
- 3M
- 6M
- 1Y

Primary comparison frame:
- selected names vs not-selected names inside the same universe
- evaluate both return and path MDD

### 2. Current baseline conclusion
#### S2
- Return underperforms not-selected names on 3M / 6M / 1Y.
- Path MDD is only slightly better.
- Interpretation: current S2 behaves like a weak defensive filter rather than a strong alpha selector.

#### S3
- Return outperforms not-selected names on 3M / 6M / 1Y.
- Path MDD is consistently worse.
- Interpretation: S3 has real selection alpha, but it pays for that alpha with higher drawdown.

#### S3 Core2
- Return underperforms not-selected names on 3M / 6M / 1Y.
- Path MDD is also worse.
- Interpretation: Core2 currently needs redesign, not minor polishing.

### 3. Upgrade priorities
1. S2 upgrade
- Goal: improve 3M / 6M / 1Y return without materially worsening MDD.
- Priority reason: current selection alpha is weak.

2. S3 Core2 redesign
- Goal: recover return edge on 3M / 6M / 1Y and reduce drawdown drag.
- Priority reason: current selected-vs-not-selected result is negative on both axes.

3. S3 risk-adjusted refinement
- Goal: retain return edge while reducing MDD and concentration risk.
- Priority reason: selection alpha exists, but volatility cost is high.

### 4. Practical tuning levers
#### S2
- Add medium-horizon relative-strength screen after fundamentals ranking.
- Add overheat penalty to avoid names already too extended above long moving averages.
- Tighten or replace regime gating with measures more aligned to 3M / 6M / 1Y follow-through.
- Re-test whether top-N should remain 30 or become narrower for stronger alpha density.

#### S3
- Add volatility penalty or risk-adjusted ranking term after current score.
- Add better breakout-quality filter rather than raw breakout flag.
- Penalize names with extreme recent run-up and weak follow-through probability.
- Test lighter concentration in the top few names.

#### S3 Core2
- Revisit the core score itself; mom20 + vol ratio alone may be too thin.
- Rebalance the role of fundamentals from tie-break only toward selective quality confirmation.
- Re-evaluate breadth gate thresholds and exit logic to reduce weak carry names.
- Consider reducing reliance on pure activity/acceleration when medium-horizon persistence is poor.

### 5. Success criteria
An upgrade candidate should be considered promising only if:
- selected average return improves vs not-selected on 3M / 6M / 1Y
- MDD is not materially worse, or the return improvement clearly compensates for the risk
- the result is not driven by a single horizon only

Recommended pass/fail framing:
- Pass: positive return delta on at least 2 of 3 horizons and no major MDD deterioration
- Strong pass: positive return delta on all 3 horizons and flat-to-better MDD on at least 2 horizons
- Fail: return delta remains negative on 6M and 1Y

### 6. Research workflow
1. Fix the experiment definition before backtesting.
2. Run the variant.
3. Compare selected vs not-selected inside the same universe.
4. Compare portfolio-level metrics separately.
5. Promote only variants that survive both views.

### 7. Deliverables
- experiment registry JSON
- baseline board CSV/Markdown
- repeated selected-vs-not-selected comparison outputs
- upgrade notes per variant
