"""Tests for run_pipeline in reconcile.pipeline, using the sample files and one broken upload."""

from pathlib import Path

import pandas as pd
import pytest

from reconcile.pipeline import run_pipeline

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "data" / "sample"
BANK_SAMPLE = SAMPLE_DIR / "bank_transactions.csv"
INVOICES_SAMPLE = SAMPLE_DIR / "invoices.csv"


# Checks that running the pipeline on the sample files returns the four expected keys.
def test_run_pipeline_returns_expected_keys():
    result = run_pipeline(BANK_SAMPLE, INVOICES_SAMPLE)

    assert set(result.keys()) == {"summary", "reconciled", "pending_bank", "pending_invoices"}


# Checks that reconciled plus pending rows equal the number of rows in each sample file.
def test_counts_add_up_to_input_sizes():
    result = run_pipeline(BANK_SAMPLE, INVOICES_SAMPLE)

    bank_rows = len(pd.read_csv(BANK_SAMPLE))
    invoice_rows = len(pd.read_csv(INVOICES_SAMPLE))
    assert len(result["reconciled"]) + len(result["pending_bank"]) == bank_rows
    assert len(result["reconciled"]) + len(result["pending_invoices"]) == invoice_rows


# Checks that a bank file missing the amount column makes run_pipeline raise a ValueError.
def test_missing_column_in_upload_raises_value_error(tmp_path):
    broken_bank = tmp_path / "bank_transactions.csv"
    broken_bank.write_text(
        "transaction_id,date,description\nTXN-0001,2026-01-05,PIX ACME\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="amount"):
        run_pipeline(broken_bank, INVOICES_SAMPLE)
