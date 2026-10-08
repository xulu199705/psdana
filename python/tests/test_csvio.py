import numpy as np
import pytest

from psd.csvio import CSVConfig, read_csv


def write(tmp_path, text):
    path = tmp_path / "capture.csv"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("text", ["0.25\n-0.5\n", "sample\n0.25\n-0.5\n", "\ufeffsample\n0.25\n-0.5\n"])
def test_single_column(tmp_path, text):
    data = read_csv(write(tmp_path, text))
    np.testing.assert_array_equal(data.samples, [0.25, -0.5])
    assert data.samples.dtype == np.float64


@pytest.mark.parametrize("delimiter", [",", ";", "\t"])
def test_named_iq_order_and_delimiter(tmp_path, delimiter):
    text = delimiter.join(["Q", "I"]) + "\n" + delimiter.join(["0.5", "0.25"]) + "\n"
    data = read_csv(write(tmp_path, text))
    assert data.delimiter == delimiter
    np.testing.assert_array_equal(data.samples, [0.25 + 0.5j])
    assert data.samples.dtype == np.complex128 and data.columns == (1, 0)


def test_unlabelled_iq_requires_explicit_interpretation(tmp_path):
    path = write(tmp_path, "0.25,0.5\n-0.5,0.25\n")
    with pytest.raises(ValueError, match="ambiguous"):
        read_csv(path)
    a = read_csv(path, CSVConfig(input_type="iq"))
    b = read_csv(path, CSVConfig(i_column=0, q_column=1, header="no"))
    np.testing.assert_array_equal(a.samples, [0.25 + 0.5j, -0.5 + 0.25j])
    np.testing.assert_array_equal(a.samples, b.samples)


def test_metadata_columns_and_explicit_names(tmp_path):
    path = write(tmp_path, "time,real,imag\n0,0.25,0.5\n1,-0.5,0.25\n")
    with pytest.raises(ValueError, match="ambiguous"):
        read_csv(path)
    data = read_csv(path, CSVConfig(i_column="real", q_column="imag"))
    np.testing.assert_array_equal(data.samples, [0.25 + 0.5j, -0.5 + 0.25j])
    real = read_csv(path, CSVConfig(real_column=1))
    np.testing.assert_array_equal(real.samples, [0.25, -0.5])


@pytest.mark.parametrize("sample_format,text", [
    ("q15", "i,q\n32767,-32768\n0,-1\n"),
    ("hex_q15", "q,i\n8000,7FFF\n0xFFFF,0000\n"),
])
def test_q15_conversion(tmp_path, sample_format, text):
    data = read_csv(write(tmp_path, text), CSVConfig(sample_format=sample_format))
    np.testing.assert_array_equal(data.samples, [32767 / 32768 - 1j, -1j / 32768])


@pytest.mark.parametrize("text,config", [
    ("", CSVConfig()), ("sample\n", CSVConfig()), ("a,a\n1,2\n", CSVConfig()),
    ("i,q\n1,2,3\n", CSVConfig()), ("i,q\n1,\n", CSVConfig()),
    ("nan\n1\n", CSVConfig()), ("inf\n1\n", CSVConfig()),
    ("sample\nNaN\n", CSVConfig()), ("sample\nInf\n", CSVConfig()),
    ("i,1\n1,2\n", CSVConfig()), ("i,q\n1,2\n", CSVConfig(i_column="i")),
    ("i,q\n1,2\n", CSVConfig(i_column="i", q_column="missing")),
    ("i,q\n1,2\n", CSVConfig(i_column=0, q_column=0)),
    ("i,q\n1,2\n", CSVConfig(real_column=2)),
    ("i,q\n1,2\n", CSVConfig(real_column=0, input_type="iq")),
    ("i,q\n1,2\n", CSVConfig(i_column=0, q_column=1, input_type="real")),
    ("sample\n32768\n", CSVConfig(sample_format="q15")),
    ("sample\n-32769\n", CSVConfig(sample_format="q15")),
    ("sample\n1.5\n", CSVConfig(sample_format="q15")),
    ("sample\n10000\n", CSVConfig(sample_format="hex_q15")),
    ("sample\n-1\n", CSVConfig(sample_format="hex_q15")),
    ("sample\nGGGG\n", CSVConfig(sample_format="hex_q15")),
    ("1\n2\n", CSVConfig(sample_format="unknown")),
    ("1\n2\n", CSVConfig(delimiter="::")),
    ("1\n2\n", CSVConfig(header="bad")),
])
def test_invalid_csv(tmp_path, text, config):
    with pytest.raises(ValueError):
        read_csv(write(tmp_path, text), config)


def test_explicit_header_for_hex_looking_names(tmp_path):
    # 'A' and 'B' are legal hexadecimal samples; auto mode cannot infer these as labels.
    path = write(tmp_path, "A,B\n7fff,8000\n")
    data = read_csv(path, CSVConfig(header="yes", sample_format="hex_q15", i_column="A", q_column="B"))
    np.testing.assert_array_equal(data.samples, [32767 / 32768 - 1j])
