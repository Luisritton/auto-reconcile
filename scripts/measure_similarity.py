"""Measure the normalized name similarity of every correct match, per dataset and stage.

Measurement only: this script does not change the matcher, the thresholds, the generator or the sample data.
It reuses the validation generator and the original sample, and saves the full list to output/similarity_validation.csv.
Run from the project root:  python scripts/measure_similarity.py
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from reconcile.matcher import _similarity, match_transactions  # noqa: E402
from validate_generalization import VALIDATION_SEEDS, load_original_sample, make_data  # noqa: E402


# Lists every correct match in one dataset, with the similarity recomputed from the normalized names.
def correct_pairs(label, bank, invoices, truth):
    result = match_transactions(bank, invoices)  # default parameters, unchanged
    merged = result.merge(truth, on="transaction_id")
    merged = merged[(merged["invoice_id"] != "") & (merged["invoice_id"] == merged["expected_invoice_id"])]
    merged = merged.merge(bank[["transaction_id", "description"]], on="transaction_id")
    merged = merged.merge(invoices[["invoice_id", "customer"]], on="invoice_id")
    merged = merged.assign(similarity=[
        round(_similarity(d, c), 4) for d, c in zip(merged["description"], merged["customer"])
    ])
    pairs = merged.rename(columns={
        "description": "bank_description",
        "customer": "invoice_customer",
        "match_score": "matcher_score",
    })
    pairs.insert(0, "dataset", label)
    return pairs[[
        "dataset", "transaction_id", "invoice_id", "match_stage",
        "bank_description", "invoice_customer", "similarity", "matcher_score",
    ]]


# Prints count, minimum, median and maximum similarity for each stage, plus the 5 lowest correct pairs.
def print_stats(pairs):
    for stage in ["exact", "fuzzy"]:
        part = pairs[pairs["match_stage"] == stage]
        print(f"\n--- {stage} stage ---")
        if part.empty:
            print("no correct pairs in this stage")
            continue
        print(f"correct pairs: {len(part)}")
        print(f"min: {part['similarity'].min():.4f}  median: {part['similarity'].median():.4f}  "
              f"max: {part['similarity'].max():.4f}")
        lowest = part.sort_values(["similarity", "transaction_id"]).head(5)
        print("5 lowest-similarity correct pairs:")
        print(lowest[["transaction_id", "invoice_id", "bank_description", "invoice_customer", "similarity"]]
              .to_string(index=False))


# Runs the measurement on the original sample and on both validation seeds, prints the stats and saves the CSV.
def main():
    datasets = [("original sample", load_original_sample())]
    for seed in VALIDATION_SEEDS:
        datasets.append((f"seed {seed}", make_data(seed)))

    all_pairs = []
    for label, (bank, invoices, truth) in datasets:
        pairs = correct_pairs(label, bank, invoices, truth)
        all_pairs.append(pairs)
        print(f"\n==================== {label} ====================")
        print_stats(pairs)

        fuzzy = pairs[pairs["match_stage"] == "fuzzy"]
        differences = int(((fuzzy["similarity"] - fuzzy["matcher_score"]).abs() > 0.0001).sum())
        print(f"\nfuzzy pairs where recomputed similarity differs from the matcher score: {differences}")

    combined = pd.concat(all_pairs, ignore_index=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUTPUT_DIR / "similarity_validation.csv", index=False)
    print(f"\nSaved {len(combined)} correct pairs to {OUTPUT_DIR / 'similarity_validation.csv'}")


if __name__ == "__main__":
    main()
