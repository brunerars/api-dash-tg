from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = (
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


def _ensure_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Métricas requerem colunas: {missing}")


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


def _reds_after_red_same_day(resultados: np.ndarray, datas: np.ndarray) -> int:
    if resultados.size <= 1:
        return 0
    count = 0
    for i in range(resultados.size - 1):
        if resultados[i] == "Red" and resultados[i + 1] == "Red" and datas[i] == datas[i + 1]:
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


def compute_metrics(df: pd.DataFrame) -> MetricsResult:
    _ensure_columns(df)
    if df.empty:
        return MetricsResult(df=pd.DataFrame())

    df = df.sort_values(["DuplaNormalizada", "DataHora"], kind="stable").copy()

    rows: list[dict] = []
    for dupla, g in df.groupby("DuplaNormalizada", sort=False):
        g = g.sort_values("DataHora", kind="stable")

        resultados = g["Resultado"].to_numpy()
        datas = g["Data"].to_numpy()
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

        reds_apos_red = _reds_after_red_same_day(resultados, datas)
        sistema_red_pct = float((reds_apos_red / reds) * 100.0) if reds else 0.0

        lucro_total = float(pd.to_numeric(g["Lucro/Prej."], errors="coerce").fillna(0.0).sum())

        rows.append(
            {
                "dupla": str(dupla),
                "ligas": _unique_in_order(g["Torneio"]),
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
        )

    out = pd.DataFrame(rows)
    return MetricsResult(df=out)

