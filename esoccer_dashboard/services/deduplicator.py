from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


REQUIRED_COLUMNS = ("DuplaNormalizada", "Data", "DataHora", "__source_file")


@dataclass(frozen=True)
class DedupResult:
    df: pd.DataFrame
    total_jogos_apos_dedup: int


def _ensure_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Deduplicação requer colunas: {missing}")


def deduplicate_clusters(df: pd.DataFrame, window_minutes: int = 5) -> DedupResult:
    """
    Deduplicação por cluster (≤ window_minutes) seguindo o CLAUDE.md:
    - mesma DuplaNormalizada
    - mesmo dia (Data idêntica)
    - diferença de horário ≤ janela entre linhas de arquivos diferentes
    - manter apenas a linha com horário mais tardio dentro do cluster quando houver múltiplos arquivos
    """

    _ensure_columns(df)
    if df.empty:
        return DedupResult(df=df.copy(), total_jogos_apos_dedup=0)

    td = pd.Timedelta(minutes=window_minutes)
    kept_groups: list[pd.DataFrame] = []

    grouped = df.sort_values("DataHora").groupby(["DuplaNormalizada", "Data"], sort=False)
    for (_, _), g in grouped:
        g = g.sort_values("DataHora").copy()
        diffs = g["DataHora"].diff()
        cluster_id = (diffs.isna() | (diffs > td)).cumsum()
        g["__cluster_id"] = cluster_id.values

        for _, cg in g.groupby("__cluster_id", sort=False):
            sources = cg["__source_file"].nunique(dropna=False)
            if sources >= 2:
                idx = cg["DataHora"].idxmax()
                kept_groups.append(cg.loc[[idx]].drop(columns=["__cluster_id"]))
            else:
                kept_groups.append(cg.drop(columns=["__cluster_id"]))

    out = pd.concat(kept_groups, ignore_index=True)
    out = out.sort_values(["DuplaNormalizada", "DataHora"], kind="stable").reset_index(drop=True)
    return DedupResult(df=out, total_jogos_apos_dedup=int(len(out)))

