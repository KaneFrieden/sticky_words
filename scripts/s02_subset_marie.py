#!/usr/bin/env python3
"""cuts the learning traces down to the population we actually study.

input:  
output:

author: Marie

run: python scripts/s02_subset_marie.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402


def main() -> None:
    config.require_data_root()
    # TODO: fill this in
    raise NotImplementedError("not written yet")


if __name__ == "__main__":
    main()
