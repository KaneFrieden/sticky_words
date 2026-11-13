#!/usr/bin/env python3
"""Download the DUOLINGO_HLR dataset from Harvard Dataverse if it is not already present."""

# We are downloading the dataset from Harvard Dataverse, unless it is already present. 
# To ensure file integrity and reproducibility, we are checking the file size and MD5 
# checksum against the publisher's own metadata. And we download first into a temp dir. 
# This should help avoid issues with incomplete downloads or corrupted files.
# We are also creating a manifest file that records the dataset's DOI, version, file ID, URL, 
# size, and checksum, along with the UTC timestamp of verification. 
# This manifest can be used for future reference and verification of the dataset's integrity.

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config  # noqa: E402

# file data & origin
DATASET_DOI = "doi:10.7910/DVN/N8XJME"
DATASET_VERSION = "1.0"
FILENAME = "settles.acl16.learning_traces.13m.csv.gz"
DATAVERSE = "https://dataverse.harvard.edu"
METADATA_URL = (
    f"{DATAVERSE}/api/datasets/:persistentId/versions/{DATASET_VERSION}"
    "?persistentId=doi%3A10.7910%2FDVN%2FN8XJME"
)
HEADERS = {"User-Agent": "DatSci-BeyondExposure/1.0"} # user agent string for Harvard Dataverse API requests
BLOCK_SIZE = 4 * 1024 * 1024


def publisher_metadata() -> dict: # retrieve metadata from the publisher's API to verify the dataset version and checksum
    request = urllib.request.Request(METADATA_URL, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    version = payload["data"]
    if f"{version['versionNumber']}.{version['versionMinorNumber']}" != DATASET_VERSION:
        raise RuntimeError("This is not the version we expected!")
    for entry in version["files"]:
        file_info = entry["dataFile"]
        if file_info["filename"] == FILENAME:
            checksum = file_info["checksum"]
            if checksum["type"].upper() != "MD5":
                raise RuntimeError("The publisher does not provide the expected MD5 checksum!")
            return {"id": file_info["id"], "bytes": int(file_info["filesize"]),
                    "md5": checksum["value"].lower()}
    raise RuntimeError(f"Dataset version {DATASET_VERSION} does not contain {FILENAME}!")


def check_file(path: Path, expected: dict) -> None:
    digest = hashlib.md5()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(BLOCK_SIZE), b""):
            digest.update(block)
    if path.stat().st_size != expected["bytes"] or digest.hexdigest() != expected["md5"]:
        raise RuntimeError(f"Size or checksum does not match Dataverse: {path}!")


def main() -> None:
    config.require_data_root()
    raw = config.DATA_RAW
    if config.DATA_RAW_IS_SHARED or raw.is_symlink(): # if raw data is shared or the raw path is a symlink, we do not want to download or overwrite the dataset
        raise RuntimeError("The raw directory is shared; please use a separate data root for downloads.")
    raw.mkdir(parents=True, exist_ok=True)
    target = raw / FILENAME
    manifest = raw / "dataset_manifest.json"
    if manifest.exists() and not target.is_file(): # if the manifest exists but the dataset file does not, we raise an error to avoid inconsistencies
        raise RuntimeError(f"A manifest already exists without the dataset: {manifest}")

    metadata = publisher_metadata() # we retrieve the metadata from the publisher's API to verify the dataset version and checksum
    download_url = f"{DATAVERSE}/api/access/datafile/{metadata['id']}"
    if target.exists():
        if not target.is_file():
            raise RuntimeError(f"The dataset path is not a file: {target}") # if the target path exists but is not a file, we raise an error
        check_file(target, metadata)
        print(f"Existing dataset matches Dataverse: {target}")
    else:
        with tempfile.TemporaryDirectory(prefix="dataset_download_", dir=raw) as temp: #temporary directory for downloading the dataset to avoid leaving partial files in case of interruption
            temporary_file = Path(temp) / FILENAME
            request = urllib.request.Request(download_url, headers=HEADERS)
            print(f"Downloading {FILENAME} from Dataverse...", flush=True)
            with urllib.request.urlopen(request, timeout=300) as response, temporary_file.open("wb") as output: # we download the dataset in chunks to avoid loading the entire file into memory
                shutil.copyfileobj(response, output, length=BLOCK_SIZE)
            check_file(temporary_file, metadata)
            with temporary_file.open("rb") as source, target.open("xb") as output:
                try:
                    shutil.copyfileobj(source, output, length=BLOCK_SIZE)
                except BaseException:
                    output.close()
                    target.unlink()
                    raise
        print(f"Downloaded and verified: {target}")

    record = { # we create a record for the manifest with the dataset metadata and verification information
        "filename": FILENAME,
        "doi": DATASET_DOI,
        "dataset_version": DATASET_VERSION,
        "file_id": metadata["id"],
        "url": download_url,
        "bytes": metadata["bytes"],
        "md5": metadata["md5"],
        "md5_source": "Harvard Dataverse API",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if manifest.exists(): # if the manifest already exists, we check that it matches the record we just created to avoid inconsistencies
        existing = json.loads(manifest.read_text(encoding="utf-8"))["duolingo_hlr"]
        if any(existing.get(key) != record[key] for key in ("filename", "bytes", "md5")):
            raise RuntimeError(f"Existing manifest does not match Dataverse: {manifest}")
        print(f"Existing manifest matches: {manifest}")
    else:
        with manifest.open("x", encoding="utf-8") as output:
            json.dump({"duolingo_hlr": record}, output, indent=2)
            output.write("\n")
        print(f"Created manifest: {manifest}")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, RuntimeError, ValueError, urllib.error.URLError) as exc:
        raise SystemExit(f"Dataset setup failed: {exc}") from None
