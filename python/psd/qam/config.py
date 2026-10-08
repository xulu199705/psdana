"""Explicit, reproducible single-channel QAM receiver configuration."""

from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np


def positive_int(value, name, minimum=1):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def finite_real(value, name, minimum=0, strict=False):
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
            or not np.isfinite(value) or (value <= minimum if strict else value < minimum)):
        raise ValueError(f"{name} must be finite and {'>' if strict else '>='} {minimum}")


@dataclass(frozen=True)
class QAMConfig:
    sample_rate_hz: float = 160e6
    symbol_rate_hz: float = 20e6
    qam_order: int = 64
    rrc_beta: float = 0.25
    rrc_span_symbols: int = 10
    timing_interp: int = 16
    timing_kaiser_beta: float = 8.0
    extra_edge_trim_symbols: int = 6
    enable_cfo_correction: bool = True
    max_residual_cfo_hz: float = 5000.0
    cfo_coarse_steps: int = 81
    cfo_fine_steps: int = 41
    cfo_search_max_symbols: int = 12000
    max_analysis_symbols: int = 30000
    constellation_points: int = 5000
    q_sign: int = 1
    scalar_fit_iterations: int = 5
    min_analysis_symbols: int = 200
    max_decision_evm_pct: float = 12.0

    def __post_init__(self):
        finite_real(self.sample_rate_hz, "sample_rate_hz", strict=True)
        finite_real(self.symbol_rate_hz, "symbol_rate_hz", strict=True)
        ratio = self.sample_rate_hz / self.symbol_rate_hz
        if not np.isfinite(ratio) or ratio < 2 or abs(ratio-round(ratio)) > 8*np.finfo(float).eps*ratio:
            raise ValueError("sample_rate/symbol_rate must be an integer SPS >= 2; no resampling to change SPS")
        positive_int(self.qam_order, "qam_order")
        if self.qam_order not in (16, 64, 256):
            raise ValueError("qam_order must be 16, 64 or 256")
        finite_real(self.rrc_beta, "rrc_beta")
        if self.rrc_beta > 1:
            raise ValueError("rrc_beta must be in [0,1]")
        positive_int(self.rrc_span_symbols, "rrc_span_symbols")
        for name in ("timing_interp", "constellation_points", "scalar_fit_iterations"):
            positive_int(getattr(self, name), name)
        positive_int(self.extra_edge_trim_symbols, "extra_edge_trim_symbols", 0)
        finite_real(self.timing_kaiser_beta, "timing_kaiser_beta")
        finite_real(self.max_residual_cfo_hz, "max_residual_cfo_hz")
        if self.max_residual_cfo_hz >= self.symbol_rate_hz/2:
            raise ValueError("CFO search range must be below symbol_rate/2")
        if not isinstance(self.enable_cfo_correction, (bool, np.bool_)):
            raise ValueError("enable_cfo_correction must be boolean")
        if self.enable_cfo_correction and self.max_residual_cfo_hz == 0:
            raise ValueError("enabled CFO correction requires a positive search range")
        for name in ("cfo_coarse_steps", "cfo_fine_steps"):
            positive_int(getattr(self, name), name, 3)
            if getattr(self, name) % 2 == 0:
                raise ValueError(f"{name} must be odd to include zero/center")
        positive_int(self.min_analysis_symbols, "min_analysis_symbols", 32)
        for name in ("cfo_search_max_symbols", "max_analysis_symbols"):
            positive_int(getattr(self, name), name, self.min_analysis_symbols)
        positive_int(self.q_sign, "q_sign", -1)
        if self.q_sign not in (-1, 1):
            raise ValueError("q_sign must be -1 or +1")
        finite_real(self.max_decision_evm_pct, "max_decision_evm_pct", strict=True)
        # Accepted NumPy scalar inputs become native JSON-portable parameters.
        for name in self.__dataclass_fields__:
            value = getattr(self,name)
            if isinstance(value,np.generic):
                object.__setattr__(self,name,value.item())

    @property
    def samples_per_symbol(self):
        return int(round(self.sample_rate_hz/self.symbol_rate_hz))
