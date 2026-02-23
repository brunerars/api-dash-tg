from __future__ import annotations

from collections import Counter
import re
from dataclasses import dataclass

import pandas as pd


_VS_SPLIT_RE = re.compile(r"\s+vs\s+", flags=re.IGNORECASE)
_PARENS_RE = re.compile(r"\(([^()]*)\)")


@dataclass(frozen=True)
class PlayerName:
    base: str
    suffixes: tuple[str, ...]


def _extract_player_name(raw: str) -> PlayerName:
    raw = str(raw).strip()
    if not raw:
        return PlayerName(base="", suffixes=())

    suffixes_raw = _PARENS_RE.findall(raw)
    base = _PARENS_RE.sub("", raw).strip()

    suffixes: list[str] = []
    for s in suffixes_raw:
        normalized = " ".join(str(s).strip().split())
        if normalized:
            suffixes.append(normalized)

    return PlayerName(base=base, suffixes=tuple(suffixes))


def _dedupe_suffixes(suffixes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in suffixes:
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _redistribute_duplicated_suffixes(left: PlayerName, right: PlayerName) -> tuple[PlayerName, PlayerName]:
    """
    Heurística necessária para casos como:
    - "Cevuu vs Elmagico (2x6) (2x6)" -> "Cevuu (2x6) vs Elmagico (2x6)"

    Quando um lado tem o mesmo sufixo repetido (>=2) e o outro lado não tem,
    assumimos que o sufixo pertence a ambos os jogadores (uma vez para cada).
    """

    left_suffixes = list(left.suffixes)
    right_suffixes = list(right.suffixes)

    lc = Counter(s.casefold() for s in left_suffixes)
    rc = Counter(s.casefold() for s in right_suffixes)

    def has_exact(suffixes: list[str], key: str) -> bool:
        return any(s.casefold() == key for s in suffixes)

    # right duplicated -> add to left
    for s in right_suffixes:
        key = s.casefold()
        if rc[key] >= 2 and lc.get(key, 0) == 0 and not has_exact(left_suffixes, key):
            left_suffixes.append(s)

    # left duplicated -> add to right
    for s in left_suffixes:
        key = s.casefold()
        if lc[key] >= 2 and rc.get(key, 0) == 0 and not has_exact(right_suffixes, key):
            right_suffixes.append(s)

    left_norm = PlayerName(base=left.base, suffixes=tuple(_dedupe_suffixes(left_suffixes)))
    right_norm = PlayerName(base=right.base, suffixes=tuple(_dedupe_suffixes(right_suffixes)))
    return left_norm, right_norm


def _format_player_name(p: PlayerName) -> str:
    if not p.base:
        return ""
    if not p.suffixes:
        return p.base
    return p.base + " " + " ".join(f"({s})" for s in p.suffixes)


def normalize_dupla(confronto: str) -> str:
    raw = str(confronto).strip()
    parts = _VS_SPLIT_RE.split(raw, maxsplit=1)
    if len(parts) != 2:
        return raw

    left = _extract_player_name(parts[0])
    right = _extract_player_name(parts[1])
    left, right = _redistribute_duplicated_suffixes(left, right)

    left_key = left.base.casefold()
    right_key = right.base.casefold()

    a, b = (left, right) if left_key <= right_key else (right, left)
    return f"{_format_player_name(a)} vs {_format_player_name(b)}".strip()


def add_dupla_normalizada(df: pd.DataFrame, confronto_col: str = "Confronto") -> pd.DataFrame:
    out = df.copy()
    out["DuplaNormalizada"] = out[confronto_col].map(normalize_dupla)
    return out

