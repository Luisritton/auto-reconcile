"""Test that the evaluation function returns the keys the report and the script rely on."""

from pathlib import Path

import pandas as pd

from reconcile.evaluation import evaluate_matches

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "data" / "sample"


# Checks that evaluate_matches returns the expected keys and one row for each stage, without checking specific numbers.
def test_evaluate_matches_returns_expected_keys():
    bank = pd.read_csv(SAMPLE_DIR / "bank_transactions.csv")
    invoices = pd.read_csv(SAMPLE_DIR / "invoices.csv")
    truth = pd.read_csv(SAMPLE_DIR / "ground_truth.csv", keep_default_na=False)

    outcome = evaluate_matches(bank, invoices, truth)

    assert set(outcome.keys()) == {"table", "expected_matches", "false_matches", "unmatched_rows"}
    assert list(outcome["table"]["stage"]) == ["exact", "fuzzy", "overall"]
