from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from esoccer_dashboard.services.deduplicator import deduplicate_clusters
from esoccer_dashboard.services.loader import load_tips_enviadas
from esoccer_dashboard.services.metrics import compute_metrics
from esoccer_dashboard.services.normalizer import add_dupla_normalizada

MIN_JOGOS_DEFAULT = 6
MIN_GREEN_DEFAULT = 35.0


def _export_xlsx(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Resultado")
    return bio.getvalue()


@st.cache_data(show_spinner=False)
def _run_pipeline(files_payload: tuple[tuple[str, bytes], ...]) -> dict:
    class _UF:
        def __init__(self, name: str, content: bytes) -> None:
            self.name = name
            self._content = content

        def getvalue(self) -> bytes:
            return self._content

    uploaded = [_UF(name, content) for name, content in files_payload]
    load_res = load_tips_enviadas(uploaded)
    df = add_dupla_normalizada(load_res.df)
    dedup_res = deduplicate_clusters(df, window_minutes=5)
    metrics_res = compute_metrics(dedup_res.df)

    return {
        "total_jogos_brutos": load_res.total_jogos_brutos,
        "total_jogos_apos_dedup": dedup_res.total_jogos_apos_dedup,
        "df_metrics": metrics_res.df,
    }


def main() -> None:
    st.set_page_config(
        page_title="Dashboard eSoccer",
        layout="wide",
    )

    st.title("Dashboard eSoccer — Análise de Duplas")
    st.caption("Upload de planilhas (.xlsx) → deduplicação ≤ 5 min → métricas por dupla.")

    files = st.file_uploader(
        "Selecione um ou mais arquivos .xlsx",
        type=["xlsx"],
        accept_multiple_files=True,
    )

    colA, colB, colC, colD = st.columns([1, 1, 1, 2])
    with colA:
        min_jogos = st.number_input("Mín. partidas", min_value=1, max_value=9999, value=MIN_JOGOS_DEFAULT)
    with colB:
        min_green = st.slider("Mín. % GREEN", min_value=0.0, max_value=100.0, value=MIN_GREEN_DEFAULT, step=1.0)
    with colC:
        min_srpt = st.number_input("Mín. SRPT", value=0.0, step=0.1)
    with colD:
        st.write("")
        run = st.button("Analisar", type="primary", disabled=not files)

    if not run:
        st.info("Faça o upload e clique em **Analisar**.")
        return

    try:
        payload = tuple((f.name, f.getvalue()) for f in files)
        with st.spinner("Processando (loader → normalização → dedup → métricas)..."):
            out = _run_pipeline(payload)
    except Exception as e:
        st.error(str(e))
        return

    st.success(
        f"Bruto: {out['total_jogos_brutos']} linhas | Após dedup: {out['total_jogos_apos_dedup']} linhas"
    )

    dfm: pd.DataFrame = out["df_metrics"].copy()
    if dfm.empty:
        st.warning("Nenhuma dupla encontrada após processamento.")
        return

    dfm = dfm.loc[
        (dfm["quantidade_entradas"] >= int(min_jogos))
        & (dfm["percentual_green"] >= float(min_green))
        & (dfm["srpt"] >= float(min_srpt))
    ].copy()

    ligas_all = sorted({liga for cell in dfm["ligas"].astype(str) for liga in cell.split(" / ") if liga})
    selected_ligas = st.multiselect("Filtrar por ligas", options=ligas_all, default=[])
    if selected_ligas:
        dfm = dfm[dfm["ligas"].apply(lambda x: any(l in str(x).split(" / ") for l in selected_ligas))].copy()

    sort_col = st.selectbox(
        "Ordenar por",
        options=[
            "srpt",
            "percentual_green",
            "quantidade_entradas",
            "pontuacao",
            "lucro_prej_total",
        ],
        index=0,
    )
    dfm = dfm.sort_values(sort_col, ascending=False, kind="stable")

    st.dataframe(
        dfm,
        use_container_width=True,
        hide_index=True,
    )

    xlsx_bytes = _export_xlsx(dfm)
    st.download_button(
        "Baixar resultado (.xlsx)",
        data=xlsx_bytes,
        file_name="resultado_esoccer.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    main()
