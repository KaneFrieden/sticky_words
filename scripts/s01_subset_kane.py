#!/usr/bin/env python3
"""Select English-learning sessions with a Spanish interface."""

# In this file we first read the raw dataset in chunks, then filter for the selected language pair (en-es),
# and finally write the filtered data to a Parquet file.
# We also generate a report with summary statistics about our selected subset.
# We are reading the dataset in chunks to again avoid overloading the RAM, and we are using a temporary directory to store intermediate files
# before moving them to the final output location.


from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config  # noqa: E402

RAW_FILE = "settles.acl16.learning_traces.13m.csv.gz" # we are using the settles dataset
CHUNK_SIZE = 500_000 # we are reading the raw dataset in chunks of 500,000 rows
SECONDS_PER_DAY = 86_400 # there are 86,400 seconds in a day

DTYPES = { # we are defining the data types for each selected column in the raw dataset to ensure correct reading and processing.
    "timestamp": "int64",
    "delta": "int64",
    "user_id": "string",
    "learning_language": "string",
    "ui_language": "string",
    "lexeme_id": "string",
    "lexeme_string": "string",
    "history_seen": "int64",
    "history_correct": "int64",
    "session_seen": "int64",
    "session_correct": "int64",
}

# We are defining the output columns for the filtered dataset, excluding the language columns since they are constant for our selected subset.
OUTPUT_COLUMNS = [name for name in DTYPES if name not in ("learning_language", "ui_language")]


def main() -> None:
    config.require_data_root() # we are checking that the data root is valid and accessible
    source = config.DATA_RAW / RAW_FILE
    if not source.is_file():
        raise RuntimeError(f"Hey! The raw dataset is missing: {source}")

    output_dir = config.DATA_INTERMEDIATE # we are defining the output directory for the filtered data and report
    language_pair = f"{config.LEARNING_LANGUAGE}_{config.UI_LANGUAGE}" # defining the language pair
    table_path = output_dir / f"traces_{language_pair}.parquet"
    report_path = output_dir / "subset_report.json"
    if table_path.exists() or report_path.exists(): # we are checking if the output files already exist to avoid overwriting them
        raise RuntimeError("Oops! A subset output already exists; choose a fresh output directory.")
    output_dir.mkdir(parents=True, exist_ok=True) # we are creating the output directory if it doesn't exist

    rows_total = 0 # we are initializing counters and containers for the summary statistics
    rows_selected = 0
    learners: set[str] = set()
    lexemes: set[str] = set()
    lag_parts: list[np.ndarray] = []
    attempts = 0
    correct = 0

    # Write the outputs to temporary files first, so an interrupted run
    # does not leave a partial file at the final output path.

    with tempfile.TemporaryDirectory(prefix="s01_", dir=output_dir) as temp: # temp directory for intermediate files
        temp_table = Path(temp) / table_path.name
        temp_report = Path(temp) / report_path.name
        writer = None
        try: # reading the chunks
            chunks = pd.read_csv(source, usecols=list(DTYPES), dtype=DTYPES, chunksize=CHUNK_SIZE)
            for chunk in chunks:
                rows_total += len(chunk)
                mask = (chunk["learning_language"] == config.LEARNING_LANGUAGE) & (chunk["ui_language"] == config.UI_LANGUAGE)
                selected = chunk.loc[mask, OUTPUT_COLUMNS].copy()
                if selected.empty:
                    continue
                 # We keep all time intervals here so we can look at their distribution
                 # before then applying the minimum-lag threshold in a later step.
                selected["delta_days"] = selected["delta"] / SECONDS_PER_DAY # we are converting the delta from seconds to days for easier interpretation
                rows_selected += len(selected)
                learners.update(selected["user_id"].dropna().tolist())
                lexemes.update(selected["lexeme_id"].dropna().tolist())
                lag_parts.append(selected["delta_days"].to_numpy(copy=True))
                attempts += int(selected["session_seen"].sum())
                correct += int(selected["session_correct"].sum())

                table = pa.Table.from_pandas(selected, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(temp_table, table.schema)
                writer.write_table(table)
                print(f"Rows read: {rows_total:,}; selected: {rows_selected:,}", flush=True)
        finally:
            if writer is not None:
                writer.close()

        if rows_selected == 0:
            raise RuntimeError("Oops! No sessions matched the selected language pair.")

        lags = np.concatenate(lag_parts) # we are concatenating the lag arrays from all chunks to compute summary statistics
        report = { # reporting the summary statistics about the selected subset
            "learning_language": config.LEARNING_LANGUAGE,
            "ui_language": config.UI_LANGUAGE,
            "rows_total_raw": rows_total,
            f"rows_{language_pair}": rows_selected,
            "share_of_raw": rows_selected / rows_total,
            "distinct_learners": len(learners),
            "distinct_lexemes": len(lexemes),
            "lag_days": { # summary statistics about the lag in days between sessions
                "min": float(lags.min()),
                "median": float(np.median(lags)),
                "max": float(lags.max()),
                "rows_below_one_day": int((lags < 1).sum()),
                "rows_at_or_above_one_day": int((lags >= 1).sum()),
            },
            "session_attempts": attempts,
            "session_correct": correct,
            "recall_rate": correct / attempts if attempts else None, # recall rate = amount of correct attempts / total attempts
        }
        temp_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8") # JSON file
        temp_table.replace(table_path)
        temp_report.replace(report_path)

    print(f"Finished: {rows_selected:,} of {rows_total:,} rows selected.")
    print(f"Saved: {table_path}")
    print(f"Saved: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"Subset failed: {exc}") from None
