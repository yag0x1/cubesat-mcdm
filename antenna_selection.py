"""
TOPSIS-based Multi-Criteria Decision Making (MCDM) tool for cubesat antenna
selection.

Merges two tabular datasets examples -- RF performance metrics and mechanical /
integration properties ("AIT" = Assembly, Integration & Test), then ranks the candidate antenna designs
using the TOPSIS method.

Usage:
    python antenna_selection.py \
        --rf data/example_rf_data.csv \
        --ait data/example_ait_data.csv \
        --output topsis_ranking_results.csv

See README.md for more information.
"""

import argparse
import re

import numpy as np
import pandas as pd

# ==========================================================================
# 1. CRITERIA CONFIGURATION
# ==========================================================================
# Each criterion maps to:
#   - "source_column": the column (after merging) that holds its raw value
#   - "type": +1 to maximize (benefit criterion), -1 to minimize (cost criterion)
#   - "weight": relative importance; all weights must sum to 1.0
#
# See README.md ("Criteria and Weights") for the justification behind these
# specific defaults.
CRITERIA = {
    "Max Gain (dBi)": {
        "source_column": "Max Gain (dBi)",
        "type": 1,
        "weight": 0.25,
    },
    "Bandwidth (%)": {
        "source_column": "Bandwidth (%)",
        "type": 1,
        "weight": 0.20,
    },
    "Radiation Efficiency (%)": {
        "source_column": "Radiation Efficiency (%)",
        "type": 1,
        "weight": 0.25,
    },
    "Height_Profile_mm": {
        # derived: 3rd value in "L x W x H"
        "source_column": "Dimensions (mm)",
        "type": -1,
        "weight": 0.15,
    },
    "Estimated_Weight_g": {
        "source_column": "Weight (g)",
        "type": -1,
        "weight": 0.15,
    },
}

# Columns used to join the two input files -- must exist, with matching
# values, in BOTH files.
MERGE_KEYS = ["No", "Title"]

# Substrings (case-insensitive) that mark a missing / not-reported value.
# Extend this list to match whatever placeholder text your own data uses.
MISSING_VALUE_MARKERS = ["not found", "not enough",
                         "none", "n/a", "multiple", "unknown"]


# ==========================================================================
# 2. DATA CLEANING
# ==========================================================================
def extract_number(value):
    if pd.isna(value):
        return np.nan
    text = str(value).strip()
    if any(marker in text.lower() for marker in MISSING_VALUE_MARKERS):
        return np.nan
    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    return float(numbers[-1]) if numbers else np.nan


def extract_height(value):
    if pd.isna(value):
        return np.nan
    text = str(value).strip()
    if any(marker in text.lower() for marker in MISSING_VALUE_MARKERS):
        return np.nan
    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    return float(numbers[2]) if len(numbers) >= 3 else np.nan


# ==========================================================================
# 3. TOPSIS ALGORITHM
# ==========================================================================
def run_topsis(decision_matrix, weights, criteria_types):
    norm = np.sqrt(np.sum(decision_matrix ** 2, axis=0))
    norm[norm == 0] = 1e-10  # avoid divide-by-zero if a column is all zeros
    r = decision_matrix / norm

    v = r * weights

    ideal_best = np.where(criteria_types == 1, v.max(axis=0), v.min(axis=0))
    ideal_worst = np.where(criteria_types == 1, v.min(axis=0), v.max(axis=0))

    dist_best = np.sqrt(np.sum((v - ideal_best) ** 2, axis=1))
    dist_worst = np.sqrt(np.sum((v - ideal_worst) ** 2, axis=1))

    return dist_worst / (dist_best + dist_worst)


# ==========================================================================
# 4. PIPELINE
# ==========================================================================
def load_and_merge(rf_path, ait_path):
    df_rf = pd.read_csv(rf_path, sep=None, engine="python")
    df_ait = pd.read_csv(ait_path, sep=None, engine="python")

    missing_rf = [k for k in MERGE_KEYS if k not in df_rf.columns]
    missing_ait = [k for k in MERGE_KEYS if k not in df_ait.columns]
    if missing_rf or missing_ait:
        raise ValueError(
            f"Merge key(s) not found -- RF missing {missing_rf}, AIT missing "
            f"{missing_ait}. Check MERGE_KEYS and your column names (see "
            "comment above)."
        )

    merged = pd.merge(df_rf, df_ait, on=MERGE_KEYS, how="inner")
    if len(merged) < max(len(df_rf), len(df_ait)):
        print(
            f"Warning: merge kept {len(merged)} rows out of {len(df_rf)} "
            f"(RF) / {len(df_ait)} (AIT). Some rows did not match on "
            f"{MERGE_KEYS} -- check for inconsistent values (e.g. a Title "
            "that differs slightly between the two files)."
        )
    return merged


def build_decision_table(merged_df):
    decision = pd.DataFrame()
    for key in MERGE_KEYS:
        decision[key] = merged_df[key]

    n_missing = pd.Series(0, index=decision.index)
    print("Missing-data summary per criterion (before median imputation):")
    for name, spec in CRITERIA.items():
        extractor = extract_height if name == "Height_Profile_mm" else extract_number
        raw_values = merged_df[spec["source_column"]].apply(extractor)
        decision[f"{name} (raw)"] = raw_values

        is_missing = raw_values.isna()
        n_missing += is_missing.astype(int)

        median = raw_values.median()
        decision[name] = raw_values.fillna(median)

        print(
            f"  {name:28s}: {is_missing.sum():3d}/{len(decision)} missing "
            f"({is_missing.mean():.0%}) -> imputed with median = {median:.3g}"
        )

    decision["N_Criteria_Imputed"] = n_missing
    return decision


def main():
    parser = argparse.ArgumentParser(
        description="Rank antenna designs from a literature review using TOPSIS."
    )
    parser.add_argument("--rf", default="example_rf_data.csv",
                        help="Path to the RF performance CSV/TSV file.")
    parser.add_argument("--ait", default="example_ait_data.csv",
                        help="Path to the mechanical/AIT CSV/TSV file.")
    parser.add_argument("--output", default="topsis_ranking_results.csv",
                        help="Path to write the ranked results CSV.")
    args, _unknown_args = parser.parse_known_args()

    weight_sum = sum(c["weight"] for c in CRITERIA.values())
    assert abs(
        weight_sum - 1.0) < 1e-9, f"Criteria weights must sum to 1.0 (got {weight_sum})"

    merged = load_and_merge(args.rf, args.ait)
    print(f"Merged {len(merged)} matching alternatives from '{
          args.rf}' and '{args.ait}'.\n")

    decision = build_decision_table(merged)

    matrix = decision[list(CRITERIA.keys())].to_numpy(dtype=float)
    weights = np.array([c["weight"] for c in CRITERIA.values()])
    types = np.array([c["type"] for c in CRITERIA.values()])

    decision["TOPSIS_Score"] = run_topsis(matrix, weights, types)
    decision["Rank"] = decision["TOPSIS_Score"].rank(
        ascending=False).astype(int)

    ranking = decision.sort_values("Rank")
    print("\n=== TOPSIS Ranking (best to worst) ===")
    print(ranking[["Rank", "Title", "TOPSIS_Score",
          "N_Criteria_Imputed"]].to_string(index=False))

    ranking.to_csv(args.output, index=False)
    print(f"\nFull results written to '{args.output}'")


if __name__ == "__main__":
    main()
