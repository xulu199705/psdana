"""Public Golden API; importing this package does not import Matplotlib."""

from .core import PSDConfig, PSDResult, compute_psd

__all__ = ["PSDConfig", "PSDResult", "compute_psd"]
