"""Explicit README image export; library plot functions still only show."""

from dataclasses import asdict
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from psd import PSDConfig, analyze_iq
from psd.csvio import CSVConfig, read_csv
from psd.plotting import plot_psd
from psd.qam import QAMConfig
from psd.qam.plotting import plot_constellation
from qam_gen import ROOT, sha256


def render():
    source = ROOT/"data/qam64_20MSymPS_160MSPS_RRC0p25.csv"
    output = ROOT/"docs/images"
    output.mkdir(parents=True,exist_ok=True)
    csv_config = CSVConfig(sample_format="hex_q15",i_column="i",q_column="q")
    psd_config,qam_config = PSDConfig(),QAMConfig()
    analysis = analyze_iq(read_csv(source,csv_config).samples,psd_config,qam_config,
                          dc_mode="decision_directed_joint")
    spectrum,axes = plot_psd(analysis.psd,show=False)
    axes.set_title("64QAM capture | 160 MSPS | Periodogram\n"
                   f"FFT {analysis.psd.fft_size} | Hann | ENBW {analysis.psd.enbw_hz:.3f} Hz")
    spectrum.tight_layout()
    constellation,constellation_axes = plot_constellation(analysis.qam_metrics,show=False)
    constellation_axes.legend(loc="upper center",bbox_to_anchor=(.5,-.1),ncol=2)
    constellation.tight_layout()
    for name,figure in (("psd.png",spectrum),("constellation.png",constellation)):
        figure.savefig(output/name,dpi=150,metadata={"Software":"psdana README renderer"})
        plt.close(figure)
    manifest = dict(input_file=source.relative_to(ROOT).as_posix(),input_sha256=sha256(source),
        csv_config=asdict(csv_config),psd_config=asdict(psd_config),qam_config=asdict(qam_config),
        dc_mode="decision_directed_joint",qam_algorithm_version="qam-blind-scalar-2",
        evm_pct_rms=analysis.qam_metrics.evm_pct_rms,recovered_symbol_count=analysis.qam_metrics.recovered_symbol_count,
        output_files=["psd.png","constellation.png"])
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print("Exported docs/images/psd.png and docs/images/constellation.png")


if __name__ == "__main__":
    render()
