"""User-owned runtime paths, independent of the launch directory.

Set SHNIFTER_DATA_DIR to an explicit directory for isolated simulations/tests.
Resolving a path never creates files or directories.
"""
from __future__ import annotations

import os
from pathlib import Path


def data_directory() -> Path:
    configured = os.environ.get("SHNIFTER_DATA_DIR")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise ValueError("SHNIFTER_DATA_DIR must be an absolute directory path")
        return path
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "ShnifterTrader"
