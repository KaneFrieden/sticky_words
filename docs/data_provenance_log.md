# Data provenance log

Append-only record of every dataset's origins, as well as how and when it was verified. We also record dead ends we hit, in order to prevent multiple fruitless searches. Some parts of this are also mentioned in the code as comments, we chose to additionally keep a centralized version, as to keep track of everything more efficiently.

The actually machine-readable versions (`data/raw/dataset_manifest.json`,
`data/raw/norms/norms_manifest.json`) are written by the fetch scripts, but
live inside the gitignored `data/` tree, so this file acts as the committed copy.

---

## 1. Duolingo Half-Life Regression learning traces

| | |
|---|---|
| **Sought** | Practice-event traces with per-event lag, exposure history and outcome, for the primary analysis |
| **Fetched by** | `scripts/s01_fetch_dataset_kane.py` |
| **Retrieved** | 2026-09-25 |
| **Citation** | Settles & Meeder (2016), ACL 2016, 1848–1858 |
| **DOI** | `doi:10.7910/DVN/N8XJME` (Harvard Dataverse) |
| **URL** | `https://dataverse.harvard.edu/api/access/datafile/3091087` |
| **File** | `settles.acl16.learning_traces.13m.csv.gz` |
| **Size** | 379,004,009 bytes |
| **md5** | `0a1cae5eb7ad4b0bd9c0de91d74fcced` |
| **Licence** | CC-BY |

**Verification:**  md5 is not ours, but rather the publisher's value, read live from the
API at download time. The publisher's value, thus, detects a
truncated or substituted download. Size and checksum are both compared, and the
file is deleted if either fails, ensuring that versions match

**Contents:** 12,854,226 practice events across diverse language pairs with the following columns:
`p_recall`, `timestamp`, `delta`, `user_id`, `learning_language`,
`ui_language`, `lexeme_id`, `lexeme_string`, `history_seen`,
`history_correct`, `session_seen`, `session_correct`.

**Notes:**
- The raw file is neither modified, nor committed (`data/raw/*` is gitignored). Rather, every downstream file is produced from it via code.
- Dataverse returns HTTP 403, when requested with Python's default user agent. Both the metadata request and the download send a browser-like `User-Agent` (with accurate and truthful information).

---

## 2. Lexical norm databases

Fetched by `scripts/s03_fetch_norms_kane.py`, with per-file details in
`data/raw/norms/norms_manifest.json`.

**Dead end: Original host** 4/5 norm files were published on
the Center for Reading Research site (`crr.ugent.be`), which turned out to be offline as of
23.09.2026. They are therefore fetched from Internet Archive snapshots, and pinned
to exact timestamps, so that the result is reproducible nonetheless.

**Verification of archived copies:** A sha256 is recorded per file, and each
source carries a minimum byte count. One archived snapshot returns HTTP 200
with an error page in place of the data file, so a status code is not an
integrity check, as we can no longer check against the publisher's version. Anything under the byte-count floor is deleted.

| Source | Feeds | Snapshot |
|---|---|---|
| Brysbaert et al. concreteness | `mea_concreteness` | 2023-11-15 |
| Kuperman et al. age of acquisition | `fam_age_of_acquisition`, `fam_prevalence` | 2022-12-07 |
| Warriner et al. affective norms | `mea_valence`, `mea_arousal` | 2013-09-27 |
| SUBTLEX-US | `fam_log_frequency` | 2022-07-01 |
| Brysbaert et al. word prevalence | `fam_prevalence` (alternative measure) | 2023-07-27 |

**Open point for `fam_prevalence` (as referenced in `docs/item_table_contract.md`)** Two files can supply it.
- The percent-known column of the age-of-acquisition file, as outlined in the original plan 
- The separate word-prevalence file for 62k lemmas, which offers broader coverage. 

Both are downloaded, but which one will end up feeding the predictor, and which is kept only for comparison, needs to
be decided and recorded in `docs/deviations.md`.

---

## 3. Derived downloads

| Source | Used for | Owner | Status |
|---|---|---|---|
| fastText English vectors | `mea_semantic_density` | Kane | not fetched yet |
| OPUS-MT en->es | `trn_norm_levenshtein_es` | Kane | not fetched yet |
