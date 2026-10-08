"""Small build helper for Phase 2 scripts; no Phase 1 DSP changes."""

import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def go_executable(explicit=None):
    path = explicit or os.environ.get("PSD_GO") or shutil.which("go")
    if path is None and os.name == "nt" and os.environ.get("ProgramFiles"):
        candidate = Path(os.environ["ProgramFiles"]) / "Go" / "bin" / "go.exe"
        if candidate.is_file():
            path = str(candidate)
    if path is None:
        raise RuntimeError("Go not found: add it to PATH or pass --go / set PSD_GO")
    return str(path)


def go_environment():
    env = os.environ.copy()
    for variable, suffix in (("GOCACHE", "go-build"), ("GOTMPDIR", "tmp")):
        destination = ROOT / ".cache" / suffix
        destination.mkdir(parents=True, exist_ok=True)
        env[variable] = str(destination)
    # Keep child test temporary files in the writable project cache.
    env["TEMP"] = env["TMP"] = env["GOTMPDIR"]
    return env


def build_cli(go=None):
    destination = ROOT / "go" / "bin"
    destination.mkdir(exist_ok=True)
    binary = destination / ("psdana.exe" if os.name == "nt" else "psdana")
    subprocess.run([go_executable(go), "build", "-o", str(binary), "./cmd/psdana"],
                   cwd=ROOT / "go", env=go_environment(), check=True)
    return binary
