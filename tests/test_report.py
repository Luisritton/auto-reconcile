"""Tests for the report builder in reconcile.report, using small hand-made tables."""

import pandas as pd
import pytest

from reconcile.report import build_report, build_summary, write_reports


# Builds a bank table from a list of rows.
def make_bank(rows):
    return pd.DataFrame(rows, columns=["transaction_id", "date", "description", "amount"])


# Builds an invoices table from a list of rows.
def make_invoices(rows):
    return pd.DataFrame(rows, columns=["invoice_id", "issue_date", "customer", "amount"])


# Builds a matches table from a list of rows.
def make_matches(rows):
    return pd.DataFrame(rows, columns=["transaction_id", "invoice_id", "match_stage", "match_score"])


# Returns a small example with two matches, two unmatched bank rows and one unmatched invoice.
def small_example():
    bank = make_bank([
        ["TXN-1", "2026-01-10", "PIX ACME", 100.00],
        ["TXN-2", "2026-01-11", "PIX BETA", 50.00],
        ["TXN-3", "2026-01-12", "TARIFA", 30.00],
        ["TXN-4", "2026-01-13", "PIX XYZ", 20.00],
    ])
    invoices = make_invoices([
        ["INV-1", "2026-01-08", "Acme", 100.00],
        ["INV-2", "2026-01-09", "Beta", 50.00],
        ["INV-3", "2026-01-10", "Gama", 70.00],
    ])
    matches = make_matches([
        ["TXN-1", "INV-1", "exact", 1.0],
        ["TXN-2", "INV-2", "fuzzy", 0.8],
        ["TXN-3", "", "unmatched", None],
        ["TXN-4", "", "unmatched", None],
    ])
    return bank, invoices, matches


# Checks that every bank transaction and every invoice appears in exactly one group.
def test_groups_add_up():
    bank, invoices, matches = small_example()

    report = build_report(bank, invoices, matches)

    reconciled_bank = list(report["reconciled"]["transaction_id"])
    pending_bank = list(report["pending_bank"]["transaction_id"])
    assert sorted(reconciled_bank + pending_bank) == sorted(bank["transaction_id"])
    assert len(set(reconciled_bank) & set(pending_bank)) == 0

    reconciled_invoices = list(report["reconciled"]["invoice_id"])
    pending_invoices = list(report["pending_invoices"]["invoice_id"])
    assert sorted(reconciled_invoices + pending_invoices) == sorted(invoices["invoice_id"])
    assert len(set(reconciled_invoices) & set(pending_invoices)) == 0


# Checks that the reconciled rate, stage counts and pending totals are correct for a known example.
def test_summary_numbers_are_correct():
    bank, invoices, matches = small_example()

    summary = build_summary(bank, invoices, matches)

    assert summary["total_bank_transactions"] == 4
    assert summary["total_invoices"] == 3
    assert summary["reconciled_count"] == 2
    assert summary["reconciled_rate"] == 0.5
    assert summary["exact_count"] == 1
    assert summary["fuzzy_count"] == 1
    assert summary["pending_bank_amount"] == 50.00
    assert summary["pending_invoice_amount"] == 70.00


# Checks that a match pointing to an invoice that does not exist raises a ValueError.
def test_unknown_invoice_id_raises_value_error():
    bank = make_bank([
        ["TXN-1", "2026-01-10", "PIX ACME", 100.00],
        ["TXN-2", "2026-01-11", "PIX BETA", 50.00],
    ])
    invoices = make_invoices([["INV-1", "2026-01-08", "Acme", 100.00]])
    matches = make_matches([
        ["TXN-1", "INV-99", "exact", 1.0],
        ["TXN-2", "", "unmatched", None],
    ])

    with pytest.raises(ValueError, match="Bank transaction count"):
        build_report(bank, invoices, matches)


# Checks that write_reports creates the three CSV files and the Excel workbook.
def test_write_reports_creates_all_files(tmp_path):
    bank, invoices, matches = small_example()
    report = build_report(bank, invoices, matches)
    summary = build_summary(bank, invoices, matches)
    output_dir = tmp_path / "output"

    write_reports(report, summary, output_dir)

    assert (output_dir / "reconciled.csv").is_file()
    assert (output_dir / "pending_bank.csv").is_file()
    assert (output_dir / "pending_invoices.csv").is_file()
    assert (output_dir / "reconciliation.xlsx").is_file()
