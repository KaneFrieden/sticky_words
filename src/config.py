"""Centralized config: paths, seeds, thresholds, predictor-block naming and constants.
Every pipeling script imports from here for easier adjustment of constants.
To avoid invented defaults, values that are left open at first are set to ``UNDECIDED``.
"""
from __future__ import annotations

import os
from pathlib import Path

# Paths; safeguard for external drives
PROJECT_ROOT = Path(__file__).resolve().parents[1]

_DATA_ROOT_ENV = os.environ.get("DATSCI_DATA_ROOT")
DATA_ROOT_IS_EXTERNAL = bool(_DATA_ROOT_ENV)
DATA_ROOT = (
    Path(_DATA_ROOT_ENV).expanduser().resolve()
    if _DATA_ROOT_ENV
    else PROJECT_ROOT / "data"
)

DATA_RAW = DATA_ROOT / "raw"
DATA_INTERMEDIATE = DATA_ROOT / "intermediate"
DATA_PROCESSED = DATA_ROOT / "processed"
FIGURES = PROJECT_ROOT / "figures"
DOCS = PROJECT_ROOT / "docs"

# must exist in external (drive) data root, otherwise drive is not mounted
DATA_ROOT_MARKER = ".datsci-data-root"


def require_data_root() -> Path:
    if not DATA_ROOT_IS_EXTERNAL:
        return DATA_ROOT

    if not DATA_ROOT.exists():
        raise RuntimeError(
            f"DATSCI_DATA_ROOT points at {DATA_ROOT}, which does not exist. "
            f"The external drive is probably not mounted."
        )
    if not (DATA_ROOT / DATA_ROOT_MARKER).is_file():
        raise RuntimeError(
            f"{DATA_ROOT} exists but has no {DATA_ROOT_MARKER} marker. "
            f"It was probably recreated on the internal disk while the drive "
            f"was unplugged. Remove it and remount the drive."
        )
    return DATA_ROOT

# Reproducibility const
RANDOM_SEED = 20260831
N_BOOTSTRAP = 2000
N_CV_FOLDS = 10

# Sentinel value for values left open at first
class _Undecided:
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNDECIDED"

    def __bool__(self) -> bool:
        raise RuntimeError(
            "An UNDECIDED config value was used in a boolean context. "
            "Decide it and record the decision in docs/deviations.md."
        )


UNDECIDED = _Undecided()


def require_decided(value, name: str, where: str):
    if isinstance(value, _Undecided):
        raise RuntimeError(
            f"config.{name} is still UNDECIDED but is required by {where}. "
            f"It must be set from the data and recorded in docs/deviations.md."
        )
    return value

# Scope filters
LEARNING_LANGUAGE = "en"
UI_LANGUAGE = "es"

# Provisional thresholds
MIN_LAG_DAYS = 1.0
MIN_OBS_PER_ITEM = 200

# Reference points for retention level; set later from the filtered data
REFERENCE_HISTORY_SEEN = UNDECIDED
REFERENCE_LAG_DAYS = UNDECIDED

# Predictor blocks
BLOCK_PREFIXES = {
    "exposure": "exp_",
    "pos": "pos_",
    "familiarity": "fam_",
    "meaning": "mea_",
    "form": "frm_",
    "transfer": "trn_",
}

CONTROL_BLOCKS = ("exposure", "pos")
INTEREST_BLOCKS = ("familiarity", "meaning", "form", "transfer")

PREDICTOR_COLUMNS = {
    "exposure": [
        "exp_log1p_history_seen",
        "exp_log1p_history_correct",
        "exp_log1p_history_wrong",
        "exp_n_distinct_learners",
        "exp_median_history_seen_at_first",
        "exp_mean_session_seen",
    ],
    "pos": ["pos_dominant"],
    "familiarity": ["fam_log_frequency", "fam_age_of_acquisition", "fam_prevalence"],
    "meaning": ["mea_concreteness", "mea_semantic_density", "mea_valence", "mea_arousal"],
    "form": [
        "frm_length_chars",
        "frm_length_syllables",
        "frm_letters_per_phoneme",
        "frm_n_inflectional_modifiers",
    ],
    "transfer": ["trn_norm_levenshtein_es"],
}


def block_of(column: str) -> str | None:
    for block, prefix in BLOCK_PREFIXES.items():
        if column.startswith(prefix):
            return block
    return None


def columns_for(*blocks: str, standardised: bool = False) -> list[str]:
    unknown = set(blocks) - set(PREDICTOR_COLUMNS)
    if unknown:
        raise KeyError(f"Unknown predictor block(s): {sorted(unknown)}")
    out: list[str] = []
    for block in blocks:
        for col in PREDICTOR_COLUMNS[block]:
            if standardised and block != "pos":
                out.append(f"{col}_z")
            else:
                out.append(col)
    return out
