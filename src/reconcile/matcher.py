"""Match bank transactions to invoices in two stages: exact first, then fuzzy by name."""

import difflib
import re
import unicodedata

import pandas as pd

BANK_PREFIX_PATTERN = re.compile(r"\b(pix|ted|transf|pagto)\b")  # bank words to ignore in names


# Matches each bank transaction to at most one invoice, exact matches first, then fuzzy matches.
def match_transactions(bank_df, invoices_df, date_window_days=2, min_similarity=0.6, fuzzy_date_window_days=30):
    bank_rows = bank_df.sort_values("transaction_id").to_dict("records")
    invoices = _prepare_invoices(invoices_df)
    used_invoices = set()
    matches = {}  # transaction_id -> (invoice_id, stage, score)

    # Stage 1: exact amount and close date.
    for tx in bank_rows:
        invoice = _find_exact(tx, invoices, used_invoices, date_window_days, min_similarity)
        if invoice is not None:
            used_invoices.add(invoice["invoice_id"])
            matches[tx["transaction_id"]] = (invoice["invoice_id"], "exact", 1.0)

    # Stage 2: same amount, date within the fuzzy window, and similar customer name; only for unmatched rows.
    for tx in bank_rows:
        if tx["transaction_id"] in matches:
            continue
        invoice, score = _find_fuzzy(tx, invoices, used_invoices, fuzzy_date_window_days, min_similarity)
        if invoice is not None:
            used_invoices.add(invoice["invoice_id"])
            matches[tx["transaction_id"]] = (invoice["invoice_id"], "fuzzy", score)

    return _build_result(bank_rows, matches)


# Converts the invoices table into a sorted list of plain dictionaries with rounded amounts and real dates.
def _prepare_invoices(invoices_df):
    invoices = []
    for row in invoices_df.to_dict("records"):
        invoices.append({
            "invoice_id": row["invoice_id"],
            "amount": round(float(row["amount"]), 2),
            "date": pd.Timestamp(row["issue_date"]),
            "customer": str(row["customer"]),
        })
    return sorted(invoices, key=lambda inv: inv["invoice_id"])


# Finds the unused invoice with the same amount and closest date, within the window and with a similar name.
def _find_exact(tx, invoices, used_invoices, date_window_days, min_similarity):
    tx_amount = round(float(tx["amount"]), 2)
    tx_date = pd.Timestamp(tx["date"])

    eligible = [
        inv for inv in invoices
        if inv["invoice_id"] not in used_invoices
        and inv["amount"] == tx_amount
        and _days_apart(tx_date, inv["date"]) <= date_window_days
        and _similarity(tx["description"], inv["customer"]) >= min_similarity
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda inv: (_days_apart(tx_date, inv["date"]), inv["invoice_id"]))


# Finds the unused invoice with the same amount, a date inside the window, and the most similar name.
def _find_fuzzy(tx, invoices, used_invoices, date_window_days, min_similarity):
    tx_amount = round(float(tx["amount"]), 2)
    tx_date = pd.Timestamp(tx["date"])

    scored = []  # each item: (similarity, days apart, invoice)
    for inv in invoices:
        if inv["invoice_id"] in used_invoices or inv["amount"] != tx_amount:
            continue
        gap = _days_apart(tx_date, inv["date"])
        if gap > date_window_days:
            continue
        score = _similarity(tx["description"], inv["customer"])
        scored.append((score, gap, inv))
    if not scored:
        return None, None

    best_score, _, best_invoice = sorted(
        scored, key=lambda item: (-item[0], item[1], item[2]["invoice_id"])
    )[0]
    if best_score < min_similarity:
        return None, None
    return best_invoice, round(best_score, 4)


# Returns the number of whole days between two dates, ignoring order.
def _days_apart(first, second):
    return abs((first - second).days)


# Lowercases a name, removes accents, dots, commas, hyphens and bank prefixes, and collapses spaces.
def normalize_name(text):
    text = unicodedata.normalize("NFKD", str(text).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[.,\-]", "", text)
    text = BANK_PREFIX_PATTERN.sub(" ", text)
    return " ".join(text.split())


# Returns a similarity score from 0 to 1 between two names, after normalizing both.
def _similarity(text_a, text_b):
    return difflib.SequenceMatcher(None, normalize_name(text_a), normalize_name(text_b)).ratio()


# Builds the result table with one row per bank transaction, in transaction_id order.
def _build_result(bank_rows, matches):
    rows = []
    for tx in bank_rows:
        if tx["transaction_id"] in matches:
            invoice_id, stage, score = matches[tx["transaction_id"]]
        else:
            invoice_id, stage, score = "", "unmatched", None
        rows.append({
            "transaction_id": tx["transaction_id"],
            "invoice_id": invoice_id,
            "match_stage": stage,
            "match_score": score,
        })
    return pd.DataFrame(rows, columns=["transaction_id", "invoice_id", "match_stage", "match_score"])
