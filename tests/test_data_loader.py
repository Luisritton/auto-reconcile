"""Tests for the CSV loader in reconcile.data_loader."""

import pytest

from reconcile.data_loader import load_data

BANK_HEADER = "transaction_id,date,description,amount\n"
INVOICE_HEADER = "invoice_id,issue_date,customer,amount\n"


# Writes text to a file in the temporary test folder and returns the file path.
def write_file(folder, name, text):
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


# Checks that a valid pair of files loads into DataFrames with the expected columns and values.
def test_valid_files_load_correctly(tmp_path):
    bank = write_file(
        tmp_path, "bank.csv", BANK_HEADER + "TXN-0001,2026-01-05,PIX ACME,100.00\n"
    )
    invoices = write_file(
        tmp_path, "invoices.csv", INVOICE_HEADER + "INV-0001,2026-01-01,Acme,100.00\n"
    )

    bank_df, invoices_df = load_data(bank, invoices)

    assert list(bank_df.columns) == ["transaction_id", "date", "description", "amount"]
    assert len(bank_df) == 1
    assert list(invoices_df.columns) == ["invoice_id", "issue_date", "customer", "amount"]
    assert invoices_df.loc[0, "invoice_id"] == "INV-0001"
    assert invoices_df.loc[0, "amount"] == 100.0


# Checks that a file missing the amount column raises a ValueError that names the column.
def test_missing_column_raises_value_error(tmp_path):
    bank = write_file(
        tmp_path, "bank.csv", "transaction_id,date,description\nTXN-0001,2026-01-05,PIX\n"
    )
    invoices = write_file(
        tmp_path, "invoices.csv", INVOICE_HEADER + "INV-0001,2026-01-01,Acme,100.00\n"
    )

    with pytest.raises(ValueError, match="amount"):
        load_data(bank, invoices)


# Checks that a completely empty file raises a ValueError that says it is empty.
def test_empty_file_raises_value_error(tmp_path):
    bank = write_file(tmp_path, "bank.csv", "")
    invoices = write_file(
        tmp_path, "invoices.csv", INVOICE_HEADER + "INV-0001,2026-01-01,Acme,100.00\n"
    )

    with pytest.raises(ValueError, match="empty"):
        load_data(bank, invoices)
