"""Validate the matcher on synthetic data with new seeds and new names, to test generalization.

Analysis only: this script does not change the matcher, the sample data or the tests.
It has its own generator, so the original generator and its seed are not touched.
Run from the project root:  python scripts/validate_generalization.py
"""

import random
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "sample"
OUTPUT_DIR = ROOT / "output"
sys.path.insert(0, str(ROOT / "src"))

from reconcile.matcher import _similarity, match_transactions  # noqa: E402

VALIDATION_SEEDS = [2024, 7]  # seeds not used by the original generator
INVOICE_COUNT = 200
MISSING_PAYMENTS = 15       # invoices with no real payment; anchors for decoys
EXTRA_TRANSACTIONS = 15     # bank transactions that match no invoice
AMOUNT_MISMATCHES = 12      # paid invoices where the bank amount is slightly off
LATE_SHARE = 0.5            # share of the other paid invoices that are paid late
DATE_WINDOW_DAYS = 2        # exact window
LATE_MIN_DAYS = 3
LATE_MAX_DAYS = 30
DECOY_A_COUNT = 8           # similar name, paid 35-60 days after the invoice
DECOY_B_COUNT = 7           # different name, paid inside the exact window
FAR_MIN_DAYS = 35
FAR_MAX_DAYS = 60
MAX_DROP = 0.05             # a drop above 5 percentage points is reported
WORST_CASES = 5
BANK_FEES = [1.5, 2.0, 5.0, 10.0]

# Customer names that the original generator does not use.
NEW_CUSTOMERS = [
    "Iota Atacadista S.A.",
    "Xis Calçados Ltda",
    "Psi Papelaria ME",
    "Theta Sistemas Eireli",
    "Rho Agropecuária",
    "Nu Transportes Ltda",
]
# Names for type B decoys, clearly different from every customer above.
NEW_OTHER_NAMES = ["Mu Engenharia", "Chi Modas", "Tau Móveis", "Upsilon Gráfica"]
# Bank words put in front of the name, as in real statements.
BANK_PREFIXES = ["PIX", "TED", "TRANSF", "PAGTO"]
ABBREVIATIONS = {
    "Atacadista": "Atac.",
    "Calçados": "Calç.",
    "Papelaria": "Papel.",
    "Sistemas": "Sist.",
    "Agropecuária": "Agrop.",
    "Transportes": "Transp.",
    "Limitada": "Ltda.",
}
SUFFIX_VARIANTS = {
    "S.A.": ["SA", "S/A"],
    "ME": ["M.E.", "M E"],
    "Eireli": ["E.I.R.E.L.I", "EIRELI"],
}
EXTRA_DESCRIPTIONS = ["TARIFA MENSAL", "CREDITO JUROS", "ESTORNO PIX", "DEVOLUCAO TED"]


# Runs the matcher on the original sample and on each new seed, prints a table, and reports big drops.
def main():
    original = load_original_sample()
    runs = [("original sample", original)]
    for seed in VALIDATION_SEEDS:
        runs.append((f"seed {seed}", make_data(seed)))

    rows = []
    errors_by_run = {}
    for label, (bank, invoices, truth) in runs:
        metrics, errors = evaluate(bank, invoices, truth)
        rows.append({"run": label, **metrics})
        errors_by_run[label] = errors

    table = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT_DIR / "validation.csv", index=False)

    print("=== Results (default parameters: exact 2 days, fuzzy 30 days, min similarity 0.6) ===")
    print(table.to_string(index=False))
    print(f"\nSaved to {OUTPUT_DIR / 'validation.csv'}")

    original_row = table.iloc[0]
    for _, row in table.iloc[1:].iterrows():
        precision_drop = original_row["precision"] - row["precision"]
        coverage_drop = original_row["coverage"] - row["coverage"]
        if precision_drop > MAX_DROP or coverage_drop > MAX_DROP:
            print(f"\nWARNING ({row['run']}): precision or coverage dropped by more than 5 percentage points.")
            print(f"  precision drop: {precision_drop * 100:.2f} points, coverage drop: {coverage_drop * 100:.2f} points")
            print(f"  5 worst cases (errors sorted by lowest name similarity):")
            print(errors_by_run[row["run"]].head(WORST_CASES).to_string(index=False))


# Loads the original sample files, read-only, keeping empty answers as empty text.
def load_original_sample():
    bank = pd.read_csv(SAMPLE_DIR / "bank_transactions.csv")
    invoices = pd.read_csv(SAMPLE_DIR / "invoices.csv")
    truth = pd.read_csv(SAMPLE_DIR / "ground_truth.csv", keep_default_na=False)
    return bank, invoices, truth


# Builds bank, invoices and answer key for one seed, using the new names and prefixes.
def make_data(seed):
    rng = random.Random(seed)
    invoices = make_invoices(rng)
    bank_rows = make_bank_transactions(rng, invoices)
    bank = pd.DataFrame(bank_rows, columns=["transaction_id", "date", "description", "amount"])
    truth = pd.DataFrame(bank_rows, columns=["transaction_id", "expected_invoice_id"])
    invoices_df = pd.DataFrame(invoices, columns=["invoice_id", "issue_date", "customer", "amount"])
    return bank, invoices_df, truth


# Runs the matcher with default parameters and returns the metrics plus a table of every error.
def evaluate(bank, invoices, truth):
    result = match_transactions(bank, invoices)  # default parameters, unchanged
    merged = result.merge(truth, on="transaction_id")

    expected_total = int((merged["expected_invoice_id"] != "").sum())
    matched = merged[merged["invoice_id"] != ""]
    correct = int((matched["invoice_id"] == matched["expected_invoice_id"]).sum())
    total_matches = len(matched)

    metrics = {
        "expected_matches": expected_total,
        "correct_matches": correct,
        "false_matches": total_matches - correct,
        "total_matches": total_matches,
        "precision": round(correct / total_matches, 4) if total_matches else 0.0,
        "coverage": round(correct / expected_total, 4) if expected_total else 0.0,
        "unmatched_rows": int((result["match_stage"] == "unmatched").sum()),
    }
    return metrics, build_error_table(bank, invoices, merged)


# Lists each wrong result (a missed expected pair or a false match) with its names and similarity, lowest similarity first.
def build_error_table(bank, invoices, merged):
    errors = merged[merged["invoice_id"] != merged["expected_invoice_id"]].copy()
    errors = errors[(errors["expected_invoice_id"] != "") | (errors["invoice_id"] != "")]
    descriptions = bank.set_index("transaction_id")["description"]
    customers = invoices.set_index("invoice_id")["customer"]

    rows = []
    for _, row in errors.iterrows():
        invoice_id = row["expected_invoice_id"] or row["invoice_id"]
        description = descriptions[row["transaction_id"]]
        customer = customers[invoice_id]
        rows.append({
            "transaction_id": row["transaction_id"],
            "error_type": "missed" if row["expected_invoice_id"] else "false match",
            "bank_description": description,
            "invoice_customer": customer,
            "similarity": round(_similarity(description, customer), 4),
        })
    table = pd.DataFrame(rows, columns=[
        "transaction_id", "error_type", "bank_description", "invoice_customer", "similarity",
    ])
    return table.sort_values("similarity").reset_index(drop=True)


# Creates the invoice list, with random issue dates in the first half of 2026 and new customer names.
def make_invoices(rng):
    invoices = []
    for number in range(1, INVOICE_COUNT + 1):
        issue_date = date(2026, 1, 1) + timedelta(days=rng.randint(0, 180))
        invoices.append({
            "invoice_id": f"INV-{number:04d}",
            "issue_date": issue_date.isoformat(),
            "customer": rng.choice(NEW_CUSTOMERS),
            "amount": round(rng.uniform(50, 5000), 2),
        })
    return invoices


# Returns a bank-style description: a random bank prefix, then the customer name with random changes.
def make_bank_name(rng, customer):
    name = customer
    for full, short in ABBREVIATIONS.items():
        if full in name and rng.random() < 0.5:
            name = name.replace(full, short)
    for full, variants in SUFFIX_VARIANTS.items():
        if full in name and rng.random() < 0.5:
            name = name.replace(full, rng.choice(variants))
    if rng.random() < 0.5:
        name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    if rng.random() < 0.4:
        name = name.upper()
    elif rng.random() < 0.3:
        name = name.lower()
    if rng.random() < 0.3:
        name = name.replace(" ", "  ")
    if rng.random() < 0.25:
        name = name + "."
    if rng.random() < 0.3:
        name = _swap_letters(rng, name)
    return rng.choice(BANK_PREFIXES) + " " + name


# Swaps two neighbouring characters at a random spot, to imitate a typing mistake.
def _swap_letters(rng, text):
    if len(text) < 4:
        return text
    pos = rng.randint(1, len(text) - 3)
    return text[:pos] + text[pos + 1] + text[pos] + text[pos + 2:]


# Creates bank rows: paid invoices, unrelated extras, and decoys built on unpaid invoices.
def make_bank_transactions(rng, invoices):
    shuffled = invoices[:]
    rng.shuffle(shuffled)
    unpaid = shuffled[:MISSING_PAYMENTS]
    paid = shuffled[MISSING_PAYMENTS:]
    mismatched_ids = {inv["invoice_id"] for inv in paid[:AMOUNT_MISMATCHES]}

    rows = []
    for inv in paid:
        amount = inv["amount"]
        expected = inv["invoice_id"]
        if inv["invoice_id"] in mismatched_ids:
            amount = round(amount - rng.choice(BANK_FEES), 2)
            expected = ""  # the amount is wrong, so it should stay unmatched
            days = rng.randint(0, DATE_WINDOW_DAYS)
        elif rng.random() < LATE_SHARE:
            days = rng.randint(LATE_MIN_DAYS, LATE_MAX_DAYS)
        else:
            days = rng.randint(0, DATE_WINDOW_DAYS)
        pay_date = date.fromisoformat(inv["issue_date"]) + timedelta(days=days)
        rows.append({
            "date": pay_date.isoformat(),
            "description": make_bank_name(rng, inv["customer"]),
            "amount": amount,
            "expected_invoice_id": expected,
        })

    for _ in range(EXTRA_TRANSACTIONS):
        extra_date = date(2026, 1, 1) + timedelta(days=rng.randint(0, 210))
        rows.append({
            "date": extra_date.isoformat(),
            "description": rng.choice(EXTRA_DESCRIPTIONS),
            "amount": round(rng.uniform(5, 800), 2),
            "expected_invoice_id": "",
        })

    for index, inv in enumerate(unpaid):
        if index < DECOY_A_COUNT:
            # Type A: same amount, similar name, paid far from the invoice date.
            days = rng.randint(FAR_MIN_DAYS, FAR_MAX_DAYS)
            description = make_bank_name(rng, inv["customer"])
        elif index < DECOY_A_COUNT + DECOY_B_COUNT:
            # Type B: same amount, clearly different name, paid inside the exact window.
            days = rng.randint(0, DATE_WINDOW_DAYS)
            description = rng.choice(BANK_PREFIXES) + " " + rng.choice(NEW_OTHER_NAMES).upper()
        else:
            continue
        pay_date = date.fromisoformat(inv["issue_date"]) + timedelta(days=days)
        rows.append({
            "date": pay_date.isoformat(),
            "description": description,
            "amount": inv["amount"],
            "expected_invoice_id": "",  # a decoy must never be matched to its invoice
        })

    rows.sort(key=lambda row: row["date"])
    for number, row in enumerate(rows, start=1):
        row["transaction_id"] = f"TXN-{number:04d}"
    return rows


if __name__ == "__main__":
    main()
