"""Evaluate the matcher on the sample data and save precision and coverage per stage to output/evaluation.csv.

Run from the project root:  python scripts/evaluate_matching.py
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "sample"
OUTPUT_DIR = ROOT / "output"
sys.path.insert(0, str(ROOT / "src"))

from reconcile.evaluation import evaluate_matches  # noqa: E402

LABEL = "Synthetic data, default parameters, author-designed decoys"


# Loads the sample files, runs the evaluation, saves the table with a dataset label, and prints it.
def main():
    bank = pd.read_csv(SAMPLE_DIR / "bank_transactions.csv")
    invoices = pd.read_csv(SAMPLE_DIR / "invoices.csv")
    truth = pd.read_csv(SAMPLE_DIR / "ground_truth.csv", keep_default_na=False)

    outcome = evaluate_matches(bank, invoices, truth)
    table = outcome["table"].copy()
    table.insert(0, "dataset", LABEL)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT_DIR / "evaluation.csv", index=False)

    print(LABEL)
    print(table.to_string(index=False))
    print(f"\nExpected matches: {outcome['expected_matches']}")
    print(f"Unmatched rows:   {outcome['unmatched_rows']}")
    print(f"\nSaved to {OUTPUT_DIR / 'evaluation.csv'}")


if __name__ == "__main__":
    main()
