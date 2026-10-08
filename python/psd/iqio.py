"""Explicit packed-IQ adapter; ordinary CSV semantics remain in csvio."""

import csv
from pathlib import Path

import numpy as np


def read_packed64(path, *, column=0, header=True, valid_column=None):
    """Decode two Q1.15 IQ samples per 64-bit HEX word, older sample first.

    I=bits15:0, Q=bits31:16 in each word. Optional valid selector is an index;
    only decimal 0/1 are accepted. No guessed headers, byte order or padding.
    """
    if isinstance(column, bool) or not isinstance(column, int) or column < 0:
        raise ValueError("packed column must be a nonnegative index")
    if not isinstance(header, bool):
        raise ValueError("header must be explicitly True or False")
    if valid_column is not None and (isinstance(valid_column, bool) or not isinstance(valid_column, int) or valid_column < 0 or valid_column == column):
        raise ValueError("valid_column must be a distinct nonnegative index")
    samples = []
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        if header:
            next(reader, None)
        for line, row in enumerate(reader, 2 if header else 1):
            if len(row) <= max(column,valid_column or 0):
                raise ValueError(f"packed row {line}: missing column")
            if valid_column is not None:
                valid = row[valid_column].strip()
                if valid not in ("0","1"):
                    raise ValueError(f"packed row {line}: valid must be 0 or 1")
                if valid == "0":
                    continue
            token = row[column].strip().removeprefix("0x").removeprefix("0X")
            if len(token) != 16 or any(c not in "0123456789abcdefABCDEF" for c in token):
                raise ValueError(f"packed row {line}: expected exactly 16 hexadecimal digits")
            value = int(token,16)
            for shift in (0,32):
                word = (value >> shift)&0xffffffff
                i, q = word&0xffff, word >> 16
                i = i if i < 32768 else i-65536
                q = q if q < 32768 else q-65536
                samples.append(complex(i/32768,q/32768))
    if not samples:
        raise ValueError("packed input contains no valid samples")
    return np.asarray(samples,dtype=np.complex128)
