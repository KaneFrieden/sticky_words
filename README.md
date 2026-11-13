# Beyond Exposure: What Makes Words Stick?

This repository is the clean rebuild of our Duolingo word-retention analysis. We
lost sight of the project a bit in October during the start of the new semester
so now we are just starting to get back into it.
The earlier full analysis remains available in the separate `project` repository
for checking counts and results. We are rewritting the scripts and code for the
project in small, more easily reviewable stages such that we don't go out of sync.

## Current stage

`scripts/s00_verify_inputs_marie.py` checks the raw dataset and the locations for
new outputs. `scripts/s01_subset_kane.py` selects the language group and produces
the first descriptive summary. Later analysis scripts are still in progress.

## Data locations

Use a separate Python 3.12 environment for this repository. The local `.venv`
is ignored by Git and can be recreated without changing the project files.

Set `DATSCI_DATA_ROOT` to a new output directory containing a
`.datsci-data-root` marker. Set `DATSCI_RAW_ROOT` when reusing an existing
raw-data directory. Choose a fresh output directory for this rebuild. When
`DATSCI_RAW_ROOT` is set, s00 checks that the two locations do not overlap.
See `env.example.sh` for the
variables. A machine-specific `env.sh` is ignored by Git.

Run `.venv/bin/python scripts/s00_verify_inputs_marie.py` after setting the variables.
The raw directory must contain the dataset and its `dataset_manifest.json`.
The script verifies the raw file's size and MD5 against that local manifest
without writing to the raw-data directory.
Downloading the dataset is now handled by `scripts/download_dataset.py`, which also creates a local manifest.
