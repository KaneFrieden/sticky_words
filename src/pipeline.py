"""Shared pipeline pieces, imported by the scripts.

Code from here is used by more than one script, so that any re-runs later (e.g., the robustness check for other language pairs) run the same code
and don't drift
"""

from __future__ import annotations

import re

LEXEME_RE = re.compile(r"^(?P<surface>.*?)/(?P<lemma>[^<]*)(?P<tags><.*>)$")
TAG_RE = re.compile(r"<([^>]*)>")
# filters out instances of `'s`, etc.
WORD_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]*$")

# duolingo placeholder that looks like a words
PLACEHOLDER_LEMMAS = {"prpers"}


def parse_one(s: str) -> dict | None:
    """Parses one lexeme_string and returns None if it does not match the format."""
    m = LEXEME_RE.match(s)
    if not m:
        return None
    tags = TAG_RE.findall(m.group("tags"))
    if not tags:
        return None

    pos, rest = tags[0], tags[1:]

    # since wildcards appear both as tags ( e.g., <*numb>) and as the surface form
    # (e.g., <*sf>/motor<n><*numb>), both get checked here; this is relevant for tasks where no sentence fixes the form (e.g., word matching)
    wildcards = [t for t in tags if t.startswith("*")]
    if "*" in m.group("surface"):
        wildcards.append("*sf")

    # <@...> denotes the syntactic construction the item was in (e.g., <@future_phrasal> for `going to eat`)
    construction = [t for t in rest if t.startswith("@")]
    modifiers = [t for t in rest if not t.startswith("@") and not t.startswith("*")]

    return {
        "surface": m.group("surface"),
        "lemma": m.group("lemma"),
        "pos": pos,
        "tags": "|".join(tags),
        "n_modifiers": len(modifiers),
        "n_construction_tags": len(construction),
        "is_wildcard": bool(wildcards),
        "wildcard_tags": "|".join(sorted(set(wildcards))),
        # kept distinct from instances the norm db does not cover, as to keep 
        # the properties of the Duolingo encoding, and the coverage of the norm dbs separate as causes for exclusion
        "is_placeholder_lemma": (
            m.group("lemma") in PLACEHOLDER_LEMMAS
            or not WORD_RE.match(m.group("lemma") or "")
        ),
        # <@...> on first position means that the entry carries no real word class
        "has_real_pos": not pos.startswith("@"),
    }
