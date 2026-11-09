"""Streamlit dashboard for auto-reconcile: upload or use sample files, tune parameters, view results."""

import io
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Lets this file import the reconcile package from the src folder.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from reconcile.pipeline import run_pipeline  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parent / "data" / "sample"
SAMPLE_BANK = SAMPLE_DIR / "bank_transactions.csv"
SAMPLE_INVOICES = SAMPLE_DIR / "invoices.csv"

# Display names for the match stages; only used on screen, never in the data or CSV files.
STAGE_LABELS = {"exact": "Exata", "fuzzy": "Aproximada", "unmatched": "Não conciliada"}


# Runs the pipeline on the file contents; cached, so the same inputs do not run again.
@st.cache_data
def run_cached(bank_bytes, bank_name, invoices_bytes, invoices_name,
               date_window_days, min_similarity, fuzzy_date_window_days):
    bank_file = io.BytesIO(bank_bytes)
    bank_file.name = bank_name
    invoices_file = io.BytesIO(invoices_bytes)
    invoices_file.name = invoices_name
    return run_pipeline(
        bank_file, invoices_file, date_window_days, min_similarity, fuzzy_date_window_days
    )


# Formats a number as Brazilian currency with two decimals, for example R$ 40.807,35.
def format_brl(value):
    text = f"{value:,.2f}"
    return "R$ " + text.replace(",", "X").replace(".", ",").replace("X", ".")


# Shows one table on screen, and a CSV download button that always saves the original values.
def show_table(df, file_name, display_df=None):
    st.dataframe(df if display_df is None else display_df)
    st.download_button(
        "Baixar CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=file_name,
        mime="text/csv",
    )


# Draws the whole page: explanation, data source, parameters, metrics, chart and result tables.
def main():
    st.set_page_config(page_title="Auto-Reconcile", layout="wide")
    st.title("Auto-Reconcile: conciliação bancária")
    st.caption("Cruza o extrato bancário com as faturas e aponta o que não bate.")

    with st.expander("Como funciona", expanded=True):
        st.markdown(
            "**Regra 1: correspondência exata.** Uma transação casa com uma fatura quando o "
            "valor é igual e a data está dentro da janela de datas da conciliação exata "
            "(2 dias por padrão). Se houver mais de "
            "uma fatura possível, vence a de data mais próxima.\n\n"
            "**Regra 2: correspondência aproximada.** Só para transações que não casaram na "
            "regra 1. O valor precisa ser igual, a data precisa estar dentro da janela de datas "
            "da conciliação aproximada (30 dias por padrão), e o nome do cliente precisa ser parecido com a descrição do banco, acima "
            "da similaridade mínima escolhida. Nunca casamos apenas pela descrição.\n\n"
            "**Privacidade.** Ao rodar localmente, os arquivos são processados apenas na memória "
            "do seu computador. Ao publicar em nuvem, os arquivos são processados nos servidores "
            "da plataforma de hospedagem. Use somente dados sintéticos ou anonimizados."
        )

    st.sidebar.header("Dados")
    source = st.sidebar.radio("Fonte dos dados", ["Arquivos de exemplo", "Enviar meus arquivos"])

    if source == "Enviar meus arquivos":
        bank_upload = st.sidebar.file_uploader("Extrato bancário (CSV)", type="csv")
        invoices_upload = st.sidebar.file_uploader("Faturas (CSV)", type="csv")
        if bank_upload is None or invoices_upload is None:
            st.info("Envie os dois arquivos CSV na barra lateral para ver o resultado.")
            st.stop()
        bank_bytes, bank_name = bank_upload.getvalue(), bank_upload.name
        invoices_bytes, invoices_name = invoices_upload.getvalue(), invoices_upload.name
    else:
        bank_bytes, bank_name = SAMPLE_BANK.read_bytes(), SAMPLE_BANK.name
        invoices_bytes, invoices_name = SAMPLE_INVOICES.read_bytes(), SAMPLE_INVOICES.name

    st.sidebar.header("Parâmetros")
    date_window_days = st.sidebar.slider("Janela de datas, conciliação exata (dias)", 0, 7, 2)
    min_similarity = st.sidebar.slider("Similaridade mínima do nome", 0.0, 1.0, 0.6, step=0.05)
    fuzzy_date_window_days = st.sidebar.slider(
        "Janela de datas, conciliação aproximada (dias)", 0, 60, 30,
        help="Usada só na correspondência aproximada, para pagamentos atrasados.",
    )

    try:
        result = run_cached(
            bank_bytes, bank_name, invoices_bytes, invoices_name,
            date_window_days, min_similarity, fuzzy_date_window_days,
        )
    except ValueError as error:
        st.error(f"Não foi possível processar os arquivos: {error}")
        st.stop()

    summary = result["summary"]
    row1 = st.columns(2)
    row1[0].metric("Taxa de conciliação", f"{summary['reconciled_rate'] * 100:.1f}%")
    row1[1].metric("Transações conciliadas", summary["reconciled_count"])
    row2 = st.columns(2)
    row2[0].metric("Valor pendente no banco", format_brl(summary["pending_bank_amount"]))
    row2[1].metric("Valor de faturas pendentes", format_brl(summary["pending_invoice_amount"]))

    st.subheader("Como as transações foram casadas")
    exact_count = summary["exact_count"]
    fuzzy_count = summary["fuzzy_count"]
    unmatched_count = len(result["pending_bank"])
    chart_data = pd.DataFrame({
        "Tipo": [STAGE_LABELS["exact"], STAGE_LABELS["fuzzy"], STAGE_LABELS["unmatched"]],
        "Transações": [exact_count, fuzzy_count, unmatched_count],
    })
    st.bar_chart(chart_data, x="Tipo", y="Transações")
    st.caption(
        f"Exata: {exact_count}  ·  Aproximada: {fuzzy_count}  ·  "
        f"Não conciliada: {unmatched_count}"
    )

    reconciled_view = (
        result["reconciled"]
        .drop(columns=["match_score"])
        .assign(match_stage=lambda df: df["match_stage"].map(STAGE_LABELS))
    )

    tab1, tab2, tab3 = st.tabs(["Conciliadas", "Pendentes no banco", "Faturas pendentes"])
    with tab1:
        show_table(result["reconciled"], "reconciled.csv", reconciled_view)
    with tab2:
        show_table(result["pending_bank"], "pending_bank.csv")
    with tab3:
        show_table(result["pending_invoices"], "pending_invoices.csv")


main()
