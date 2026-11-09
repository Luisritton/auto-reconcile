"""Generate synthetic bank transactions, invoices and a ground-truth answer key for testing.

Run from the project root:  python src/reconcile/generate_sample.py
"""

import random
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SEED = 42                   # fixed seed so the same files are produced every run
INVOICE_COUNT = 200
MISSING_PAYMENTS = 15       # invoices with no real payment; these are the anchors for decoys
EXTRA_TRANSACTIONS = 15     # bank transactions that match no invoice
AMOUNT_MISMATCHES = 12      # paid invoices where the bank amount is slightly off
LATE_SHARE = 0.5            # share of the other paid invoices that are paid late
DATE_WINDOW_DAYS = 2        # the window the exact rule uses by default
LATE_MIN_DAYS = 3           # late payments come at least this many days after issue
LATE_MAX_DAYS = 30          # and at most this many, so some fall inside and some outside the window
DECOY_A_COUNT = 8           # decoys with a similar name but a date more than 30 days away
DECOY_B_COUNT = 7           # decoys with a different name and a date inside the exact window
FAR_MIN_DAYS = 35           # type A decoys are paid this many days or more after the invoice date
FAR_MAX_DAYS = 60           # and at most this many

CUSTOMERS = [
    "Acme Ltda",
    "Beta Comercio Limitada",
    "Gama Serviços",
    "Delta Tech",
    "Epsilon Logística",
    "Zeta Consultoria",
]
OTHER_NAMES = [              # clearly different from every customer above
    "Omega Importadora",
    "Sigma Construtora",
    "Kappa Viagens",
    "Lambda Pet Shop",
]
ABBREVIATIONS = {
    "Comercio": "Com.",
    "Consultoria": "Consult.",
    "Logística": "Log.",
    "Serviços": "Serv.",
    "Limitada": "Ltda.",
}
EXTRA_DESCRIPTIONS = [
    "TARIFA BANCARIA",
    "RENDIMENTO POUPANCA",
    "PIX RECEBIDO SEM REFERENCIA",
    "ESTORNO TED",
]
BANK_FEES = [1.5, 2.0, 5.0, 10.0]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"


# Creates all sample files, saves them in data/sample/, and prints how many rows of each kind exist.
def main():
    rng = random.Random(SEED)
    invoices = make_invoices(rng)
    bank_rows = make_bank_transactions(rng, invoices)

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    invoices_df = pd.DataFrame(
        invoices, columns=["invoice_id", "issue_date", "customer", "amount"]
    )
    bank_df = pd.DataFrame(
        bank_rows, columns=["transaction_id", "date", "description", "amount"]
    )
    truth_df = pd.DataFrame(
        bank_rows, columns=["transaction_id", "expected_invoice_id"]
    )
    decoys_df = pd.DataFrame(
        [
            {"transaction_id": row["transaction_id"], "decoy_type": row["kind"][-1]}
            for row in bank_rows
            if row["kind"].startswith("decoy_")
        ],
        columns=["transaction_id", "decoy_type"],
    )
    invoices_df.to_csv(SAMPLE_DIR / "invoices.csv", index=False)
    bank_df.to_csv(SAMPLE_DIR / "bank_transactions.csv", index=False)
    truth_df.to_csv(SAMPLE_DIR / "ground_truth.csv", index=False)
    decoys_df.to_csv(SAMPLE_DIR / "decoys.csv", index=False)

    print(f"Wrote {len(invoices_df)} invoices to {SAMPLE_DIR / 'invoices.csv'}")
    print(f"Wrote {len(bank_df)} transactions to {SAMPLE_DIR / 'bank_transactions.csv'}")
    print(f"Wrote {len(truth_df)} answers to {SAMPLE_DIR / 'ground_truth.csv'}")
    print(f"Wrote {len(decoys_df)} decoys to {SAMPLE_DIR / 'decoys.csv'}")
    print_counts(bank_rows)


# Prints how many generated rows belong to each kind, so the data can be checked by eye.
def print_counts(bank_rows):
    kinds = {}
    for row in bank_rows:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    print("Rows by kind:")
    print(f"  exact (date inside window, amount equal):           {kinds.get('exact', 0)}")
    print(f"  late (date outside exact window, name varied):      {kinds.get('late', 0)}")
    print(f"  amount differs slightly:                            {kinds.get('amount_mismatch', 0)}")
    print(f"  unmatched extras (no invoice):                      {kinds.get('extra', 0)}")
    print(f"  decoy A (similar name, date 35-60 days away):       {kinds.get('decoy_A', 0)}")
    print(f"  decoy B (different name, date inside exact window): {kinds.get('decoy_B', 0)}")


# Creates the invoice list, with random issue dates in the first half of 2026.
def make_invoices(rng):
    invoices = []
    for number in range(1, INVOICE_COUNT + 1):
        issue_date = date(2026, 1, 1) + timedelta(days=rng.randint(0, 180))
        invoices.append({
            "invoice_id": f"INV-{number:04d}",
            "issue_date": issue_date.isoformat(),
            "customer": rng.choice(CUSTOMERS),
            "amount": round(rng.uniform(50, 5000), 2),
        })
    return invoices


# Returns a bank-style version of a customer name, with random abbreviations, accents, case, spacing and typos.
def make_bank_name(rng, customer):
    name = customer
    for full, short in ABBREVIATIONS.items():
        if full in name and rng.random() < 0.5:
            name = name.replace(full, short)
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
    return name


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
            kind = "amount_mismatch"
            days = rng.randint(0, DATE_WINDOW_DAYS)
        elif rng.random() < LATE_SHARE:
            kind = "late"
            days = rng.randint(LATE_MIN_DAYS, LATE_MAX_DAYS)
        else:
            kind = "exact"
            days = rng.randint(0, DATE_WINDOW_DAYS)

        pay_date = date.fromisoformat(inv["issue_date"]) + timedelta(days=days)
        rows.append({
            "date": pay_date.isoformat(),
            "description": "PIX " + make_bank_name(rng, inv["customer"]),
            "amount": amount,
            "kind": kind,
            "expected_invoice_id": expected,
        })

    for _ in range(EXTRA_TRANSACTIONS):
        extra_date = date(2026, 1, 1) + timedelta(days=rng.randint(0, 210))
        rows.append({
            "date": extra_date.isoformat(),
            "description": rng.choice(EXTRA_DESCRIPTIONS),
            "amount": round(rng.uniform(5, 800), 2),
            "kind": "extra",
            "expected_invoice_id": "",
        })

    for index, inv in enumerate(unpaid):
        if index < DECOY_A_COUNT:
            # Type A: same amount, similar name, but paid far from the invoice date.
            days = rng.randint(FAR_MIN_DAYS, FAR_MAX_DAYS)
            kind = "decoy_A"
            description = "PIX " + make_bank_name(rng, inv["customer"])
        elif index < DECOY_A_COUNT + DECOY_B_COUNT:
            # Type B: same amount, clearly different name, date inside the exact window.
            days = rng.randint(0, DATE_WINDOW_DAYS)
            kind = "decoy_B"
            description = "PIX " + rng.choice(OTHER_NAMES).upper()
        else:
            continue
        pay_date = date.fromisoformat(inv["issue_date"]) + timedelta(days=days)
        rows.append({
            "date": pay_date.isoformat(),
            "description": description,
            "amount": inv["amount"],
            "kind": kind,
            "expected_invoice_id": "",  # a decoy must never be matched to its invoice
        })

    rows.sort(key=lambda row: row["date"])
    for number, row in enumerate(rows, start=1):
        row["transaction_id"] = f"TXN-{number:04d}"
    return rows


if __name__ == "__main__":
    main()
