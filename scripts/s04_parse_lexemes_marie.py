#!/usr/bin/env python3
"""splits lexeme_string into its parts: lemma, part of speech, tags; reduces the 3641179 practise events to unique lexemes

input: data/intermediate/traces_en_es.parquet
output: data/intermediate/lexemes.parquet
        data/intermediate/lexemes_report.json
        

author: Marie

run: python scripts/s04_parse_lexemes_marie.py
"""

from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config, pipeline  # noqa: E402


def main() -> None:
    config.require_data_root()
    src = config.DATA_INTERMEDIATE / "traces_en_es.parquet"
    if not src.is_file():
        sys.exit(f"missing {src}. run scripts/s02_subset_marie.py first")

    # 3641179 events, but less distinct lexeme strings and we parse each one once
    traces = pd.read_parquet(src, columns=["lexeme_id", "lexeme_string"])
    lex = traces.drop_duplicates("lexeme_id").reset_index(drop=True)
    n_events = len(traces)

    parsed = [pipeline.parse_one(s) for s in lex["lexeme_string"]]
    failed = [s for s, p in zip(lex["lexeme_string"], parsed) if p is None]
    if failed:
        sys.exit(
            f"{len(failed)} lexeme string(s) failed to parse and did not match the expected format. "
            f"E.g., \n " + "\n ".join(failed[:5])
        )

    lex = pd.concat([lex, pd.DataFrame(parsed)], axis=1)

    # tally of how many events exclusion of wildcards costs
    ev = traces.merge(lex[["lexeme_id", "lemma", "is_wildcard"]], on="lexeme_id")
    wild_lex = lex[lex.is_wildcard]
    clean_lex = lex[~lex.is_wildcard]
                    
    lost_lemmas = sorted(set(wild_lex.lemma) - set(clean_lex.lemma))
    events_on_wild = int(ev.is_wildcard.sum())
    events_on_lost = int(ev[ev.lemma.isin(lost_lemmas)].shape[0])
                         
    # same for placeholder lemmas
    placeholders = lex[lex.is_placeholder_lemma]
    events_on_placeholders = int(ev.lemma.isin(set(placeholders.lemma)).sum())

    wildcard_kinds = wild_lex["wildcard_tags"].str.split("|").explode().value_counts()

    report = {
        "n_lexemes": len(lex),
        "n_lemmas": int(lex.lemma.nunique()),
        "n_events": n_events,
        "wildcards": {
            "n_lexemes": len(wild_lex),
            "share_of_lexemes": len(wild_lex) / len(lex),
            "kinds": {k: int(v) for k, v in wildcard_kinds.items()},
            "events_on_wildcard_lexemes": events_on_wild,
            "share_of_events": events_on_wild / n_events,
            "lemmas_only_ever_wildcard": len(lost_lemmas),
            "events_on_those_lemmas": events_on_lost,
            "examples_lost": lost_lemmas[:15],
        },
        "placeholder_lemmas": {
            "n_lexemes": len(placeholders),
            "lemmas": sorted(placeholders.lemma.unique().tolist()),
            "events": events_on_placeholders,
            "share_of_events": events_on_placeholders / n_events,
            "note": "encoding artefacts, NOT norm-coverage failures",
        },
        "n_lemmas_after_dropping_wildcards": int(clean_lex.lemma.nunique()),
        "lexemes_without_real_pos": int((~lex.has_real_pos).sum()),
        "pos_distribution": {k: int(v) for k, v in lex.pos.value_counts().items()},
        "modifiers": {
            "mean": float(lex.n_modifiers.mean()),
            "max": int(lex.n_modifiers.max()),
            "distribution": {str(k): int(v)
                             for k, v in lex.n_modifiers.value_counts().sort_index().items()},
        },
        "construction_tags": {
            "n_lexemes_with_any": int((lex.n_construction_tags > 0).sum()),
            "max": int(lex.n_construction_tags.max()),
        },
    }

    dest = config.DATA_INTERMEDIATE / "lexemes.parquet"
    lex.to_parquet(dest, index=False)
    (config.DATA_INTERMEDIATE / "lexemes_report.json").write_text(
        json.dumps(report, indent=2) + "\n")

    w = report["wildcards"]
    p = report["placeholder_lemmas"]
    print(f"lexemes parsed     {len(lex):,}  (0 failures)")
    print(f"distinct lemmas    {report['n_lemmas']:,}")
    print(f"\nwildcards: {len(wild_lex):,} lexemes ({w['share_of_lexemes']:.1%}), "
          f"kinds {w['kinds']}")
    print(f"  events on them   {events_on_wild:,} ({w['share_of_events']:.1%})")
    print(f"  lemmas lost      {len(lost_lemmas)} ({events_on_lost:,} events)")
    print(f"  lemmas remaining {report['n_lemmas_after_dropping_wildcards']:,}")
    print(f"\nplaceholder lemmas {p['lemmas']}  "
          f"{p['events']:,} events ({p['share_of_events']:.2%})")
    print(f"\nPoS distribution   {report['pos_distribution']}")
    print(f"modifiers          mean {report['modifiers']['mean']:.2f}  "
          f"max {report['modifiers']['max']}  dist {report['modifiers']['distribution']}")
    print(f"\nwritten to {dest}")


if __name__ == "__main__":
    main()
