from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


_REQUIRED_ALWAYS = ("DataHora", "__source_file")


@dataclass(frozen=True)
class DedupResult:
    df: pd.DataFrame
    total_jogos_apos_dedup: int


def deduplicate_clusters(
    df: pd.DataFrame,
    dedup_key: list[str],
    window_minutes: int = 5,
) -> DedupResult:
    """
    Deduplicação por cluster (≤ window_minutes) seguindo o CLAUDE.md:
    - agrupa por dedup_key (ex: ["DuplaNormalizada", "Data"])
    - diferença de horário ≤ janela entre linhas de arquivos diferentes
    - manter apenas a linha com horário mais tardio dentro do cluster
      quando houver múltiplos arquivos

    O dedup_key é definido pela estratégia — nunca hardcoded aqui.
    """
    required = list(_REQUIRED_ALWAYS) + [c for c in dedup_key if c not in _REQUIRED_ALWAYS]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Deduplicação requer colunas: {missing}")

    if df.empty:
        return DedupResult(df=df.copy(), total_jogos_apos_dedup=0)

    td = pd.Timedelta(minutes=window_minutes)
    keep_indices: list[int] = []

    df_sorted = df.sort_values("DataHora")
    grouped = df_sorted.groupby(dedup_key, sort=False)
    for _, g in grouped:
        g = g.sort_values("DataHora")
        diffs = g["DataHora"].diff()
        cluster_id = (diffs.isna() | (diffs > td)).cumsum()

        for _, cg in g.groupby(cluster_id, sort=False):
            sources = cg["__source_file"].nunique(dropna=False)
            if sources >= 2:
                keep_indices.append(int(cg["DataHora"].idxmax()))
            else:
                keep_indices.extend(cg.index.tolist())

    out = df.loc[keep_indices].sort_values([dedup_key[0], "DataHora"], kind="stable").reset_index(drop=True)
    return DedupResult(df=out, total_jogos_apos_dedup=int(len(out)))
