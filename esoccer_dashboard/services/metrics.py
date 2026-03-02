from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


_FIXED_REQUIRED = (
    "DuplaNormalizada",
    "Torneio",
    "Data",
    "DataHora",
    "Resultado",
    "Lucro/Prej.",
)


@dataclass(frozen=True)
class MetricsResult:
    df: pd.DataFrame


def _unique_in_order(values: pd.Series) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for v in values.astype(str).tolist():
        if v not in seen:
            seen.add(v)
            out.append(v)
    return " / ".join(out)


def _map_gr(value: str) -> str:
    return "G" if value == "Green" else "R"


def _max_streak(flags: np.ndarray) -> int:
    if flags.size == 0:
        return 0
    best = 0
    cur = 0
    for f in flags:
        if f:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return int(best)


def _trailing_streak(flags: np.ndarray) -> int:
    if flags.size == 0:
        return 0
    cur = 0
    for f in flags[::-1]:
        if f:
            cur += 1
        else:
            break
    return int(cur)


def _reds_after_red(
    resultados: np.ndarray,
    datas: np.ndarray,
    datahoras: np.ndarray,
    janela_horas: int | None,
) -> int:
    """
    Conta pares consecutivos Red -> Red.

    janela_horas is None:
        Conta apenas quando ambos os reds ocorrem no mesmo dia (datas[i] == datas[i+1]).
    janela_horas = N:
        Conta quando mesmo dia OU quando a diferença entre DataHora é ≤ N horas
        (incluindo reds em dias diferentes mas próximos).
    """
    if resultados.size <= 1:
        return 0
    count = 0
    for i in range(resultados.size - 1):
        if resultados[i] != "Red" or resultados[i + 1] != "Red":
            continue
        if janela_horas is None:
            if datas[i] == datas[i + 1]:
                count += 1
        else:
            if datas[i] == datas[i + 1]:
                count += 1
            else:
                delta = pd.Timestamp(datahoras[i + 1]) - pd.Timestamp(datahoras[i])
                if delta.total_seconds() <= janela_horas * 3600:
                    count += 1
    return int(count)


def _srpt(resultados: np.ndarray) -> float:
    n = resultados.size
    if n == 0:
        return 0.0
    values = np.where(resultados == "Green", 1.0, -3.0)
    distances = (n - 1) - np.arange(n)
    weights = 0.5 ** (distances / 10.0)
    return float(np.sum(weights * values))


def compute_metrics(
    df: pd.DataFrame,
    group_by: list[str],
    sistema_red_janela_horas: int | None,
) -> MetricsResult:
    """
    Calcula as 16 métricas por grupo definido por group_by.

    group_by: ["DuplaNormalizada"] ou ["DuplaNormalizada", "Linha"]
    sistema_red_janela_horas: None = só mesmo dia / int = mesmo dia OU até N horas

    Definido pela estratégia — nunca hardcoded aqui.
    """
    required = list(_FIXED_REQUIRED) + [c for c in group_by if c not in _FIXED_REQUIRED]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Métricas requerem colunas: {missing}")

    if df.empty:
        return MetricsResult(df=pd.DataFrame())

    df = df.sort_values([group_by[0], "DataHora"], kind="stable").copy()

    rows: list[dict] = []
    for group_key, g in df.groupby(group_by, sort=False):
        g = g.sort_values("DataHora", kind="stable")

        resultados = g["Resultado"].to_numpy()
        datas = g["Data"].to_numpy()
        datahoras = g["DataHora"].to_numpy()
        total = int(len(g))
        greens = int(np.sum(resultados == "Green"))
        reds = int(np.sum(resultados == "Red"))

        ultimos_6_vals = g.tail(6)["Resultado"].tolist()
        ultimos_6 = "-".join(_map_gr(v) for v in ultimos_6_vals)

        last10 = g.tail(10)
        last10_total = int(len(last10))
        last10_greens = int(np.sum(last10["Resultado"].to_numpy() == "Green"))
        pct_green_10 = float((last10_greens / last10_total) * 100.0) if last10_total else 0.0

        pontuacao = int(np.sum(np.where(resultados == "Green", 1, -3)))

        is_red = resultados == "Red"
        is_green = resultados == "Green"

        max_reds = _max_streak(is_red)
        max_greens = _max_streak(is_green)
        sequencia_atual_g = _trailing_streak(is_green)

        reds_apos_red = _reds_after_red(resultados, datas, datahoras, sistema_red_janela_horas)
        sistema_red_pct = float((reds_apos_red / reds) * 100.0) if reds else 0.0

        lucro_total = float(pd.to_numeric(g["Lucro/Prej."], errors="coerce").fillna(0.0).sum())

        fontes: list[str] = sorted(g["__bet"].dropna().unique().tolist())

        # group_key é string quando group_by tem 1 coluna, tupla quando tem 2+
        if len(group_by) == 1:
            dupla_val = str(group_key)
            linha_val = None
        else:
            dupla_val = str(group_key[0])
            linha_val = str(group_key[1])

        row: dict = {
            "dupla": dupla_val,
            "ligas": _unique_in_order(g["Torneio"]),
            "fontes": fontes,
            "quantidade_entradas": total,
            "quantidade_greens": greens,
            "percentual_green": float((greens / total) * 100.0) if total else 0.0,
            "pontuacao": pontuacao,
            "ultimos_6": ultimos_6,
            "pct_green_10": pct_green_10,
            "quantidade_reds": reds,
            "max_reds": max_reds,
            "reds_apos_red": reds_apos_red,
            "sistema_red_pct": sistema_red_pct,
            "srpt": _srpt(resultados),
            "sequencia_atual_g": sequencia_atual_g,
            "max_greens": max_greens,
            "lucro_prej_total": lucro_total,
        }

        if linha_val is not None:
            row["linha"] = linha_val

        rows.append(row)

    out = pd.DataFrame(rows)
    return MetricsResult(df=out)
