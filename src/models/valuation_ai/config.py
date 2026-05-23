# config.py ver 2026-05-06_001
from __future__ import annotations

from pathlib import Path

MODEL_CODE = "AI-GROWTH-VALUATION-V01"
MODEL_NAME_KR = "주가수준평가AI"

ROOT = Path(r"D:\Quant")
PRICE_DB = ROOT / r"data\db\price.db"
REGIME_DB = ROOT / r"data\db\regime.db"
FUNDAMENTALS_DB = ROOT / r"data\db\fundamentals.db"
CLASSIFICATION_DB = ROOT / r"data\db\security_classification.db"
OUT_DB = ROOT / r"data\db\valuation_ai.db"
MODEL_DIR = ROOT / r"data\models\valuation_ai"
REPORT_DIR = ROOT / r"reports\valuation_ai"
DEFAULT_UNIVERSE = ROOT / r"data\universe\universe_mix_top400_latest.csv"
QUANTMARKET_CONTEXT_DIR = Path(r"D:\QuantMarket\service_platform\quant_model_handoff\market_context\current")

FEATURE_TABLE = "valuation_features_monthly"
LABEL_TABLE = "valuation_labels_forward"
SCORE_TABLE = "valuation_ai_scores"
EVAL_TABLE = "valuation_model_eval"
MARKET_CONTEXT_DAILY_TABLE = "valuation_market_context_daily"
MARKET_CONTEXT_MONTHLY_TABLE = "valuation_market_context_monthly"

FEATURE_COLUMNS = [
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "ret_12m",
    "excess_ret_3m_sector",
    "vol_20d",
    "vol_60d",
    "mdd_3m",
    "mdd_6m",
    "distance_sma_60",
    "distance_sma_140",
    "distance_sma_200",
    "trading_value_20d",
    "price_acceleration",
    "price_percentile_3y",
    "annual_revenue_yoy",
    "annual_op_income_yoy",
    "half_revenue_yoy",
    "half_op_income_yoy",
    "q_revenue_yoy",
    "q_op_income_yoy",
    "q_revenue_yoy_delta_1q",
    "q_op_income_yoy_delta_1q",
    "pit_growth_score",
    "coverage_score",
    "sector_sales_growth_median",
    "sector_op_growth_median",
    "sector_price_momentum_3m",
    "sector_price_momentum_12m",
    "market_regime",
    "market_ret_1m",
    "market_ret_3m",
    "market_ret_6m",
    "market_vol_20d",
    "market_mdd_3m",
    "market_breadth_ret_pos_1m",
    "market_breadth_above_sma60",
    "market_breadth_above_sma120",
    "market_regime_score",
    "market_regime_bullish_pct",
    "market_regime_bearish_pct",
    "market_regime_neutral_pct",
    "market_context_available",
    "qm_market_state_score",
    "qm_trend_score",
    "qm_breadth_score",
    "qm_risk_score",
    "qm_defensive_flow_score",
    "qm_kospi_ret_1m",
    "qm_kospi_ret_3m",
    "qm_kosdaq_ret_1m",
    "qm_kosdaq_ret_3m",
    "qm_market_breadth_above_sma20",
    "qm_new_high_ratio_20d",
    "qm_new_low_ratio_20d",
    "qm_trading_value_expansion_ratio",
    "qm_risk_on_score",
    "qm_risk_off_score",
    "qm_theme_ret_1w",
    "qm_theme_ret_1m",
    "qm_theme_ret_3m",
    "qm_theme_momentum_score",
    "qm_theme_rotation_score",
    "qm_theme_persistence_days",
    "qm_theme_breadth_positive_ratio",
    "qm_theme_above_sma60_ratio",
    "qm_theme_trading_value_expansion_ratio",
    "qm_theme_concentration_score",
    "qm_leading_theme_rank",
    "qm_theme_mapping_confidence",
    "qm_usdkrw_ret_1m",
    "qm_gold_proxy_ret_1m",
    "qm_bond_proxy_ret_1m",
    "qm_inverse_etf_ret_1m",
    "qm_defensive_asset_strength_score",
    "qm_market_stress_score",
    "qm_drawdown_pressure_score",
    "qm_crash_warning_flag",
    "qm_foreign_net_buy_ratio",
    "qm_institution_net_buy_ratio",
    "qm_flow_concentration_score",
    "qm_smart_money_score",
    "qm_flow_context_available",
    "qm_flow_coverage_flag",
    "qm_forecast_20d_predicted_forward_return",
    "qm_forecast_20d_score",
    "qm_forecast_20d_confidence",
    "qm_forecast_20d_training_sample_count",
    "qm_forecast_20d_baseline_score",
    "qm_forecast_20d_expected_volatility_score",
    "qm_forecast_20d_drawdown_risk_score",
    "qm_forecast_20d_upside_participation_score",
    "qm_forecast_20d_market_forecast_score",
    "qm_forecast_20d_global_risk_on_score",
    "qm_forecast_20d_external_macro_pressure_score",
    "qm_forecast_20d_external_asset_risk_on_score",
    "qm_forecast_20d_korea_proxy_momentum_score",
    "qm_forecast_20d_market_state_delta_5d",
    "qm_forecast_20d_market_state_delta_20d",
    "qm_forecast_20d_score_acceleration_5d",
    "qm_forecast_20d_score_delta_5d",
    "qm_forecast_20d_score_delta_20d",
    "qm_forecast_20d_transition_count_20d",
    "qm_forecast_20d_regime_stability_score",
    "qm_forecast_20d_coverage_ratio",
]

CATEGORICAL_COLUMNS = [
    "market",
    "sector_bucket",
    "theme_bucket",
    "market_regime_label",
    "qm_market_state_label",
    "qm_volatility_regime_label",
    "qm_quantmarket_theme_bucket",
    "qm_forecast_20d_label",
    "qm_forecast_20d_coverage_quality_label",
]

STATE_THRESHOLDS = {
    "UNDERVALUED": 80.0,
    "FAIR": 60.0,
    "OVERHEATED": 40.0,
}
