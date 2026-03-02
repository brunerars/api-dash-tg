from __future__ import annotations

# Mapeia os shorthands de documentação para os nomes reais de colunas do DataFrame.
_COL_MAP: dict[str, str] = {
    "Dupla": "DuplaNormalizada",
    "Linha": "Linha",
    "Data": "Data",
}


def _translate(keys: list[str]) -> list[str]:
    return [_COL_MAP.get(k, k) for k in keys]


ESTRATEGIAS: dict[str, dict] = {
    "eSoccer — Dupla": {
        "group_by": ["Dupla"],
        "dedup_key": ["Dupla", "Data"],
        "min_jogos": 6,
        "min_green_pct": 35,
        "sistema_red_janela_horas": None,
        "descricao": "Analisa por confronto entre jogadores",
    },
    "Over/HT — Dupla + Linha": {
        "group_by": ["Dupla", "Linha"],
        "dedup_key": ["Dupla", "Linha", "Data"],
        "min_jogos": 4,
        "min_green_pct": 65,
        "sistema_red_janela_horas": 12,
        "descricao": "Over e HT — analisa por confronto e linha de mercado",
    },
}
# Para adicionar nova estratégia: apenas adicionar entrada aqui.
# NUNCA alterar metrics.py ou deduplicator.py para isso.


def get_strategy_names() -> list[str]:
    return list(ESTRATEGIAS.keys())


def get_strategy(name: str) -> dict | None:
    return ESTRATEGIAS.get(name)


def get_strategy_internal(name: str) -> dict | None:
    """
    Retorna o config da estratégia com group_by e dedup_key já traduzidos
    para os nomes reais de colunas do DataFrame (group_by_internal, dedup_key_internal).
    """
    cfg = ESTRATEGIAS.get(name)
    if cfg is None:
        return None
    return {
        **cfg,
        "group_by_internal": _translate(cfg["group_by"]),
        "dedup_key_internal": _translate(cfg["dedup_key"]),
    }
