# CubeSat Antenna Selection via MCDM 

A Multi-Criteria Decision Making (MCDM) small tool that ranks candidate antenna using the **TOPSIS**
method (Technique for Order Preference by Similarity to Ideal Solution).

It merges two tabular datasets:

- an **RF performance** table (gain, bandwidth, efficiency, polarization, ...)
- a **mechanical / integration** table (dimensions, mass, substrate,
  fabrication method, ...), referred to here as **AIT** (Assembly,
  Integration & Test)

and produces a single ranked list, from the design closest to the ideal
trade-off to the one furthest from it.

> The `data/` folder contains a small **synthetic example dataset** (six
> fictitious antennas) so the script runs out of the box. Replace it with
> your own extracted literature data — see [Input Data Format](#input-data-format).

## Why This Tool 
Selecting the right antennas for a CubeSat mission often involves balancing multiple, often conflicting, criteria (such as mass, Gain, cost, and weight). This repository provides a systematic way to evaluate and prioritize these alternatives.

Critical aspects of this tool:
- **The method selected:** Choosing the appropriate MCDM algorithm for the specific evaluation.
- **The parameters used:** Defining the right criteria for decision-making.
- **The selection of scores:** Assigning weights and scores based on the specific mission's focus and constraints.

## Why TOPSIS

Several MCDM methods exist (AHP, WSM, ELECTRE, PROMETHEE, ...); TOPSIS was
chosen for this use case because it:

- **Handles benefit and cost criteria natively.** Gain, bandwidth and
  efficiency should be maximized; height and mass should be minimized.
  TOPSIS handles both directly through the positive/negative ideal solution
  construction, with no need for utility-function transformations.
- **Needs only one round of subjective judgment.** Unlike AHP, it does not
  require pairwise comparisons between every criterion — only a single
  weight vector — which keeps the method reproducible and limits where
  subjectivity can enter the analysis.
- **Produces one continuous, interpretable score per alternative.** The
  *closeness coefficient* C\* ∈ [0, 1] has a direct geometric meaning
  (relative distance to the ideal design) and is easy to report and rank by.
- **Is well established for engineering trade studies**, including antenna
  and small-satellite subsystem selection, which supports reproducibility
  and makes the result easy for reviewers to sanity-check.

## Criteria and Weights

| Criterion | Column | Direction | Weight |
|---|---|---|---|
| Max Gain | `Max Gain (dBi)` | Maximize | 0.25 |
| Bandwidth | `Bandwidth (%)` | Maximize | 0.20 |
| Radiation Efficiency | `Radiation Efficiency (%)` | Maximize | 0.25 |
| Height / profile | derived from `Dimensions (mm)` | Minimize | 0.15 |
| Mass | `Weight (g)` | Minimize | 0.15 |

**Rationale.** The five criteria fall into two groups:

1. **Link-budget performance — gain, bandwidth, efficiency (70% combined).**
   Gain and radiation efficiency together determine how much of the
   transmitter's power actually reaches the link (EIRP on transmit, G/T on
   receive); on a power-constrained CubeSat, every dB lost to inefficiency
   has to be recovered elsewhere in the budget, so these two receive the
   highest individual weights (0.25 each). Bandwidth is weighted slightly
   lower (0.20) because it mainly affects *robustness* — tolerance to
   fabrication variance, on-orbit thermal detuning, and frequency-plan
   flexibility — rather than the link margin itself.
2. **Physical integration cost — height and mass (30% combined).** CubeSats
   are built to strict, standardized volume (`U`) and mass budgets, so a
   bulky or heavy antenna directly displaces payload or other subsystems.
   These are real constraints, but for the body-mounted/conformal antennas
   that dominate this design space they typically act as *feasibility*
   constraints (does it fit, does it stay within the mass budget) more than
   as continuously optimized objectives — so they are weighted lower than
   raw RF performance, while still being substantial enough (0.15 each) to
   separate designs that are RF-equivalent but not equally practical to fly.

These weights are a starting point that encodes "RF performance first,
physical footprint second." **They are a mission-priority judgment call, not
a universal constant** — a mission with a very tight volume budget (e.g. a
1U bus with little room to spare) might justifiably weight height and mass
more heavily; a mission with a marginal link budget might push gain and
efficiency even higher. Adjust `CRITERIA` in
[`topsis_antenna_selection.py`](topsis_antenna_selection.py) to match your
own mission's priorities — weights only need to sum to 1.0.

## Methodology

### 1. Data extraction

Each raw cell is free text (e.g. produced by manual extraction or an
LLM-assisted reading of each paper), so it first has to be reduced to a
single number:

- A regular expression pulls out all numbers in the cell and keeps the
  **last** one (e.g. `"7.7/12.8" → 12.8`, `"4-10" → 10`).
- Cells containing a configurable list of "missing data" markers (`"Not
  found"`, `"None"`, `"N/A"`, ...) are treated as missing (`NaN`) rather
  than parsed.
- The height/profile criterion is derived from a `"Length x Width x Height"`
  dimensions string by taking the third number; if only two numbers are
  present (no height reported), it is treated as missing rather than
  mistaking the width for the height.

### 2. Handling missing data

Any criterion missing for a given antenna is imputed with the **median** of
that criterion across all other antennas, so a single unreported figure
doesn't remove an otherwise well-documented design from the comparison. The
script reports, per criterion, how many values were missing and what median
was substituted, and the output table includes both the raw (`... (raw)`)
and imputed values plus an `N_Criteria_Imputed` count per antenna — a higher
count means that antenna's score leans more on dataset-wide medians and less
on figures actually reported in its source paper, which is useful context
when interpreting the ranking.

### 3. TOPSIS ranking

Given the resulting decision matrix `X` (alternatives × criteria):

1. **Vector-normalize** each column: `r_ij = x_ij / sqrt(Σ_i x_ij²)`.
2. **Apply criterion weights**: `v_ij = r_ij · w_j`.
3. **Identify the ideal best/worst** for each criterion — the max for a
   "maximize" criterion and the min for a "minimize" one (and vice versa
   for the worst).
4. **Compute the Euclidean distance** from each alternative to the ideal
   best (`D+`) and ideal worst (`D-`).
5. **Compute the closeness coefficient**: `C* = D- / (D+ + D-)`.

`C*` ranges from 0 to 1; a design tied with the ideal best on every
criterion scores 1, and one tied with the ideal worst on every criterion
scores 0. Alternatives are ranked by `C*`, descending.

## Input Data Format

Both input files must share two **merge key** columns with matching values:
`No` (an identifier) and `Title` (must match exactly between the two
files). Expected columns (extra columns are ignored):

**RF file**

| Column | Example |
|---|---|
| `No`, `Title` | merge keys |
| `Max Gain (dBi)` | `7.5` or `7.7/12.8` for a multi-band design |
| `Bandwidth (%)` | `15.0` |
| `Radiation Efficiency (%)` | `92.0` or `Not found.` |

**AIT file**

| Column | Example |
|---|---|
| `No`, `Title` | merge keys |
| `Dimensions (mm)` | `80 x 80 x 3.2` (Length x Width x Height) |
| `Weight (g)` | `45` or `Not found.` |

Files may be comma- or tab-delimited; the delimiter is auto-detected.

## Usage

```bash
pip install -r requirements.txt

python topsis_antenna_selection.py \
    --rf data/example_rf_data.csv \
    --ait data/example_ait_data.csv \
    --output topsis_ranking_results.csv
```

All three arguments are optional and default to the example dataset and
`topsis_ranking_results.csv` in the current directory.

## Output

`topsis_ranking_results.csv` contains one row per antenna, with:

- the merge keys (`No`, `Title`)
- each criterion's raw extracted value (`... (raw)`) and the value actually
  used in the calculation after imputation
- `N_Criteria_Imputed` — how many of the 5 criteria were imputed for that row
- `TOPSIS_Score` — the closeness coefficient C\*
- `Rank` — 1 = best

## Limitations

- **Multi-value cells and multi-band designs.** Taking the *last* number in
  a cell like `"7.7/12.8"` is a simple, transparent default, but for a
  multi-band antenna it does not reliably correspond to any specific band —
  the position of a value in the string depends on how the source data was
  reported, not on a fixed band ordering. If your dataset includes
  multi-band designs and the band-specific value matters, extract it
  explicitly (e.g. by cross-referencing a center-frequency column) rather
  than relying on this default.
- **Median imputation can flatten differences.** When a criterion is
  missing for a large share of alternatives, most of them end up sharing
  the same imputed value, so that criterion stops differentiating the
  ranking for those rows. Check `N_Criteria_Imputed` before treating a
  ranking position as a strong result, and prefer filling in real figures
  from the source papers wherever feasible.
- **Weights encode a judgment call**, not a derived or universal
  optimum — see [Criteria and Weights](#criteria-and-weights).



## Inspiration and Acknowledgments

This project was inspired by the [Multi-Criteria-Decision-Making](https://github.com/Pegah-Ardehkhani/Multi-Criteria-Decision-Making) repository by Pegah-Ardehkhani. 

Their work provides an overview and implementation of various MCDM techniques (such as TOPSIS, VIKOR, AHP, and SAW). These algorithms were adapted for design requirements of CubeSat Antenas.


