# A quick check for our config.py file

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config as c  # noqa: E402

def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    checks: list[str] = []

    # does each block have a prefix, and vice versa?
    if set(c.PREDICTOR_COLUMNS) != set(c.BLOCK_PREFIXES):
        fail(
            "predictor columns and block prefixes disagree: "
            f"{set(c.PREDICTOR_COLUMNS) ^ set(c.BLOCK_PREFIXES)}"
        )
    checks.append(f"{len(c.PREDICTOR_COLUMNS)} blocks, prefixes consistent")

    # does every column have the right prefix?
    for block, cols in c.PREDICTOR_COLUMNS.items():
        prefix = c.BLOCK_PREFIXES[block]
        for col in cols:
            if not col.startswith(prefix):
                fail(f"column {col!r} is in block {block!r} but lacks prefix {prefix!r}")
            if c.block_of(col) != block:
                fail(f"block_of({col!r}) returned {c.block_of(col)!r}, expected {block!r}")
    checks.append("all columns have the right prefix")   

    # are there any duplicate column names across blocks?
    allcols = [col for cols in c.PREDICTOR_COLUMNS.values() for col in cols]
    dupes = {col for col in allcols if allcols.count(col) > 1}
    if dupes:
        fail(f"duplicate predictor column name(s): {sorted(dupes)}")
    checks.append(f"{len(allcols)} predictor columns, no duplicates")


    # do control and interest blocks partition the block set?
    if set(c.CONTROL_BLOCKS) | set(c.INTEREST_BLOCKS) != set(c.PREDICTOR_COLUMNS):
            fail("control + interest do not cover every block")
    if set(c.CONTROL_BLOCKS) & set(c.INTEREST_BLOCKS):
            fail("a block is listed as both control and of-interest")
    checks.append("control/interest blocks partition cleanly")

    # we have 12 predictors of interest
    n_interest = len(c.columns_for(*c.INTEREST_BLOCKS))
    if n_interest != 12: 
         fail(f"expected: 12 predictors of interest (proposal 5.4), found: {n_interest}")
    checks.append("12 predictors of interest, matching proposal 5.4")

    # pos_dominant is categorical, it should not end up standardised
    if any(col.endswith("_z") for col in c.columns_for("pos", standardised=True)):
        fail("pos_dominant got standardised, it's supposed to stay categorical")
    checks.append("pos_dominant stayed categorical")

    # things we have not decided yet, add a name here whenever
    # config.py grows a new UNDECIDED value
    for name in ("REFERENCE_HISTORY_SEEN", "REFERENCE_LAG_DAYS"):
        value = getattr(c, name)
        if not isinstance(value, c._Undecided):
            continue  # already decided, nothing to check
        try:
            c.require_decided(value, name, "check_config")
        except RuntimeError:
            continue
        fail(f"{name} is still UNDECIDED but require_decided let it through anyway")
    checks.append("undecided values still refuse to be used")

    # do repo folders exist?
    for path in (c.FIGURES, c.DOCS):
        if not path.is_dir():
            fail(f"missing folder: {path}")
    checks.append("figures/ and docs/ are both there")

    # can we access the data root, and is it the one we expect?
    try:
        root = c.require_data_root()
    except RuntimeError as exc:
        fail(f"data root is unusable:\n{exc}")
    # if require_data_root() ever returned early without hitting a return, root
    # would just be None here and the checks below would mean nothing, but
    # without any error telling us that
    if not isinstance(root, Path):
        fail(f"require_data_root() handed back {root!r} instead of a Path")
    if root != c.DATA_ROOT:
        fail(f"require_data_root() returned {root}, expected {c.DATA_ROOT}")
    for path in (c.DATA_RAW, c.DATA_INTERMEDIATE, c.DATA_PROCESSED):
        if not path.is_dir():
            fail(f"missing data folder: {path}")
    where = "on the external drive" if c.DATA_ROOT_IS_EXTERNAL else "in the repo"
    checks.append(f"data root resolves, {where}")

    print("everything checks out.")
    for line in checks:
        print(f"  - {line}")
    print(f"\nseed {c.RANDOM_SEED}, min lag {c.MIN_LAG_DAYS} days, min obs {c.MIN_OBS_PER_ITEM}")
    print(f"data root: {root}")
    if not c.DATA_ROOT_IS_EXTERNAL:
        print("  (DATSCI_DATA_ROOT isn't set, so this is just the in-repo ./data)")


if __name__ == "__main__":
    main()
