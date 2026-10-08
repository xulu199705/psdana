"""Constant-cost square-grid nearest coordinate, preserving float ties."""
import numpy as np

def nearest_level_indices(values, levels):
    # Clamp before subtraction to prevent overflow for finite extreme inputs.
    scaled=(np.clip(values,levels[0],levels[-1])-levels[0])/(levels[1]-levels[0])
    lower=np.clip(np.floor(scaled).astype(np.intp),0,len(levels)-2)
    upper=lower+1
    # Compare the actual stored levels, preserving the former argmin's exact
    # floating-point distance semantics, including lower-index ties.
    result=np.where(abs(values-levels[upper])<abs(values-levels[lower]),upper,lower)
    # At extreme finite magnitudes, subtraction can round several distances
    # identically. Preserve argmin's earliest tie across the whole grid.
    extreme=abs(values)>1e12
    if np.any(extreme):
        result[extreme]=np.argmin(abs(values[extreme,None]-levels),axis=1)
    return result
