"""Run the whole reconciliation, from input files to report tables and summary."""

from reconcile.data_loader import load_data
from reconcile.matcher import match_transactions
from reconcile.report import build_report, build_summary


# Loads the two files, matches them, and returns the summary and the three report tables in one dict.
def run_pipeline(bank_path, invoices_path, date_window_days=2, min_similarity=0.6, fuzzy_date_window_days=30):
    bank_df, invoices_df = load_data(bank_path, invoices_path)
    matches_df = match_transactions(
        bank_df,
        invoices_df,
        date_window_days=date_window_days,
        min_similarity=min_similarity,
        fuzzy_date_window_days=fuzzy_date_window_days,
    )
    report = build_report(bank_df, invoices_df, matches_df)
    summary = build_summary(bank_df, invoices_df, matches_df)
    return {
        "summary": summary,
        "reconciled": report["reconciled"],
        "pending_bank": report["pending_bank"],
        "pending_invoices": report["pending_invoices"],
    }
