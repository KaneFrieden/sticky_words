"""Configuration for the datsci project.
This module defines the project root and data directories, and provides a function to
require that the data root is valid. The data root can be configured via environment
variables, and the module checks for the presence of a marker file to ensure that the
data root is valid."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def configured_path(variable: str, default: Path) -> Path:
    value = os.environ.get(variable)
    return Path(value).expanduser().resolve() if value else default


DATA_ROOT_IS_EXTERNAL = bool(os.environ.get("DATSCI_DATA_ROOT"))
DATA_ROOT = configured_path("DATSCI_DATA_ROOT", PROJECT_ROOT / "data")

DATA_RAW_IS_SHARED = bool(os.environ.get("DATSCI_RAW_ROOT"))
DATA_RAW = configured_path("DATSCI_RAW_ROOT", DATA_ROOT / "raw")

DATA_INTERMEDIATE = DATA_ROOT / "intermediate"
DATA_PROCESSED = DATA_ROOT / "processed"
DATA_ROOT_MARKER = ".datsci-data-root"


def require_data_root() -> Path:
    if not DATA_ROOT_IS_EXTERNAL:
        return DATA_ROOT
    if not DATA_ROOT.is_dir():
        raise RuntimeError(f"External data root is missing: {DATA_ROOT}")
    if not (DATA_ROOT / DATA_ROOT_MARKER).is_file():
        raise RuntimeError(
            f"External data root has no {DATA_ROOT_MARKER} marker: {DATA_ROOT}"
        )
    return DATA_ROOT
