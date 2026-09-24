#!/usr/bin/env python3
"""downloads the five lexical norm databases.

Input:  The network
Output: data/raw/norms/<file> for each source
        and an entry per file in data/raw/norms/norms_manifest.json,
        with url, snapshot, sha256, size and the date we got it


We originally wanted to get the files from the Center for Reading Research site (crr.ugent.be).
However, as of today, 23/09/26 the website is down which is why we used the internet Archive
& Wayback Machine to get the files. We added the exact timestamp and a sha256 hash to make it easier
to verify and retrieve the files. To catch errors, we added minimum byte sizes for each file, so that if the Wayback Machine 
returns an error page instead of the real file, we can detect it and delete it.
We got that minimum size by looking at the actual files once we had downloaded them.

author: Kane

run: python scripts/s03_fetch_norms_kane.py [--force] [--only NAME]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402

WAYBACK = "https://web.archive.org/web/{ts}id_/{url}"
USER_AGENT = "Mozilla/5.0 (DatSci academic project)"


@dataclass(frozen=True)
class NormSource:
    name: str
    filename: str
    original_url: str
    citation: str
    feeds: tuple[str, ...]           # which predictor columns this file feeds into
    wayback_ts: str | None = None    # None means fetch the live url instead
    min_bytes: int = 0               # anything smaller gets treated as a failure
    notes: str = ""

    @property
    def url(self) -> str:
        if self.wayback_ts is None:
            return self.original_url
        return WAYBACK.format(ts=self.wayback_ts, url=self.original_url)


# snapshots resolved and checked against the Wayback CDX API on 2026-09-23.
#
# 'min_bytes' is purposefully a bit lower than the actual (expected) size. The CDX index reports
# the compressed WARC record length, which never matches the real file size,
# so comparing against that number doesn't make sense. 
# We chose the value on smth that actually happened to us; being shown a 200 response with an
# 11 KB error page.
SOURCES: tuple[NormSource, ...] = (
    NormSource(
        name="concreteness",
        filename="Concreteness_ratings_Brysbaert_et_al_BRM.txt",
        original_url="http://crr.ugent.be/papers/Concreteness_ratings_Brysbaert_et_al_BRM.txt",
        citation="Brysbaert, Warriner & Kuperman (2014), Behav Res Methods 46(3), 904-911",
        feeds=("mea_concreteness",),
        wayback_ts="20231115122317",
        min_bytes=1_000_000,
        notes="40k generally known English lemmas.",
    ),
    NormSource(
        name="aoa",
        filename="AoA_51715_words.zip",
        original_url="http://crr.ugent.be/papers/AoA_51715_words.zip",
        citation="Kuperman, Stadthagen-Gonzalez & Brysbaert (2012), Behav Res Methods 44(4), 978-990",
        feeds=("fam_age_of_acquisition", "fam_prevalence"),
        wayback_ts="20221207143117",
        min_bytes=4_000_000,
        notes=(
            "Extended 51,715-word list. Filename is not "
            "'AoA_ratings_Kuperman_et_al_BRM.zip', which is what most "
            "papers cite. But this file also "
            "has the percent-known column we use for prevalence."
        ),
    ),
    NormSource(
        name="warriner",
        filename="Ratings_Warriner_et_al.csv",
        original_url="http://crr.ugent.be/papers/Ratings_Warriner_et_al.csv",
        citation="Warriner, Kuperman & Brysbaert (2013), Behav Res Methods 45(4), 1191-1207",
        feeds=("mea_valence", "mea_arousal"),
        wayback_ts="20130927021105",
        min_bytes=3_000_000,
        notes=(
            "13,915 English lemmas: valence, arousal, dominance. pinned to a "
            "2013 snapshot is semi-on-purpose, later ones returned HTTP 503 or error pages."
        ),
    ),
    NormSource(
        name="subtlex_us",
        filename="SUBTLEX-US_frequency_list_with_PoS_information_final_text_version.zip",
        original_url=(
            "http://crr.ugent.be/papers/"
            "SUBTLEX-US_frequency_list_with_PoS_information_final_text_version.zip"
        ),
        citation="Brysbaert & New (2009), Behav Res Methods 41(4), 977-990",
        feeds=("fam_log_frequency",),
        wayback_ts="20220701004339",
        min_bytes=1_000_000,
        notes="Our main frequency source, wordfreq is the backup and for cross-checking.",
    ),
    NormSource(
        name="prevalence",
        filename="WordprevalencesSupplementaryfilefirstsubmission.xlsx",
        original_url=(
            "http://crr.ugent.be/papers/"
            "WordprevalencesSupplementaryfilefirstsubmission.xlsx"
        ),
        citation="Brysbaert, Mandera, McCormick & Keuleers (2019), Behav Res Methods 51, 467-479",
        feeds=("fam_prevalence",),
        wayback_ts="20230727214006",
        min_bytes=8_000_000,
        notes=(
            "Word prevalence for 62k English lemmas. This is not what we originally "
            "planned to use for prevalence, that was the AoA file's "
            "percent-known column instead, but this is a bit more broad,"
            "so we download it anyway for comparison purposes"
        ),
    ),
)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(source: NormSource, dest: Path) -> None:
    req = urllib.request.Request(source.url, headers={"User-Agent": USER_AGENT})
    tmp = dest.with_suffix(dest.suffix + ".part")
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp, tmp.open("wb") as out:
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
            tmp.replace(dest)
            return
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 503) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            break
        except urllib.error.URLError as exc:
            last = exc
            break
    tmp.unlink(missing_ok=True)
    exc = last
    if isinstance(exc, urllib.error.HTTPError):
        raise RuntimeError(
            f"{source.name}: got HTTP {exc.code} for\n  {source.url}\n"
            f"if this is a Wayback snapshot, it may have been withdrawn. "
            f"look it up again against the CDX API and update the pinned "
            f"timestamp here."
        ) from exc
    raise RuntimeError(f"{source.name}: network error for {source.url}: {exc}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="download again even if we have it")
    ap.add_argument("--only", help="fetch just one source, by name")
    args = ap.parse_args()

    config.require_data_root()
    out_dir = config.DATA_RAW / "norms"
    out_dir.mkdir(parents=True, exist_ok=True)

    sources = SOURCES
    if args.only:
        sources = tuple(s for s in SOURCES if s.name == args.only)
        if not sources:
            sys.exit(f"no source called {args.only!r}. we have: {[s.name for s in SOURCES]}")

    manifest_path = out_dir / "norms_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}

    failures: list[str] = []
    for source in sources:
        dest = out_dir / source.filename
        if dest.is_file() and not args.force:
            print(f"  {source.name:<14} already have it ({dest.stat().st_size:,} bytes)")
        else:
            print(f"  {source.name:<14} downloading ...", flush=True)
            try:
                download(source, dest)
            except RuntimeError as exc:
                print(f"    FAILED: {exc}", file=sys.stderr)
                failures.append(source.name)
                continue

        size = dest.stat().st_size
        if size < source.min_bytes:
            dest.unlink(missing_ok=True)
            print(
                f"    FAILED: got {size:,} bytes, needed at least {source.min_bytes:,}. "
                f"might be an error page instead of real data. Deleted",
                file=sys.stderr,
            )
            failures.append(source.name)
            continue
        digest = sha256_of(dest)
        manifest[source.name] = {
            "filename": source.filename,
            "original_url": source.original_url,
            "fetched_from": source.url,
            "wayback_snapshot": source.wayback_ts,
            "citation": source.citation,
            "feeds": list(source.feeds),
            "bytes": size,
            "sha256": digest,
            "retrieved": date.today().isoformat(),
            "notes": source.notes,
        }
        print(f"    {size:,} bytes, sha256 {digest[:16]}...")

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote manifest to {manifest_path}")

    if failures:
        sys.exit(f"\n{len(failures)} source(s) failed: {failures}")
    print(f"got {len(manifest)}/{len(SOURCES)} norm sources.")


if __name__ == "__main__":
    main()
