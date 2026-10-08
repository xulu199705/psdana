import os
import sys
from pathlib import Path

os.environ["MPLBACKEND"] = "Agg"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
