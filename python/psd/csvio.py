"""Strict CSV adapter with explicit column and fixed-point interpretation."""

import csv
from dataclasses import dataclass
from numbers import Integral
from pathlib import Path
from typing import Optional, Union

import numpy as np

Column = Union[str, int]


@dataclass(frozen=True)
class CSVConfig:
    sample_format: str = "float"  # float / q15 (decimal int16) / hex_q15 (16-bit words)
    input_type: str = "auto"  # auto / real / iq
    header: str = "auto"  # auto / yes / no
    delimiter: Optional[str] = None  # sniff comma / semicolon / tab; single column -> comma
    real_column: Optional[Column] = None
    i_column: Optional[Column] = None
    q_column: Optional[Column] = None


@dataclass(frozen=True)
class CSVData:
    samples: np.ndarray
    path: Path
    header: Optional[tuple]
    delimiter: str
    columns: tuple
    sample_format: str

    @property
    def sample_count(self) -> int:
        return int(self.samples.size)


def _number(token: str, sample_format: str) -> float:
    token = token.strip()
    if sample_format == "float":
        value = float(token)
    elif sample_format == "q15":
        if not token or any(c not in "+-0123456789" for c in token):
            raise ValueError("Q1.15 requires decimal signed int16 tokens")
        integer = int(token, 10)
        if not -32768 <= integer <= 32767:
            raise ValueError("decimal Q1.15 value outside signed int16 range")
        value = integer / 32768.0
    else:
        digits = token[2:] if token.lower().startswith("0x") else token
        if not 1 <= len(digits) <= 4 or any(c not in "0123456789abcdefABCDEF" for c in digits):
            raise ValueError("hex_q15 requires an unsigned 16-bit hexadecimal word")
        integer = int(digits, 16)
        value = (integer if integer < 32768 else integer - 65536) / 32768.0
    if not np.isfinite(value):
        raise ValueError("sample contains NaN or Inf")
    return value


def read_csv(path: Union[str, Path], config: CSVConfig = CSVConfig()) -> CSVData:
    """Read samples without peak normalization. Unlabelled two-column data is ambiguous.

    Auto IQ requires header names i and q (case insensitive), or both explicit
    selectors. input_type='iq' explicitly declares first column I, second Q for
    an unlabelled two-column file. Selectors are names or zero-based integers.
    """
    if config.sample_format not in ("float", "q15", "hex_q15"):
        raise ValueError("sample_format must be float, q15 or hex_q15")
    if config.input_type not in ("auto", "real", "iq") or config.header not in ("auto", "yes", "no"):
        raise ValueError("invalid input_type or header setting")
    if config.delimiter is not None and (len(config.delimiter) != 1 or config.delimiter in "\r\n"):
        raise ValueError("delimiter must be a single non-newline character")
    source = Path(path)
    with source.open(encoding="utf-8-sig", newline="") as stream:
        preview = stream.read(8192)
        stream.seek(0)
        delimiter = config.delimiter
        if delimiter is None:
            try:
                delimiter = csv.Sniffer().sniff(preview, delimiters=",;\t").delimiter
            except csv.Error:
                delimiter = ","
        rows = [(line, [v.strip() for v in row]) for line, row in enumerate(csv.reader(stream, delimiter=delimiter), 1) if row]
    if not rows:
        raise ValueError("CSV contains no rows")
    first = rows[0][1]
    width = len(first)
    for line, row in rows:
        if len(row) != width:
            raise ValueError(f"CSV row {line}: expected {width} columns, found {len(row)}")
    if config.header == "auto":
        numeric = []
        for token in first:
            try:
                _number(token, config.sample_format)
                numeric.append(True)
            except ValueError:
                numeric.append(False)
        if all(numeric):
            has_header = False
        elif any(numeric):
            raise ValueError("ambiguous first row: mixed header/numeric values; specify header=yes/no")
        else:
            # Do not silently swallow an invalid NaN/Inf or numeric sample as a header.
            for token in first:
                try:
                    float(token)
                except ValueError:
                    continue
                raise ValueError("invalid numeric first row; specify the sample format/header explicitly")
            has_header = True
    else:
        has_header = config.header == "yes"
    header = tuple(first) if has_header else None
    if header and (any(not name for name in header) or len(set(s.casefold() for s in header)) != width):
        raise ValueError("CSV header names must be nonempty and unique (case insensitive)")
    data_rows = rows[1:] if has_header else rows
    if not data_rows:
        raise ValueError("CSV has a header but no samples")

    def index(selector: Column) -> int:
        if isinstance(selector, Integral) and not isinstance(selector, bool):
            selected = int(selector)
            if not 0 <= selected < width:
                raise ValueError(f"column index {selected} outside [0, {width})")
            return selected
        if isinstance(selector, str) and header:
            matches = [j for j, name in enumerate(header) if name.casefold() == selector.casefold()]
            if len(matches) == 1:
                return matches[0]
        raise ValueError(f"column {selector!r} not found; names require a header")

    has_iq_selectors = config.i_column is not None or config.q_column is not None
    if has_iq_selectors and (config.i_column is None or config.q_column is None):
        raise ValueError("specify both i_column and q_column")
    if config.real_column is not None and (has_iq_selectors or config.input_type == "iq"):
        raise ValueError("real_column conflicts with IQ selection")
    if has_iq_selectors and config.input_type == "real":
        raise ValueError("IQ columns conflict with input_type=real")
    if has_iq_selectors:
        selected = (index(config.i_column), index(config.q_column))
    elif config.real_column is not None:
        selected = (index(config.real_column),)
    elif config.input_type != "real" and header and {"i", "q"}.issubset(s.casefold() for s in header):
        selected = (index("i"), index("q"))
    elif width == 1 and config.input_type != "iq":
        selected = (0,)
    elif width == 2 and config.input_type == "iq" and not header:
        selected = (0, 1)
    else:
        raise ValueError("ambiguous data columns; specify real_column or both i_column/q_column")
    if len(set(selected)) != len(selected):
        raise ValueError("I and Q must select different columns")
    output = np.empty(len(data_rows), dtype=np.complex128 if len(selected) == 2 else np.float64)
    for j, (line, row) in enumerate(data_rows):
        try:
            values = [_number(row[k], config.sample_format) for k in selected]
        except ValueError as exc:
            raise ValueError(f"CSV row {line}: {exc}") from exc
        output[j] = values[0] + 1j * values[1] if len(values) == 2 else values[0]
    return CSVData(output, source.resolve(), header, delimiter, selected, config.sample_format)
