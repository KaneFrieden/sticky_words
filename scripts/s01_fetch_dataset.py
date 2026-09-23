#!/usr/bin/env python3
"""downloads the Duolingo Half-Life Regression dataset.

input: nothing, just the network
output: data/raw/settles.acl16.learning_traces.13m.csv.gz
        and an entry in data/raw/dataset_manifest.json

We neither modify the raw file nor commit it (379 MB). 
All of our subsets are produced by code from it, to maintain reproducibility.

For integrity, we look again at the publisher's own md5, taken live from the 
Dataverse API. This way we can detect a truncated or substituted download.



run: python scripts/s01_fetch_dataset.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402

DOI = "doi:10.7910/DVN/N8XJME"
API = "https://dataverse.harvard.edu/api"
FILENAME = "settles.acl16.learning_traces.13m.csv.gz"
CITATION = "Settles & Meeder (2016), ACL 2016, 1848-1858"
# the default urllib user agent gets a 403 from Dataverse, so 
# we pretend to be a browser
HEADERS = {"User-Agent": "Mozilla/5.0 (DatSci academic project)"}


def dataverse_metadata() -> dict:
    url = f"{API}/datasets/:persistentId/?persistentId={DOI}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    for f in data["data"]["latestVersion"]["files"]:
        df = f["dataFile"]
        if df["filename"] == FILENAME:
            return df
    raise RuntimeError(f" {FILENAME} not in Dataverse record for {DOI}")


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    config.require_data_root()
    dest = config.DATA_RAW / FILENAME
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"look up {DOI} ...", flush=True)
    meta = dataverse_metadata()
    expected_md5 = meta["md5"]
    expected_size = meta["filesize"]
    url = f"{API}/access/datafile/{meta['id']}"
    print(f"  {FILENAME}: {expected_size:,} bytes, md5 {expected_md5}")

    if dest.is_file() and dest.stat().st_size == expected_size:
        print("same size file already exists", flush=True)
    else:
        print(f"downloading here: {dest}", flush=True)
        req = urllib.request.Request(url, headers=HEADERS)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(req, timeout=300) as resp, tmp.open("wb") as out:
            done = 0
            while chunk := resp.read(1 << 22):
                out.write(chunk)
                done += len(chunk)
                pct = 100 * done / expected_size if expected_size else 0
                print(f"\r  {done / 1e6:.0f} / {expected_size / 1e6:.0f} MB ({pct:.1f}%)",
                      end="", flush=True)
        print()
        tmp.replace(dest)

    size = dest.stat().st_size
    print("check for integrity", flush=True)
    actual = md5_of(dest)
    if actual != expected_md5 or size != expected_size:
        dest.unlink(missing_ok=True)
        sys.exit(
            f"file did not match expectations\n"
            f"  size: got {size:,}, expected {expected_size:,}\n"
            f"  md5:  got {actual}, expected {expected_md5}\n"
            f"try running this again. if it fails a second time, the published "
            f"file itself may have changed"
        )
    print(f"md5 matches: {actual}")

    mpath = config.DATA_RAW / "dataset_manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.is_file() else {}
    manifest["duolingo_hlr"] = {
        "filename": FILENAME,
        "doi": DOI,
        "url": url,
        "citation": CITATION,
        "bytes": size,
        "md5": actual,
        "md5_source": "Harvard Dataverse API",
        "license": "CC-BY",
        "retrieved": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    mpath.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote manifest to {mpath}")


if __name__ == "__main__":
    main()
