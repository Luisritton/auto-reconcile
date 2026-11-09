"""Tests for the two-stage matcher in reconcile.matcher, using small hand-made tables."""

import difflib
from pathlib import Path

import pandas as pd

from reconcile.matcher import match_transactions, normalize_name


# Builds a bank table from a list of rows.
def make_bank(rows):
    return pd.DataFrame(rows, columns=["transaction_id", "date", "description", "amount"])


# Builds an invoices table from a list of rows.
def make_invoices(rows):
    return pd.DataFrame(rows, columns=["invoice_id", "issue_date", "customer", "amount"])


# Returns the single result row for a given transaction id.
def row_for(result, transaction_id):
    return result[result["transaction_id"] == transaction_id].iloc[0]


# Checks that a transaction within the date window and with the same amount is matched exactly.
def test_exact_match_within_date_window():
    bank = make_bank([["TXN-1", "2026-01-10", "PIX ACME LTDA", 100.00]])
    invoices = make_invoices([["INV-1", "2026-01-08", "Acme", 100.00]])

    result = match_transactions(bank, invoices, date_window_days=2)

    row = row_for(result, "TXN-1")
    assert row["invoice_id"] == "INV-1"
    assert row["match_stage"] == "exact"
    assert row["match_score"] == 1.0


# Checks that the same amount five days apart is not an exact match when the window is two days.
def test_same_amount_outside_date_window_is_not_exact():
    bank = make_bank([["TXN-1", "2026-01-13", "PIX ZETA", 100.00]])
    invoices = make_invoices([["INV-1", "2026-01-08", "Acme Ltda", 100.00]])

    result = match_transactions(bank, invoices, date_window_days=2)

    assert row_for(result, "TXN-1")["match_stage"] != "exact"


# Checks that two transactions with the same amount cannot both take the same single invoice.
def test_two_transactions_cannot_share_one_invoice():
    bank = make_bank([
        ["TXN-1", "2026-01-10", "PIX ACME", 100.00],
        ["TXN-2", "2026-01-10", "PIX ACME", 100.00],
    ])
    invoices = make_invoices([["INV-1", "2026-01-10", "Acme", 100.00]])

    result = match_transactions(bank, invoices, date_window_days=2)

    matched = result[result["invoice_id"] == "INV-1"]
    assert len(matched) == 1
    assert (result["match_stage"] == "unmatched").sum() == 1


# Checks that a same amount and similar name, but dates 10 days apart with a 2-day window, do not match in any stage.
def test_similar_name_and_amount_but_date_outside_window_is_not_matched():
    bank = make_bank([["TXN-1", "2026-01-20", "PIX ACME LTDA", 250.00]])
    invoices = make_invoices([["INV-1", "2026-01-10", "Acme Ltda", 250.00]])

    result = match_transactions(
        bank, invoices, date_window_days=2, min_similarity=0.6, fuzzy_date_window_days=2
    )

    row = row_for(result, "TXN-1")
    assert row["match_stage"] == "unmatched"
    assert row["invoice_id"] == ""


# Checks that a same amount and similar name, 10 days apart, match in the fuzzy stage when its window is 30 days.
def test_similar_name_within_fuzzy_window_matches():
    bank = make_bank([["TXN-1", "2026-01-20", "PIX ACME LTDA", 250.00]])
    invoices = make_invoices([["INV-1", "2026-01-10", "Acme Ltda", 250.00]])

    result = match_transactions(
        bank, invoices, date_window_days=2, min_similarity=0.6, fuzzy_date_window_days=30
    )

    row = row_for(result, "TXN-1")
    assert row["match_stage"] == "fuzzy"
    assert row["invoice_id"] == "INV-1"


# Checks that a decoy with the same amount and a similar name, but a date 59 days away, is not matched in any stage.
def test_decoy_with_similar_name_and_far_date_is_not_matched():
    bank = make_bank([["TXN-1", "2026-03-10", "PIX ACME LTDA", 250.00]])
    invoices = make_invoices([["INV-1", "2026-01-10", "Acme Ltda", 250.00]])

    result = match_transactions(bank, invoices)  # default parameters

    row = row_for(result, "TXN-1")
    assert row["match_stage"] == "unmatched"
    assert row["invoice_id"] == ""


# Checks that with a 0-day fuzzy window, a same-amount and similar-name transaction with different dates is never fuzzy-matched.
def test_fuzzy_window_zero_never_fuzzy_matches_when_dates_differ():
    bank = make_bank([["TXN-1", "2026-01-15", "PIX ACME LTDA", 250.00]])
    invoices = make_invoices([["INV-1", "2026-01-10", "Acme Ltda", 250.00]])

    result = match_transactions(
        bank, invoices, date_window_days=2, min_similarity=0.6, fuzzy_date_window_days=0
    )

    row = row_for(result, "TXN-1")
    assert row["match_stage"] != "fuzzy"
    assert row["match_stage"] == "unmatched"


# Checks that same amount and same date, with clearly different customer names, are not matched in any stage.
def test_same_amount_same_date_different_names_not_matched():
    bank = make_bank([["TXN-1", "2026-01-10", "PIX OMEGA IMPORTADORA", 250.00]])
    invoices = make_invoices([["INV-1", "2026-01-10", "Acme Ltda", 250.00]])

    result = match_transactions(bank, invoices)  # default parameters

    row = row_for(result, "TXN-1")
    assert row["match_stage"] == "unmatched"
    assert row["invoice_id"] == ""


# Checks that normalize_name removes accents and punctuation: "Açaí Ltda." becomes "acai ltda".
def test_normalize_removes_accents_and_punctuation():
    assert normalize_name("Açaí Ltda.") == "acai ltda"


# Checks that normalize_name removes bank prefixes as whole words: "PIX Acme Ltda." becomes "acme ltda".
def test_normalize_removes_bank_prefixes():
    assert normalize_name("PIX Acme Ltda.") == "acme ltda"


# Checks that repeated spaces collapse to one space, and that leading and trailing spaces are removed.
def test_normalize_collapses_spaces():
    assert normalize_name("  Gama    Serviços  ") == "gama servicos"


# Checks that normalize_name gives the same output for the same input every time.
def test_normalize_is_deterministic():
    text = "PIX Beta Com.L tda."
    assert normalize_name(text) == normalize_name(text)


# Checks that on the sample data the fuzzy stage finds matches, and that the date limit rejects some of them.
def test_sample_fuzzy_matches_exist_and_date_limit_rejects_some():
    sample_dir = Path(__file__).resolve().parents[1] / "data" / "sample"
    bank = pd.read_csv(sample_dir / "bank_transactions.csv")
    invoices = pd.read_csv(sample_dir / "invoices.csv")

    limited = match_transactions(bank, invoices)  # default fuzzy window
    unlimited = match_transactions(bank, invoices, fuzzy_date_window_days=100000)

    assert (limited["match_stage"] == "fuzzy").sum() > 0
    assert (limited["invoice_id"] != "").sum() < (unlimited["invoice_id"] != "").sum()


# Checks that a same-amount transaction with a completely different name stays unmatched.
def test_same_amount_different_name_stays_unmatched():
    bank = make_bank([["TXN-1", "2026-03-01", "PIX ZETA CONSULTORIA", 250.00]])
    invoices = make_invoices([["INV-1", "2026-01-01", "Acme Ltda", 250.00]])

    result = match_transactions(bank, invoices, date_window_days=2, min_similarity=0.6)

    row = row_for(result, "TXN-1")
    assert row["match_stage"] == "unmatched"
    assert row["invoice_id"] == ""


# Checks that no invoice id appears more than once in the output, even with many competing transactions.
def test_same_invoice_never_appears_twice():
    bank = make_bank([
        ["TXN-1", "2026-01-10", "PIX ACME", 100.00],
        ["TXN-2", "2026-01-10", "PIX ACME", 100.00],
        ["TXN-3", "2026-01-10", "PIX ACME", 100.00],
    ])
    invoices = make_invoices([
        ["INV-1", "2026-01-10", "Acme", 100.00],
        ["INV-2", "2026-01-10", "Acme", 100.00],
    ])

    result = match_transactions(bank, invoices, date_window_days=2)

    used_ids = result.loc[result["invoice_id"] != "", "invoice_id"]
    assert len(used_ids) == 2
    assert used_ids.is_unique
    assert (result["match_stage"] == "unmatched").sum() == 1
