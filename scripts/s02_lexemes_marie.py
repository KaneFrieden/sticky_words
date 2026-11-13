#!/usr/bin/env python3
"""Parse the distinct lexeme descriptions in the selected learning traces."""

# This script reads the filtered learning traces from s01, extracts the distinct lexeme descriptions,
#  and parses them into their components: surface form, lemma, part of speech, and any additional tags. 
# It also counts how many events correspond to each lexeme and generates a report summarizing the parsing results, 
# including counts of special cases like wildcards, prpers, construction tags, and unparsed lexemes. 
# The output is saved in Parquet format for further analysis, and we write a JSON report. 

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config  # noqa: E402

# based on the dataset entries, we are defining regex patterns to parse the lexeme descriptions into their components.
LEXEME_PATTERN = re.compile(r"^(?P<surface>[^/]*)/(?P<lemma>[^<]*)(?P<tags>(?:<[^<>]+>)+)$")
# the format of the lexeme descriptions is like this: boys/boy<n><pl>, with tags describing 
# the part of speech and other features. The regex captures the surface form, lemma, and tags separately.
TAG_PATTERN = re.compile(r"<([^<>]+)>")
WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z'-]*") # a simple pattern to identify valid word lemmas, which start with a letter 
#and may contain letters, hyphens, or apostrophes.


def parse_lexeme(value: str) -> dict: # parse lexeme descriptions into their components and identify special cases like 
    # wildcards (<* >), prpers (an artifical lemma for personal pronouns), construction tags, and unparsed lexemes.
    # Wildcards ares something like: <*sf>/year<n><*numb>, where the concrete word form and numerus is not specified.
    match = LEXEME_PATTERN.fullmatch(value)
    if not match:
        return {
            "surface": None, "lemma": None, "pos": None, "tags": None,
            "is_wildcard": "<*" in value, "is_prpers": False,
            "has_construction_tag": "<@" in value, "is_unparsed": True,
            "is_nonword_lemma": False, "has_no_regular_pos": False, # we don't know if the lemma is a valid word or if the pos is regular, so we set these to False
            "n_grammatical_tags": None, "n_construction_tags": None,
            "n_wildcard_tags": None,
        }

    surface = match.group("surface") # extract the surface form from the matched lexeme description
    lemma = match.group("lemma")  # same for lemma
    tags = TAG_PATTERN.findall(match.group("tags")) # same for tags, into list of strings
    return {
        "surface": surface,
        "lemma": lemma,
        "pos": tags[0],
        "tags": "|".join(tags),
        "is_wildcard": "*" in surface or any(tag.startswith("*") for tag in tags),
        "is_prpers": lemma == "prpers",
        "has_construction_tag": any(tag.startswith("@") for tag in tags),
        "is_unparsed": False,
        "is_nonword_lemma": WORD_PATTERN.fullmatch(lemma) is None, # check if the lemma is a valid word according to the WORD_PATTERN
        "has_no_regular_pos": tags[0].startswith("@"), # check if the part of speech tag is a construction tag, which is not a regular pos
        # count the number of grammatical tags, construction tags, and wildcard tags in the lexeme description
        "n_grammatical_tags": sum(not tag.startswith(("@", "*")) for tag in tags[1:]),
        "n_construction_tags": sum(tag.startswith("@") for tag in tags),
        "n_wildcard_tags": sum(tag.startswith("*") for tag in tags),
    }


def main() -> None:
    config.require_data_root()
    language_pair = f"{config.LEARNING_LANGUAGE}_{config.UI_LANGUAGE}"
    source = config.DATA_INTERMEDIATE / f"traces_{language_pair}.parquet"
    destination = config.DATA_INTERMEDIATE / "lexemes.parquet"
    report_path = config.DATA_INTERMEDIATE / "lexeme_parse_report.json"

    if not source.is_file():
        raise RuntimeError(f"Hey! The s01 subset is missing: {source}")
    if destination.exists() or report_path.exists():
        raise RuntimeError("Oops! An s02 output already exists; choose a fresh output directory.")

    traces = pd.read_parquet(source, columns=["lexeme_id", "lexeme_string"])
    if traces.empty or traces.isna().any().any():
        raise ValueError("The subset is empty or contains missing lexeme IDs or descriptions.")

    lexemes = traces.drop_duplicates().reset_index(drop=True)
    if lexemes["lexeme_id"].duplicated().any():
        raise ValueError("A lexeme ID has more than one description; inspect the input before continuing.")

    parsed = pd.DataFrame([parse_lexeme(value) for value in lexemes["lexeme_string"]])
    lexemes = pd.concat([lexemes, parsed], axis=1)
    counts = traces["lexeme_id"].value_counts()
    lexemes["n_events"] = lexemes["lexeme_id"].map(counts).astype("int64")
    # we filter out the unparsed lexemes to focus on those that were successfully parsed for further analysis.
    parsed_lexemes = lexemes.loc[~lexemes["is_unparsed"]]
    pos_counts = ( # group the parsed lexemes by lemma and part of speech, and count each combination
        parsed_lexemes.groupby(["lemma", "pos"], dropna=False)
        .agg(lexemes=("lexeme_id", "size"), events=("n_events", "sum"))
        .reset_index()
    )
    mixed_lemmas = pos_counts.groupby("lemma")["pos"].nunique()
    mixed_lemmas = mixed_lemmas[mixed_lemmas > 1].index
    mixed_pos = pos_counts[pos_counts["lemma"].isin(mixed_lemmas)]
    mixed_examples = []
    for lemma, group in mixed_pos.groupby("lemma"):
        mixed_examples.append({
            "lemma": lemma,
            "events": int(group["events"].sum()),
            "word_classes": [
                {"tag": row.pos, "lexemes": int(row.lexemes), "events": int(row.events)}
                for row in group.itertuples(index=False)
            ],
        })
    mixed_examples.sort(key=lambda item: (-item["events"], item["lemma"]))

    report = { # report to summ the parsing results
        "n_events": len(traces),
        "n_lexemes": len(lexemes),
        "n_lemmas": int(lexemes["lemma"].nunique()),
        "ids_per_description_max": int(lexemes.groupby("lexeme_string")["lexeme_id"].nunique().max()),
        "marked": {
            name: {"lexemes": int(lexemes[name].sum()), "events": int(lexemes.loc[lexemes[name], "n_events"].sum())}
            for name in ("is_wildcard", "is_prpers", "has_construction_tag",
                         "is_unparsed", "is_nonword_lemma", "has_no_regular_pos")
        },
        "examples": {
            name: lexemes.loc[lexemes[name], "lexeme_string"].head(10).tolist()
            for name in ("is_wildcard", "is_prpers", "has_construction_tag",
                         "is_unparsed", "is_nonword_lemma", "has_no_regular_pos")
        },
        "tag_counts": { # count the number of lexemes and events for each type of tag (grammatical, construction, wildcard) in the parsed lexemes
            name: {
                "lexemes_with_any": int((parsed_lexemes[name] > 0).sum()),
                "events_on_those_lexemes": int(parsed_lexemes.loc[parsed_lexemes[name] > 0, "n_events"].sum()),
            }
            for name in ("n_grammatical_tags", "n_construction_tags", "n_wildcard_tags")
        },
        "multiple_word_classes": {
            "n_lemmas": len(mixed_lemmas),
            "examples_by_event_count": mixed_examples[:20],
        },
    }

    with tempfile.TemporaryDirectory(prefix="s02_", dir=config.DATA_INTERMEDIATE) as temp:
        temp_table = Path(temp) / destination.name
        temp_report = Path(temp) / report_path.name
        lexemes.to_parquet(temp_table, index=False)
        temp_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        temp_table.replace(destination)
        temp_report.replace(report_path)

    print(f"Parsed {len(lexemes):,} lexemes from {len(traces):,} events.")
    print(f"Saved: {destination}\nSaved: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"Lexeme parsing failed: {exc}") from None
