from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RouterModeConfig:
    stock_model: str
    etf_model: str
    stock_weight: float
    etf_weight: float
    stock_fallback: str | None = None
    etf_fallback: str | None = None


@dataclass(frozen=True)
class ServiceProfileConfig:
    name: str
    stock_weight_delta_by_mode: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RouterExecutionConfig:
    rebalance: str = 'M'
    weekly_anchor_weekday: int = 2
    weekly_holiday_shift: str = 'prev'
    fee_bps: float = 0.0
    slippage_bps: float = 0.0


@dataclass(frozen=True)
class RouterRegimeConfig:
    horizon: str = '3m'
    risk_on_min: float = 3.0
    risk_off_max: float = 1.0
    fallback_mode: str = 'neutral'


@dataclass(frozen=True)
class RouterConfig:
    strategy_name: str = 'MULTIASSET_ROUTER_P0'
    regime: RouterRegimeConfig = field(default_factory=RouterRegimeConfig)
    execution: RouterExecutionConfig = field(default_factory=RouterExecutionConfig)
    modes: dict[str, RouterModeConfig] = field(default_factory=lambda: {
        'risk_on': RouterModeConfig(stock_model='S3', etf_model='S4', stock_weight=0.70, etf_weight=0.30, stock_fallback='S2', etf_fallback='CASH'),
        'neutral': RouterModeConfig(stock_model='S2', etf_model='S5', stock_weight=0.40, etf_weight=0.60, stock_fallback='CASH', etf_fallback='CASH'),
        'risk_off': RouterModeConfig(stock_model='S2', etf_model='S6', stock_weight=0.10, etf_weight=0.90, stock_fallback='CASH', etf_fallback='CASH'),
    })
    service_profiles: dict[str, ServiceProfileConfig] = field(default_factory=lambda: {
        'auto': ServiceProfileConfig(name='auto', stock_weight_delta_by_mode={}),
        'stable': ServiceProfileConfig(name='stable', stock_weight_delta_by_mode={'risk_on': -0.15, 'neutral': -0.10, 'risk_off': -0.05}),
        'balanced': ServiceProfileConfig(name='balanced', stock_weight_delta_by_mode={'risk_on': -0.05, 'neutral': 0.0, 'risk_off': 0.0}),
        'growth': ServiceProfileConfig(name='growth', stock_weight_delta_by_mode={'risk_on': 0.10, 'neutral': 0.10, 'risk_off': 0.05}),
    })

    def resolve_mode_config(self, mode: str, service_profile: str = 'auto') -> dict[str, object]:
        mode_cfg = self.modes[str(mode)]
        prof = self.service_profiles.get(service_profile, self.service_profiles['auto'])
        delta = float(prof.stock_weight_delta_by_mode.get(mode, 0.0))
        stock_weight = min(max(float(mode_cfg.stock_weight) + delta, 0.0), 1.0)
        etf_weight = min(max(1.0 - stock_weight, 0.0), 1.0)
        return {
            'stock_model': mode_cfg.stock_model,
            'etf_model': mode_cfg.etf_model,
            'stock_weight': stock_weight,
            'etf_weight': etf_weight,
            'stock_fallback': mode_cfg.stock_fallback,
            'etf_fallback': mode_cfg.etf_fallback,
        }
