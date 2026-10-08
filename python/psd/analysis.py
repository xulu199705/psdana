"""Compose independent analyses over one unchanged input sample array."""

from dataclasses import dataclass
from typing import Optional, Tuple, TYPE_CHECKING

from .core import PSDConfig, PSDResult, compute_psd
from .power import PowerResult, analyze_band_power

if TYPE_CHECKING:
    from .qam import QAMConfig, QAMResult


@dataclass(frozen=True)
class IQAnalysis:
    psd: PSDResult
    power_metrics: Optional[PowerResult]
    qam_metrics: Optional["QAMResult"]


def analyze_iq(samples, psd_config: PSDConfig = PSDConfig(),
               qam_config: Optional["QAMConfig"] = None,
               power_band: Optional[Tuple[float,float]] = None, *,
               dc_mode="legacy_mean") -> IQAnalysis:
    """Compute PSD, optional (left,right) band power and optional blind QAM.

    QAM rate must equal PSD fs; QAM requires complex input. No file or plot I/O.
    SciPy is loaded only when QAM is requested.
    """
    if qam_config is not None and qam_config.sample_rate_hz != psd_config.fs:
        raise ValueError("PSD and QAM sample rates must agree")
    spectrum = compute_psd(samples, psd_config)
    power = None
    if power_band is not None:
        if len(power_band) != 2:
            raise ValueError("power_band must contain left and right boundaries")
        power = analyze_band_power(spectrum, *power_band)
    qam = None
    if qam_config is not None:
        from .qam import analyze_qam
        qam = analyze_qam(samples, qam_config, dc_mode=dc_mode)
    return IQAnalysis(spectrum,power,qam)
