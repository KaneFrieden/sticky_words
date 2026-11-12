#!/usr/bin/env python3
"""Check the local data source and output locations before an analysis run."""

#
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402

# first we are reading the raw data in 4mb chunks to avoid overloading the ram.
def md5_of(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

# we are checking the raw data and output locations to make sure they are valid and do not overlap.
def main() -> None:
    output_root = config.require_data_root()
    raw_root = config.DATA_RAW # the raw data location is in the env.sh config

    if config.DATA_RAW_IS_SHARED and (
        raw_root.is_relative_to(output_root)
        or output_root.is_relative_to(raw_root)
    ):
        raise RuntimeError(
            "Oops! The output root seems to overlap the shared raw-data location. Please choose a separate "
            "DATSCI_DATA_ROOT so this run doesn't replace any old results."
        )
    if not raw_root.is_dir():
        raise RuntimeError(f"Hey! Your Raw-data directory is missing: {raw_root}")

    manifest_path = raw_root / "dataset_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Hey! Dataset manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_info = manifest["duolingo_hlr"]
    filename = source_info["filename"]
    if Path(filename).name != filename:
        raise RuntimeError(f"Hey! Invalid filename in dataset manifest: {filename!r}")

    raw_file = raw_root / filename
    if not raw_file.is_file():
        raise RuntimeError(f"Hey! Raw dataset is missing: {raw_file}")
    actual_bytes = raw_file.stat().st_size
    expected_bytes = int(source_info["bytes"])
    if actual_bytes != expected_bytes:
        raise RuntimeError(
            f"Ooops! Your dataset has {actual_bytes:,} bytes; but the manifest says "
            f"{expected_bytes:,}."
        )

    actual_md5 = md5_of(raw_file)
    expected_md5 = source_info["md5"].lower()
    if actual_md5 != expected_md5:
        raise RuntimeError(
            f"Ooops! Your dataset MD5 is {actual_md5}; but the manifest says {expected_md5}."
        )

    print(f"All good! Raw dataset verified: {raw_file}")
    print(f"  bytes: {actual_bytes:,}")
    print(f"  MD5:   {actual_md5}")
    print(f"New intermediate output: {config.DATA_INTERMEDIATE}")
    print(f"New processed output:    {config.DATA_PROCESSED}")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"Input check failed: {exc}") from None
