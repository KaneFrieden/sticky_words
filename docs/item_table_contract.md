# Item-table contract between authors

Makes handoff between the two halves of the project explicit and establishes convention. 

Changing a col name here is akin to a change to the interface. Both authors must agree first, then
update this file and `src/config.py` in the same commit, to ensure uniformity and avoid divergence.

Canonical column names live in [`src/config.py`](../src/config.py)
(`PREDICTOR_COLUMNS`) and this file explains them.

Normally, a name which is merely misspelled but keeps its block prefix still
passes `check_config` (tested). However, there should be assertions during the between-author merge, so that this is caught.

---

## 1. Marie -> Kane: item inventory

**File:** `data/intermediate/item_inventory.parquet`
**Produced by:** `scripts/s05_item_inventory_marie.py`
**Grain:** one row per lemma.

| Column | Type | Notes |
|---|---|---|
| `lemma` | str | Base form parsed from `lexeme_string`. Join key. |
| `pos_dominant` | str | Most frequent PoS tag across the lexemes sharing this lemma. Control, not a predictor of interest. |
| `pos_dominant_share` | float | How dominant that PoS is. Makes split-PoS lemmas visible. |
| `n_lexemes` | int | How many distinct lexeme strings collapsed into this lemma. |
| `n_events` | int | Practice events for this lemma after the filters. |
| `exp_log1p_history_seen` | float | Mean of log1p(history_seen). |
| `exp_log1p_history_correct` | float | Mean of log1p(history_correct). |
| `exp_log1p_history_wrong` | float | Mean of log1p(history_seen - history_correct). |
| `exp_n_distinct_learners` | int | Distinct learners who practised this lemma. |
| `exp_median_history_seen_at_first` | float | Curriculum position. Median exposure count at a learner's first encounter. |
| `exp_mean_session_seen` | float | Mean session size. |
| `frm_n_inflectional_modifiers` | float | Mean modifier count across the lemma's lexemes. Parsed from the tag, so it originates on Marie's side even though it belongs to the form block. |

**Key/Index:** `lemma` alone, not the `(lemma, pos)` tuple. The proposal fixes the base form as
the unit of analysis (4.3, 5.2), where part of speech enters as a single
dominant-category control. Where one lemma carries several PoS readings
(`run<n>` vs `run<vblex>`) they collapse into one row, and `n_lexemes` plus
`pos_dominant_share` make the collapsing visible.

**Which sample is used by each aggregate:** Exposure aggregates are computed on the
lag-filtered sample, as this is what the outcome model sees.
`exp_median_history_seen_at_first` is the exception and uses all events for the
lemma, before the lag filter, because it describes where a word sits in the
course. Simply filtering by lag would introduce bias towards words whose early occurrences
happen to be spaced far apart.

**Exclusions, always counted separately:**

1. Wildcard lexemes (`<*sf>`, `<*numb>`, `<*pers>`).
2. Placeholder lemmas (`prpers` and similar). These are Duolingo encoding artefacts and not norm-coverage failures
3. Events with a lag below `config.MIN_LAG_DAYS`.

---

## 2. Marie -> Kane: outcome estimates

**File:** `data/intermediate/item_outcomes.parquet`
**Produced by:** `scripts/s06_fit_outcomes_marie.py`
**Grain:** one row per lemma, for lemmas with at least
`config.MIN_OBS_PER_ITEM` events.

| Column | Type | Notes |
|---|---|---|
| `lemma` | str | Join key. |
| `retention_level` | float | Fitted log-odds of recall at the reference point. |
| `retention_level_se` | float | Standard error (delta method). Feeds the inverse-variance weights. |
| `decay_slope` | float | Change in fitted log-odds per doubling of lag. |
| `decay_slope_se` | float | Standard error. |
| `cov_level_slope` | float | Sampling covariance of the two outcomes. Both come from one regression, so part of their correlation across items is mechanical. |
| `half_life_days` | float | Derived, for interpretability only. |
| `half_life_extrapolated` | bool | True where p = 0.5 falls outside the observed lag range. |
| `glm_converged` | bool | Stage-1 convergence flag. |
| `level_unstable` | bool | True where the level's SE exceeds the instability threshold. Flagged **independently** of the slope: an item can have an unusable level and a usable slope. |
| `n_obs` | int | Events the fit used. |

The reference point used (`REFERENCE_HISTORY_SEEN`, `REFERENCE_LAG_DAYS`) is
recorded in `docs/deviations.md` when it is decided, not fixed silently.

---

## 3. Kane -> Marie: analysis table

**File:** `data/processed/analysis_table.parquet`
**Produced by:** Kane's merge (s08)
**Grain:** one row per lemma, restricted to lemmas with complete predictor
coverage. The coverage report states how many are lost and to which source.

Contains everything above, plus:

- the lexical predictors listed below
- a standardised `_z` copy of every continuous predictor, standardised on the
  retained sample
- one `*_missing` boolean per norm-sourced predictor, so that coverage stays
  inspectable after the merge instead of being inferred from the NaNs.

### Predictor blocks

| Prefix | Block | Role | Produced by |
|---|---|---|---|
| `exp_` | Exposure & curriculum | control | Marie (s05) |
| `pos_` | Part of speech | control | Marie (s05) |
| `fam_` | Familiarity | of interest | Kane |
| `mea_` | Meaning | of interest | Kane |
| `frm_` | Form | of interest | Kane, except `frm_n_inflectional_modifiers` (Marie) |
| `trn_` | Transfer | of interest | Kane |

### Columns of interest (12)

| Column | Block | Source |
|---|---|---|
| `fam_log_frequency` | familiarity | SUBTLEX-US |
| `fam_age_of_acquisition` | familiarity | Kuperman et al. |
| `fam_prevalence` | familiarity | percent-known column (AoA file); open decision, see `docs/data_provenance_log.md` |
| `mea_concreteness` | meaning | Brysbaert et al. |
| `mea_semantic_density` | meaning | fastText neighbours |
| `mea_valence` | meaning | Warriner et al. |
| `mea_arousal` | meaning | Warriner et al. |
| `frm_length_chars` | form | lemma string |
| `frm_length_syllables` | form | norm file |
| `frm_letters_per_phoneme` | form | norm file |
| `frm_n_inflectional_modifiers` | form | lexeme tags (Marie) |
| `trn_norm_levenshtein_es` | transfer | translation + edit distance |

### Standardisation

Every continuous predictor gets a `_z` copy: mean 0, SD 1, computed only on the
analysis sample after coverage filtering, so that coefficients are
comparable across predictors (proposal 5.4). `pos_dominant` is categorical and
is never standardised, instead it is dummy-coded at model-fitting time.

Both the raw and the `_z` columns are kept. The raw ones are what figures and
descriptive tables should use, while the `_z` ones are what the models use.

Select a block with `config.columns_for("familiarity", "transfer")`, or with
`standardised=True` for the `_z` variants, rather than re-typing the names.

### Invariants for merging

- `lemma` has to stay unique. A join that multiplies rows is a bug, and not a coverage result.
- No row disappears without being counted in an exclusion, for maximum transparency.
- Every `_z` column has mean 0 and SD 1 on the retained sample. 
- Standardisation needs to happen after complete-case filtering, and not before.
- `pos_dominant` is categorical and never standardised.
- Comumn names need to match `congif.PREDICTOR_COLUMNS` exactly.
