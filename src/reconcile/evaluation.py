"""Compare the matcher output with the answer key, per stage and overall."""

import pandas as pd

from reconcile.matcher import match_transactions


# Runs the matcher with default parameters and returns precision and coverage for each stage and overall.
def evaluate_matches(bank_df, invoices_df, truth_df):
    result = match_transactions(bank_df, invoices_df)  # default parameters, unchanged
    merged = result.merge(truth_df, on="transaction_id")
    expected_total = int((merged["expected_invoice_id"] != "").sum())

    rows = []
    for stage in ["exact", "fuzzy", "overall"]:
        if stage == "overall":
            part = merged[merged["invoice_id"] != ""]
        else:
            part = merged[merged["match_stage"] == stage]
        matches = len(part)
        correct = int((part["invoice_id"] == part["expected_invoice_id"]).sum())
        rows.append({
            "stage": stage,
            "matches": matches,
            "correct": correct,
            "false_matches": matches - correct,
            "precision": round(correct / matches, 4) if matches else 0.0,
            "coverage": round(correct / expected_total, 4) if expected_total else 0.0,
        })

    table = pd.DataFrame(rows)
    return {
        "table": table,
        "expected_matches": expected_total,
        "false_matches": int(table.loc[table["stage"] == "overall", "false_matches"].iloc[0]),
        "unmatched_rows": int((result["match_stage"] == "unmatched").sum()),
    }
