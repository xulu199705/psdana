"""Public Golden API; importing this package does not import Matplotlib."""

from .core import PSDConfig, PSDResult, compute_psd
from .power import PowerResult, analyze_band_power

__all__ = ["PSDConfig", "PSDResult", "compute_psd", "PowerResult", "analyze_band_power"]
