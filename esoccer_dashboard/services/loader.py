from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable, Protocol

import pandas as pd


SHEET_NAME = "Tips Enviadas"
REQUIRED_COLUMNS = ("Torneio", "Confronto", "Data", "Hora", "Resultado", "Lucro/Prej.")


class UploadedLike(Protocol):
    name: str

    def getvalue(self) -> bytes: ...


@dataclass(frozen=True)
class LoadResult:
    df: pd.DataFrame
    total_jogos_brutos: int


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _ensure_required_columns(df: pd.DataFrame, source_name: str) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Arquivo '{source_name}' não tem as colunas obrigatórias na aba '{SHEET_NAME}': {missing}"
        )


def _parse_date_series(s: pd.Series) -> pd.Series:
    dt = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
    dt = dt.fillna(pd.to_datetime(s, dayfirst=True, errors="coerce"))
    return dt.dt.date


def _parse_time_series(s: pd.Series) -> pd.Series:
    raw = s.astype(str).str.strip()
    dt = pd.to_datetime(raw, format="%H:%M:%S", errors="coerce")
    dt = dt.fillna(pd.to_datetime(raw, format="%H:%M", errors="coerce"))
    return dt.dt.time


def _parse_datetime_series(date_s: pd.Series, time_s: pd.Series) -> pd.Series:
    raw = date_s.astype(str).str.strip() + " " + time_s.astype(str).str.strip()
    dt = pd.to_datetime(raw, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    dt = dt.fillna(pd.to_datetime(raw, errors="coerce"))
    return dt


def _parse_lucro_series(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce").astype(float)
    raw = s.astype(str).str.strip().str.replace(" ", "", regex=False)
    raw = raw.str.replace(".", "", regex=False).where(raw.str.contains(","), raw)
    raw = raw.str.replace(",", ".", regex=False)
    return pd.to_numeric(raw, errors="coerce").astype(float)


def _normalize_resultado_series(s: pd.Series) -> pd.Series:
    raw = s.astype(str).str.strip().str.lower()
    mapped = raw.map({"green": "Green", "red": "Red"})
    return mapped


def load_tips_enviadas(files: Iterable[UploadedLike]) -> LoadResult:
    frames: list[pd.DataFrame] = []

    for uf in files:
        source_name = getattr(uf, "name", "arquivo.xlsx")
        content = uf.getvalue()
        bio = BytesIO(content)

        try:
            df = pd.read_excel(bio, sheet_name=SHEET_NAME)
        except ValueError as e:
            raise ValueError(f"Arquivo '{source_name}' não tem a aba '{SHEET_NAME}'.") from e

        df = _normalize_columns(df)
        _ensure_required_columns(df, source_name)

        # Manter colunas obrigatórias + opcionais presentes (ex: "Linha" para Over/HT)
        _optional = [c for c in ("Linha",) if c in df.columns]
        df = df.loc[:, list(REQUIRED_COLUMNS) + _optional].copy()
        df["__source_file"] = source_name

        df["Data"] = _parse_date_series(df["Data"])
        df["Hora"] = _parse_time_series(df["Hora"])
        df["DataHora"] = _parse_datetime_series(df["Data"], df["Hora"])

        df["Lucro/Prej."] = _parse_lucro_series(df["Lucro/Prej."])
        df["Resultado"] = _normalize_resultado_series(df["Resultado"])

        if df["DataHora"].isna().any():
            raise ValueError(
                f"Arquivo '{source_name}' tem linhas com Data/Hora inválidas na aba '{SHEET_NAME}'."
            )

        if df["Resultado"].isna().any():
            raise ValueError(
                f"Arquivo '{source_name}' tem linhas com Resultado inválido (esperado: Green/Red)."
            )

        frames.append(df)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return LoadResult(df=out, total_jogos_brutos=int(len(out)))

