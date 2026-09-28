#!/usr/bin/env python3
"""cuts the learning traces down to the population we actually study (es-speakers learning en).

input: data/raw/settles.acl16.learning_traces.13m.csv.gz
output:data/intermediate/traces_en_es.parquet 
       data/intermediate/subset_report.json

author: Marie

run: python scripts/s02_subset_marie.py
"""

from __future__ import annotations

import sys
from pathlib import Path
import json
import pandas as pd

RAW_NAME = "settles.acl16.learning_traces.13m.csv.gz"
CHUNK_SIZE = 1000000

DATA_TYPES = { # avoids differences in dtype between chunks
    "p_recall": "float32",
    "timestamp": "int64",
    "delta": "int64",
    "user_id": "string",
    "learning_language": "category",
    "ui_language": "category",
    "lexeme_id": "string",
    "lexeme_string": "string",
    "history_seen": "int32",
    "history_correct": "int32",
    "session_seen": "int32",
    "session_correct": "int32",
}

# p_recall is easily recomputable, and the two language-cols are constant post-filtering anyway, so no need to keep them
KEEP = [
    "timestamp", "delta", "user_id", "lexeme_id", "lexeme_string",
    "history_seen", "history_correct", "session_seen", "session_correct",
]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402


def main() -> None:
    config.require_data_root()
    src = config.DATA_RAW / RAW_NAME
    if not src.is_file():
        sys.exit(f"missing {src}. run scripts/s01_fetch_dataset_kane.py first")

    kept: list[pd.DataFrame] = []
    n_total = 0
    ui_counts: dict[str, int] = {}   # comped in advance, for the second-L1 rerun later

    print(f"reading {src.name} in {CHUNK_SIZE:,}-row chunks", flush=True)
    reader = pd.read_csv(src, dtype=DATA_TYPES, chunksize=CHUNK_SIZE, compression="gzip")
    for i, chunk in enumerate(reader, 1):
        n_total += len(chunk)
        en = chunk[chunk["learning_language"] == config.LEARNING_LANGUAGE]
        for ui, n in en["ui_language"].value_counts().items():
            ui_counts[str(ui)] = ui_counts.get(str(ui), 0) + int(n)
        sub = en[en["ui_language"] == config.UI_LANGUAGE]
        if len(sub):
            kept.append(sub[KEEP].copy())
        print(f"\r chunk {i}: {n_total:,} rows read", end="", flush=True)
    print()

    df = pd.concat(kept, ignore_index=True)
    df["delta_days"] = df["delta"] / 86400.0

    lag = df["delta_days"]
    quantiles = [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    above_cutoff = lag >= config.MIN_LAG_DAYS

    report = {
        "rows_total_raw": n_total,
        "rows_en_es": len(df),
        "share_of_raw": len(df) / n_total,
        "distinct_learners": int(df["user_id"].nunique()),
        "distinct_lexemes": int(df["lexeme_id"].nunique()),
        "ui_languages_learning_en": dict(
            sorted(ui_counts.items(), key=lambda kv: -kv[1])
        ),
        "lag_days": {
            "min": float(lag.min()),
            "max": float(lag.max()),
            "mean": float(lag.mean()),
            "median": float(lag.median()),
            "quantiles": {str(p): float(lag.quantile(p)) for p in quantiles},
            "zero_or_negative": int((lag <= 0).sum()),
        },
        # this is just a figure, and not applied, as 1-day threshold is provisional
        "provisional_min_lag_days": config.MIN_LAG_DAYS,
        "rows_at_or_above_min_lag": int(above_cutoff.sum()),
        "share_at_or_above_min_lag": float(above_cutoff.mean()),
        # the median is unfiltered
        "exposure_history_seen": {
            "median": float(df["history_seen"].median()),
            "mean": float(df["history_seen"].mean()),
            "quantiles": {str(p): float(df["history_seen"].quantile(p)) for p in quantiles},
        },
        "recall": {
            "mean_session_correct_rate": float(
                df["session_correct"].sum() / df["session_seen"].sum()
            ),
            "mean_session_seen": float(df["session_seen"].mean()),
        },
    }

    dest = config.DATA_INTERMEDIATE / "traces_en_es.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dest, index=False)
    (config.DATA_INTERMEDIATE / "subset_report.json").write_text(
        json.dumps(report, indent=2) + "\n")

    print(f"raw rows: {n_total:,}")
    print(f"en/es-paired rows: {len(df):,}  ({len(df) / n_total:.2%} of raw data)")
    print(f"distinct learners: {df['user_id'].nunique():,}")
    print(f"distinct lexemes: {df['lexeme_id'].nunique():,}")


if __name__ == "__main__":
    main()
