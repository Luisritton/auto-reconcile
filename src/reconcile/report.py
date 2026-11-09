"""Build reconciliation reports (matched pairs, pending items, summary) and write them to files."""

from pathlib import Path

import pandas as pd

REPORT_GROUPS = ["reconciled", "pending_bank", "pending_invoices"]
RECONCILED_COLUMNS = [
    "transaction_id", "invoice_id", "date_bank", "date_invoice",
    "customer", "amount", "match_stage", "match_score",
]
PENDING_BANK_COLUMNS = ["transaction_id", "date", "description", "amount"]
PENDING_INVOICE_COLUMNS = ["invoice_id", "issue_date", "customer", "amount"]


# Splits the data into reconciled and pending groups, and checks that no row was lost.
def build_report(bank_df, invoices_df, matches_df):
    matched = matches_df[matches_df["invoice_id"] != ""]

    bank_slim = bank_df.rename(columns={"date": "date_bank"})[
        ["transaction_id", "date_bank", "amount"]
    ]
    invoice_slim = invoices_df.rename(columns={"issue_date": "date_invoice"})[
        ["invoice_id", "date_invoice", "customer"]
    ]
    reconciled = matched.merge(bank_slim, on="transaction_id").merge(
        invoice_slim, on="invoice_id"
    )
    reconciled = reconciled[RECONCILED_COLUMNS].reset_index(drop=True)

    matched_bank_ids = set(matched["transaction_id"])
    matched_invoice_ids = set(matched["invoice_id"])
    pending_bank = bank_df[~bank_df["transaction_id"].isin(matched_bank_ids)]
    pending_bank = pending_bank[PENDING_BANK_COLUMNS].reset_index(drop=True)
    pending_invoices = invoices_df[~invoices_df["invoice_id"].isin(matched_invoice_ids)]
    pending_invoices = pending_invoices[PENDING_INVOICE_COLUMNS].reset_index(drop=True)

    _check_counts(reconciled, pending_bank, pending_invoices, bank_df, invoices_df)

    return {
        "reconciled": reconciled,
        "pending_bank": pending_bank,
        "pending_invoices": pending_invoices,
    }


# Raises a ValueError if the reconciled and pending groups do not add up to the original totals.
def _check_counts(reconciled, pending_bank, pending_invoices, bank_df, invoices_df):
    bank_total = len(reconciled) + len(pending_bank)
    if bank_total != len(bank_df):
        raise ValueError(
            f"Bank transaction count does not match: {len(reconciled)} reconciled + "
            f"{len(pending_bank)} pending = {bank_total}, but there are {len(bank_df)} "
            "bank transactions. Check matches_df for unknown transaction IDs."
        )

    invoice_total = len(reconciled) + len(pending_invoices)
    if invoice_total != len(invoices_df):
        raise ValueError(
            f"Invoice count does not match: {len(reconciled)} reconciled + "
            f"{len(pending_invoices)} pending = {invoice_total}, but there are "
            f"{len(invoices_df)} invoices. Check matches_df for unknown or duplicate invoice IDs."
        )


# Calculates the summary numbers (counts, rates and pending totals) for the reconciliation.
def build_summary(bank_df, invoices_df, matches_df):
    report = build_report(bank_df, invoices_df, matches_df)
    reconciled = report["reconciled"]
    total_bank = len(bank_df)

    rate = round(len(reconciled) / total_bank, 4) if total_bank else 0.0
    return {
        "total_bank_transactions": total_bank,
        "total_invoices": len(invoices_df),
        "reconciled_count": len(reconciled),
        "reconciled_rate": rate,
        "exact_count": int((reconciled["match_stage"] == "exact").sum()),
        "fuzzy_count": int((reconciled["match_stage"] == "fuzzy").sum()),
        "pending_bank_amount": round(float(report["pending_bank"]["amount"].sum()), 2),
        "pending_invoice_amount": round(float(report["pending_invoices"]["amount"].sum()), 2),
    }


# Writes the three groups as CSV files and all groups plus the summary as one Excel workbook.
def write_reports(report, summary, output_dir):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for name in REPORT_GROUPS:
        report[name].to_csv(output_path / f"{name}.csv", index=False)

    summary_df = pd.DataFrame(list(summary.items()), columns=["metric", "value"])
    with pd.ExcelWriter(output_path / "reconciliation.xlsx", engine="openpyxl") as writer:
        for name in REPORT_GROUPS:
            report[name].to_excel(writer, sheet_name=name, index=False)
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
