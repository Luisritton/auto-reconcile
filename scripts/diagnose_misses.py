"""Diagnose why expected matches were missed, count false matches, and sweep the fuzzy date window.

Analysis only: this script does not change the matcher, the generator or the tests.
Run from the project root:  python scripts/diagnose_misses.py
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "sample"
OUTPUT_DIR = ROOT / "output"
sys.path.insert(0, str(ROOT / "src"))

from reconcile.matcher import _days_apart, _similarity, match_transactions  # noqa: E402

EXACT_WINDOW = 2       # exact window used for the diagnosis
FUZZY_WINDOW = 30      # default fuzzy window (same as the matcher default)
MIN_SIMILARITY = 0.6   # default similarity threshold
SWEEP_WINDOWS = [7, 15, 30, 45]
DATE_BINS = [-1, 2, 7, 15, 30, float("inf")]
DATE_BIN_LABELS = ["0-2 days", "3-7 days", "8-15 days", "16-30 days", "over 30 days"]


# Loads the sample bank transactions, invoices, answer key and decoy list, keeping empty answers as empty text.
def load_sample():
    bank = pd.read_csv(SAMPLE_DIR / "bank_transactions.csv")
    invoices = pd.read_csv(SAMPLE_DIR / "invoices.csv")
    truth = pd.read_csv(SAMPLE_DIR / "ground_truth.csv", keep_default_na=False)
    decoys = pd.read_csv(SAMPLE_DIR / "decoys.csv", keep_default_na=False)
    decoy_types = dict(zip(decoys["transaction_id"], decoys["decoy_type"]))
    return bank, invoices, truth, decoy_types


# Builds one row per expected match, with the matcher's answer and the numbers needed to explain a miss.
def build_pairs(bank, invoices, truth, result):
    bank_by_id = bank.set_index("transaction_id")
    invoices_by_id = invoices.set_index("invoice_id")
    result_by_tx = result.set_index("transaction_id")
    taken = {inv_id: tx_id for tx_id, inv_id in zip(result.transaction_id, result.invoice_id) if inv_id}

    rows = []
    for _, pair in truth[truth["expected_invoice_id"] != ""].iterrows():
        tx = bank_by_id.loc[pair.transaction_id]
        inv = invoices_by_id.loc[pair.expected_invoice_id]
        matched = result_by_tx.loc[pair.transaction_id, "invoice_id"]
        taken_by = taken.get(pair.expected_invoice_id)
        rows.append({
            "transaction_id": pair.transaction_id,
            "expected_invoice_id": pair.expected_invoice_id,
            "matched_invoice_id": matched,
            "match_stage": result_by_tx.loc[pair.transaction_id, "match_stage"],
            "correct": matched == pair.expected_invoice_id,
            "tx_date": tx["date"],
            "inv_date": inv["issue_date"],
            "tx_description": tx["description"],
            "inv_customer": inv["customer"],
            "tx_amount": round(float(tx["amount"]), 2),
            "inv_amount": round(float(inv["amount"]), 2),
            "amount_equal": round(float(tx["amount"]), 2) == round(float(inv["amount"]), 2),
            "date_diff_days": _days_apart(pd.Timestamp(tx["date"]), pd.Timestamp(inv["issue_date"])),
            "similarity": round(_similarity(tx["description"], inv["customer"]), 4),
            "taken_by_other": taken_by is not None and taken_by != pair.transaction_id,
        })
    return pd.DataFrame(rows)


# Gives the first reason, in the order requested, that explains why one expected match was missed.
def classify_reason(row):
    if row["taken_by_other"]:
        return "expected invoice taken by another transaction"
    if not row["amount_equal"]:
        return "amount differs"
    if row["date_diff_days"] > EXACT_WINDOW:
        return "date outside exact window"
    if row["date_diff_days"] > FUZZY_WINDOW and row["similarity"] >= MIN_SIMILARITY:
        return "date outside fuzzy window"
    if row["similarity"] < MIN_SIMILARITY:
        return "name similarity below threshold"
    return "other (unexpected)"


# Names the blocker that the fuzzy stage would hit for an equal-amount miss: the date or the name.
def fuzzy_blocker(row):
    if row["date_diff_days"] > FUZZY_WINDOW:
        return "date beyond fuzzy window"
    if row["similarity"] < MIN_SIMILARITY:
        return "name below threshold (date inside window)"
    return "none (fuzzy should have matched)"


# Gives the date-difference bucket (0-2, 3-7, ...) for one number of days.
def date_bucket(days):
    return pd.cut([days], bins=DATE_BINS, labels=DATE_BIN_LABELS)[0]


# Lists every match that points to an invoice other than the expected one, with its stage and decoy type.
def find_false_matches(result, truth, decoy_types):
    merged = result.merge(truth, on="transaction_id")
    wrong = merged[
        (merged["invoice_id"] != "") & (merged["invoice_id"] != merged["expected_invoice_id"])
    ].copy()
    wrong["decoy_type"] = wrong["transaction_id"].map(decoy_types).fillna("")
    return wrong


# Gives the min, median and max normalized name similarity for correct exact, correct fuzzy, false matches and missed pairs.
def similarity_table(pairs, wrong, bank, invoices):
    wrong_full = wrong.merge(bank[["transaction_id", "description"]], on="transaction_id")
    wrong_full = wrong_full.merge(invoices[["invoice_id", "customer"]], on="invoice_id")
    false_scores = [_similarity(d, c) for d, c in zip(wrong_full["description"], wrong_full["customer"])]
    groups = {
        "Correct exact": pairs.loc[pairs["correct"] & (pairs["match_stage"] == "exact"), "similarity"].tolist(),
        "Correct fuzzy": pairs.loc[pairs["correct"] & (pairs["match_stage"] == "fuzzy"), "similarity"].tolist(),
        "False matches (decoys)": false_scores,
        "Missed expected pairs": pairs.loc[~pairs["correct"], "similarity"].tolist(),
    }
    rows = []
    for name, values in groups.items():
        s = pd.Series(values, dtype=float)
        rows.append({
            "group": name,
            "count": len(s),
            "min": round(s.min(), 4) if len(s) else None,
            "median": round(s.median(), 4) if len(s) else None,
            "max": round(s.max(), 4) if len(s) else None,
        })
    return pd.DataFrame(rows)


# Runs the matcher with several fuzzy windows and reports precision, coverage and unmatched totals.
def sweep_fuzzy_windows(bank, invoices, truth, expected_fuzzy_ids):
    rows = []
    for window in SWEEP_WINDOWS:
        result = match_transactions(
            bank, invoices,
            date_window_days=EXACT_WINDOW,
            min_similarity=MIN_SIMILARITY,
            fuzzy_date_window_days=window,
        )
        fuzzy = result[result["match_stage"] == "fuzzy"].merge(truth, on="transaction_id")
        correct = int((fuzzy["invoice_id"] == fuzzy["expected_invoice_id"]).sum())
        fuzzy_count = len(fuzzy)
        rows.append({
            "fuzzy_window_days": window,
            "fuzzy_count": fuzzy_count,
            "correct_fuzzy": correct,
            "precision": round(correct / fuzzy_count, 4) if fuzzy_count else 0.0,
            "coverage": round(correct / len(expected_fuzzy_ids), 4) if expected_fuzzy_ids else 0.0,
            "total_unmatched": int((result["match_stage"] == "unmatched").sum()),
        })
    return pd.DataFrame(rows)


# Runs the full diagnosis: summary, reasons, false matches, precision, remaining misses, sweep and CSV output.
def main():
    bank, invoices, truth, decoy_types = load_sample()
    result = match_transactions(bank, invoices)  # default parameters

    pairs = build_pairs(bank, invoices, truth, result)
    pairs["reason"] = ""
    pairs["fuzzy_blocker"] = ""
    missed_mask = ~pairs["correct"]
    pairs.loc[missed_mask, "reason"] = pairs[missed_mask].apply(classify_reason, axis=1)
    equal_amount_missed = missed_mask & pairs["amount_equal"] & ~pairs["taken_by_other"]
    pairs.loc[equal_amount_missed, "fuzzy_blocker"] = pairs[equal_amount_missed].apply(fuzzy_blocker, axis=1)

    total = len(pairs)
    correct = int(pairs["correct"].sum())
    print("=== Summary ===")
    print(f"Total expected matches: {total}")
    print(f"Correctly matched:      {correct}")
    print(f"Missed:                 {total - correct}")
    print(f"Coverage:               {correct / total:.4f}")

    print("\n=== Missed pairs per reason (first reason in the requested order) ===")
    print(pairs.loc[missed_mask, "reason"].value_counts().to_string())

    print("\n=== Root cause for missed pairs with equal amount (what blocks the fuzzy stage) ===")
    print(pairs.loc[equal_amount_missed, "fuzzy_blocker"].value_counts().to_string())

    missed_df = pairs[missed_mask].copy()
    missed_df["date_bucket"] = missed_df["date_diff_days"].apply(date_bucket)
    print("\n=== Date differences of missed pairs ===")
    histogram = missed_df["date_bucket"].value_counts().reindex(DATE_BIN_LABELS, fill_value=0)
    print(histogram.to_string())

    print("\n=== 10 worst cases (largest date gap first, then lowest similarity) ===")
    worst = missed_df.sort_values(["date_diff_days", "similarity"], ascending=[False, True]).head(10)
    print(worst.to_string(index=False))

    remaining = pairs[equal_amount_missed & (pairs["date_diff_days"] > EXACT_WINDOW)]
    print(f"\n=== Expected fuzzy pairs still unmatched at a {FUZZY_WINDOW}-day window: {len(remaining)} ===")
    print(remaining[[
        "transaction_id", "expected_invoice_id", "tx_description", "inv_customer",
        "tx_amount", "inv_amount", "amount_equal", "date_diff_days", "similarity", "fuzzy_blocker",
    ]].to_string(index=False))

    wrong = find_false_matches(result, truth, decoy_types)
    print("\n=== False matches (matched to an invoice that is not the expected one) ===")
    print(f"Total false matches: {len(wrong)}")
    print(wrong.groupby(["match_stage", "decoy_type"]).size().rename("count").to_string())

    fuzzy_rows = result[result["match_stage"] == "fuzzy"].merge(truth, on="transaction_id")
    fuzzy_rows["is_decoy"] = fuzzy_rows["transaction_id"].isin(decoy_types.keys())
    fuzzy_ordinary = fuzzy_rows[~fuzzy_rows["is_decoy"]]
    fuzzy_ok = int((fuzzy_ordinary["invoice_id"] == fuzzy_ordinary["expected_invoice_id"]).sum())
    print("\n=== Precision, fuzzy stage ===")
    print(f"Fuzzy matches on ordinary rows: {len(fuzzy_ordinary)}, correct: {fuzzy_ok}, "
          f"precision: {fuzzy_ok / len(fuzzy_ordinary):.4f}" if len(fuzzy_ordinary) else
          "Fuzzy matches on ordinary rows: 0")
    print(f"Fuzzy matches on decoy rows (all wrong by design): {int(fuzzy_rows['is_decoy'].sum())}")

    print("\n=== Normalized name similarity by group (print only, no threshold change) ===")
    print(similarity_table(pairs, wrong, bank, invoices).to_string(index=False))

    expected_fuzzy_ids = set(
        pairs.loc[pairs["amount_equal"] & (pairs["date_diff_days"] > EXACT_WINDOW), "transaction_id"]
    )
    print("\n=== Fuzzy window sweep (exact window 2, min similarity 0.6) ===")
    print(f"Expected fuzzy pairs (equal amount, date outside exact window): {len(expected_fuzzy_ids)}")
    sweep = sweep_fuzzy_windows(bank, invoices, truth, expected_fuzzy_ids)
    print(sweep.to_string(index=False))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    columns = [
        "transaction_id", "expected_invoice_id", "matched_invoice_id", "match_stage",
        "tx_amount", "inv_amount", "amount_equal", "tx_date", "inv_date", "date_diff_days",
        "tx_description", "inv_customer", "similarity", "taken_by_other",
        "reason", "fuzzy_blocker", "date_bucket",
    ]
    missed_df[columns].to_csv(OUTPUT_DIR / "diagnosis.csv", index=False)
    print(f"\nSaved {len(missed_df)} missed pairs to {OUTPUT_DIR / 'diagnosis.csv'}")


if __name__ == "__main__":
    main()
