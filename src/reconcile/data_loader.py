"""Load the bank transactions and invoices CSV files and check their columns."""

import pandas as pd

BANK_COLUMNS = ["transaction_id", "date", "description", "amount"]
INVOICE_COLUMNS = ["invoice_id", "issue_date", "customer", "amount"]


# Loads both CSV files and returns them as a (bank_df, invoices_df) tuple.
def load_data(bank_path, invoices_path):
    bank_df = _read_csv(bank_path, BANK_COLUMNS, "Bank transactions")
    invoices_df = _read_csv(invoices_path, INVOICE_COLUMNS, "Invoices")
    return bank_df, invoices_df


# Reads one CSV file and raises a ValueError if it is empty or missing required columns.
def _read_csv(path, required_columns, label):
    file_name = getattr(path, "name", path)  # uploaded files carry their own name
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        raise ValueError(f"{label} file '{file_name}' is empty.")

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(
            f"{label} file '{file_name}' is missing required column(s): {', '.join(missing)}"
        )

    if df.empty:
        raise ValueError(f"{label} file '{file_name}' has a header but no data rows.")

    return df
