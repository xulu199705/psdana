"""Packed order, fixed-point scale and real capture interpretation."""

from pathlib import Path

import numpy as np
import pytest

from psd.csvio import read_csv, CSVConfig
from psd.iqio import read_packed64
from qam_gen import quantize_q15, write_packed64

ROOT = Path(__file__).resolve().parents[2]


def test_packed_word_order(tmp_path):
    path = tmp_path/"packed.csv"
    # older I=-32768 Q=32767; newer I=1 Q=-1
    path.write_text("packed_iq\nFFFF00017FFF8000\n",encoding="utf-8")
    x = read_packed64(path)
    np.testing.assert_array_equal(x,[-1+1j*(32767/32768),1/32768-1j/32768])
    values = np.array([[-32768,32767],[1,-1]],dtype=np.int16)
    write_packed64(path,values)
    np.testing.assert_array_equal(read_packed64(path),x)


def test_explicit_valid_filter(tmp_path):
    path = tmp_path/"valid.csv"
    path.write_text("data,valid\ninvalid,0\n0000000000000000,1\n",encoding="utf-8-sig")
    np.testing.assert_array_equal(read_packed64(path,valid_column=1),[0j,0j])
    path.write_text("data,valid\n0000000000000000,2\n",encoding="utf-8")
    with pytest.raises(ValueError,match="valid"):
        read_packed64(path,valid_column=1)


@pytest.mark.parametrize("text", ["", "packed_iq\n", "packed_iq\n123\n", "packed_iq\nGGGG000000000000\n", "packed_iq\n\n"])
def test_invalid_packed(tmp_path,text):
    path = tmp_path/"bad.csv"
    path.write_text(text,encoding="utf-8")
    with pytest.raises(ValueError):
        read_packed64(path)


def test_q15_factor_and_clipping():
    values,meta = quantize_q15(np.array([1-1j,2+0j]))
    np.testing.assert_array_equal(values,[[32767,-32767],[32767,0]])
    assert meta["quantizer_multiplier"] == 32767
    assert meta["decoder_divisor"] == 32768
    assert meta["clipped_component_count"] == 1


def test_actual_qam_csv_layout():
    path = ROOT/"data/qam64_20MSymPS_160MSPS_RRC0p25.csv"
    if not path.exists():
        pytest.skip("BLOCKED: real QAM capture not supplied")
    capture = read_csv(path,CSVConfig(sample_format="hex_q15",i_column="i",q_column="q"))
    assert capture.header == ("q","i")
    assert capture.sample_count == 16384
    assert capture.columns == (1,0)
    first = path.read_text(encoding="utf-8-sig").splitlines()[1].split(",")
    def signed(t):
        v = int(t,16)
        return (v if v<32768 else v-65536)/32768
    assert capture.samples[0] == signed(first[1])+1j*signed(first[0])
