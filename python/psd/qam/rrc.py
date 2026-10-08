"""Unit-energy RRC, including exact removable singularities."""

import numpy as np

from .config import finite_real, positive_int


def rrc_taps(beta: float, span_symbols: int, sps: int) -> np.ndarray:
    finite_real(beta, "beta")
    if beta > 1:
        raise ValueError("beta must be in [0,1]")
    positive_int(span_symbols, "span_symbols")
    positive_int(sps, "sps")
    length = span_symbols*sps+1
    if length % 2 == 0:
        length += 1  # Same odd-length convention as the supplied generator.
    t = np.arange(-(length//2), length//2+1, dtype=float)/sps
    if beta == 0:
        h = np.sinc(t)
    else:
        h = np.empty_like(t)
        for k, tk in enumerate(t):
            if tk == 0:
                h[k] = 1+beta*(4/np.pi-1)
            elif abs(abs(tk)-1/(4*beta)) <= 8*np.finfo(float).eps*max(1,abs(tk)):
                h[k] = beta/np.sqrt(2)*((1+2/np.pi)*np.sin(np.pi/(4*beta))
                                      +(1-2/np.pi)*np.cos(np.pi/(4*beta)))
            else:
                h[k] = (np.sin(np.pi*tk*(1-beta))+4*beta*tk*np.cos(np.pi*tk*(1+beta)))/(np.pi*tk*(1-(4*beta*tk)**2))
    return h/np.sqrt(np.sum(h*h))
