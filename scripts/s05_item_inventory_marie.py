#!/usr/bin/env python3
"""builds the lemma-level item inventory (one row/lemma, see docs/item_table_contract.md), and collapses the events.

input: data/intermediate/traces_en_es.parquet
       data/intermediate/lexemes.parquet
output: data/intermediate/item_inventory.parquet
        data/intermediate/events_analysis.parquet
        data/intermediate/inventory_report.json

author: Marie

run: python scripts/s05_item_inventory_marie.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402


def main() -> None:
    config.require_data_root()
    traces_path = config.DATA_INTERMEDIATE / "traces_en_es.parquet"
    lex_path = config.DATA_INTERMEDIATE / "lexemes.parquet"
    for p, script in ((traces_path, "s02_subset_marie.py"),
                      (lex_path, "s04_parse_lexemes_marie.py")):
        if not p.is_file():
            sys.exit(f"missing {p}. run scripts/{script} first")

    traces = pd.read_parquet(traces_path)
    lex = pd.read_parquet(lex_path)

    ev = traces.merge(
        lex[["lexeme_id", "lemma", "pos", "n_modifiers", "is_wildcard",
             "is_placeholder_lemma"]],
        on="lexeme_id", how="left",
    )
    if ev["lemma"].isna().any():
        sys.exit(f"{ev['lemma'].isna().sum()} events did not join to a lexeme")

    n0 = len(ev)
    steps = [("start", n0)]
    ev = ev[~ev.is_wildcard]
    steps.append(("after dropping wildcard lexemes", len(ev)))
    ev = ev[~ev.is_placeholder_lemma]
    steps.append(("after dropping placeholder lemmas", len(ev)))

    # curriculum posn is computed pre-lag filter, because it describes
    # where a word is situatred in the course, not what the retention sample looks like
    first_idx = ev.groupby(["user_id", "lemma"], observed=True)["timestamp"].idxmin()
    curriculum = (
        ev.loc[first_idx, ["lemma", "history_seen"]]
        .groupby("lemma", observed=True)["history_seen"]
        .median()
        .rename("exp_median_history_seen_at_first")
    )

    analysis_events = ev[ev.delta_days >= config.MIN_LAG_DAYS].copy()
    steps.append((f"after lag >= {config.MIN_LAG_DAYS} day(s)", len(analysis_events)))

    analysis_events["history_wrong"] = analysis_events["history_seen"] - analysis_events["history_correct"]

    g = analysis_events.groupby("lemma", observed=True)
    inventory = pd.DataFrame({
        "n_events": g.size(),
        "n_lexemes": g["lexeme_id"].nunique(),
        "exp_n_distinct_learners": g["user_id"].nunique(),
        # log1p before averaging, since exposure counts are skewed
        "exp_log1p_history_seen": g["history_seen"].apply(lambda s: np.log1p(s).mean()),
        "exp_log1p_history_correct": g["history_correct"].apply(lambda s: np.log1p(s).mean()),
        "exp_log1p_history_wrong": g["history_wrong"].apply(lambda s: np.log1p(s).mean()),
        "exp_mean_session_seen": g["session_seen"].mean(),
        "frm_n_inflectional_modifiers": g["n_modifiers"].mean(),
        "session_seen_total": g["session_seen"].sum(),
        "session_correct_total": g["session_correct"].sum(),
        "median_lag_days": g["delta_days"].median(),
        "min_lag_days": g["delta_days"].min(),
        "max_lag_days": g["delta_days"].max(),
        "n_distinct_lags": g["delta_days"].nunique(),
    })

    # dominant part of speech  plus share (0-1), so lemmas with different PoS stay visible
    pos_counts = analysis_events.groupby(["lemma", "pos"], observed=True).size().rename("n")
    pos_share = pos_counts / pos_counts.groupby("lemma", observed=True).transform("sum")
    dominant = (pos_share.rename("share").reset_index()
                .sort_values("share", ascending=False)
                .drop_duplicates("lemma"))

    inventory = inventory.join(dominant.set_index("lemma")[["pos", "share"]]).rename(
        columns={"pos": "pos_dominant", "share": "pos_dominant_share"})
    inventory = inventory.join(curriculum)
    inventory["recall_rate"] = inventory.session_correct_total / inventory.session_seen_total
    inventory = inventory.reset_index()

    enough = inventory.n_events >= config.MIN_OBS_PER_ITEM
    split_pos = inventory.pos_dominant_share < 0.8

    report = {
        "filter_chain": [{"step": s, "events": n} for s, n in steps],
        "events_start": n0,
        "events_analysis": len(analysis_events),
        "share_retained": len(analysis_events) / n0,
        "n_lemmas": len(inventory),
        "n_lemmas_at_min_obs": int(enough.sum()),
        "min_obs_per_item": config.MIN_OBS_PER_ITEM,
        "min_lag_days": config.MIN_LAG_DAYS,
        "events_in_qualifying_lemmas": int(inventory.loc[enough, "n_events"].sum()),
        "pos_dominance": {
            "lemmas_below_0.8_dominant": int(split_pos.sum()),
            "share": float(split_pos.mean()),
            "examples": inventory.loc[split_pos, "lemma"].head(10).tolist(),
        },
        "pos_distribution_at_min_obs": {
            k: int(v) for k, v in inventory.loc[enough, "pos_dominant"].value_counts().items()
        },
        "recall_rate": {
            "mean": float(inventory.loc[enough, "recall_rate"].mean()),
            "min": float(inventory.loc[enough, "recall_rate"].min()),
            "max": float(inventory.loc[enough, "recall_rate"].max()),
        },
        "lags_per_item_at_min_obs": {
            "median_distinct_lags": float(inventory.loc[enough, "n_distinct_lags"].median()),
            "min_distinct_lags": int(inventory.loc[enough, "n_distinct_lags"].min()),
        },
    }

    inventory.to_parquet(config.DATA_INTERMEDIATE / "item_inventory.parquet", index=False)
    analysis_events.to_parquet(config.DATA_INTERMEDIATE / "events_analysis.parquet", index=False)
    (config.DATA_INTERMEDIATE / "inventory_report.json").write_text(
        json.dumps(report, indent=2) + "\n")

    print("filter sequence:")
    for s, n in steps:
        print(f"{s:<38} {n:>10,} ({n / n0:6.1%})")
    print(f"\nlemmas {len(inventory):,}")
    print(f"lemmas with >= {config.MIN_OBS_PER_ITEM} events {int(enough.sum()):,}")
    print(f"events in those lemmas {report['events_in_qualifying_lemmas']:,}")
    print(f"\nPoS split (<80% dominant): {int(split_pos.sum())} lemmas "
          f"({split_pos.mean():.1%})  e.g., {report['pos_dominance']['examples'][:5]}")
    print(f"recall rate across items: mean {report['recall_rate']['mean']:.4f}")
    print(f"PoS at items that clear min-obs: {report['pos_distribution_at_min_obs']}")


if __name__ == "__main__":
    main()
