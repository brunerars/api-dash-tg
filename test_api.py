"""
Script para testar a API localmente — eSoccer — Dupla
Uso: python test_api.py
"""

import json
import sys
from pathlib import Path

import requests

BASE_URL = "http://localhost:8000"
API_KEY = "123"
STRATEGY = "eSoccer — Dupla"

FILES = [
    Path(r"C:\Users\Bruno\Desktop\api-tg\dash-tg\data\BETANO.xlsx"),
]


def test_strategies():
    print("\n=== GET /strategies ===")
    r = requests.get(f"{BASE_URL}/strategies")
    print(f"Status: {r.status_code}")
    data = r.json()
    print(json.dumps(data, indent=2, ensure_ascii=False))

    strategies = data.get("strategies", [])
    ids = [s["id"] for s in strategies]
    assert STRATEGY in ids, f"Estratégia '{STRATEGY}' não encontrada em {ids}"
    entry = next(s for s in strategies if s["id"] == STRATEGY)
    assert "min_jogos" in entry, "Campo min_jogos ausente"
    assert "min_green_pct" in entry, "Campo min_green_pct ausente"
    assert "descricao" in entry, "Campo descricao ausente"
    print(f"[OK] Estratégia encontrada: min_jogos={entry['min_jogos']}, min_green_pct={entry['min_green_pct']}")


def test_analyze():
    print("\n=== POST /analyze ===")

    missing = [f for f in FILES if not f.exists()]
    if missing:
        print(f"ERRO: arquivos não encontrados: {missing}")
        sys.exit(1)

    open_files = []
    try:
        multipart_files = []
        for path in FILES:
            fh = open(path, "rb")
            open_files.append(fh)
            multipart_files.append(("files", (path.name, fh)))

        r = requests.post(
            f"{BASE_URL}/analyze",
            headers={"X-API-Key": API_KEY},
            data={"strategy": STRATEGY},
            files=multipart_files,
        )
    finally:
        for fh in open_files:
            fh.close()

    print(f"Status: {r.status_code}")

    if r.status_code != 200:
        print("Erro:", r.text)
        return None

    data = r.json()
    print(f"cache_hit:              {data.get('cache_hit')}")
    print(f"cache_key:              {data.get('cache_key')}")
    print(f"strategy:               {data.get('strategy')}")
    print(f"total_jogos_brutos:     {data.get('total_jogos_brutos')}")
    print(f"total_jogos_apos_dedup: {data.get('total_jogos_apos_dedup')}")
    print(f"duplas retornadas:      {len(data.get('duplas', []))}")

    duplas = data.get("duplas", [])

    # Validações estruturais
    assert data.get("strategy") == STRATEGY, "strategy no response não bate"
    assert isinstance(data.get("cache_key"), str) and len(data["cache_key"]) == 32, "cache_key inválida"
    assert isinstance(data.get("total_jogos_brutos"), int), "total_jogos_brutos inválido"
    assert isinstance(data.get("total_jogos_apos_dedup"), int), "total_jogos_apos_dedup inválido"

    if duplas:
        d = duplas[0]
        # Campos obrigatórios — eSoccer não tem "linha"
        campos = [
            "dupla", "ligas", "quantidade_entradas", "quantidade_greens",
            "percentual_green", "pontuacao", "ultimos_6", "pct_green_10",
            "quantidade_reds", "max_reds", "reds_apos_red", "sistema_red_pct",
            "srpt", "sequencia_atual_g", "max_greens", "lucro_prej_total",
        ]
        for campo in campos:
            assert campo in d, f"Campo ausente na dupla: {campo}"
        assert "linha" not in d, "Campo 'linha' não deveria aparecer na estratégia eSoccer"

        # Validações de valor
        assert d["quantidade_entradas"] >= 6, "Filtro min_jogos=6 violado"
        assert d["percentual_green"] >= 35.0, "Filtro min_green_pct=35 violado"

        print("\nPrimeira dupla:")
        print(json.dumps(d, indent=2, ensure_ascii=False))
        print("[OK] Estrutura da dupla validada (16 campos, sem 'linha')")

    return data.get("cache_key")


def test_cache_hit(cache_key: str):
    print("\n=== POST /analyze (cache hit) ===")

    open_files = []
    try:
        multipart_files = []
        for path in FILES:
            fh = open(path, "rb")
            open_files.append(fh)
            multipart_files.append(("files", (path.name, fh)))

        r = requests.post(
            f"{BASE_URL}/analyze",
            headers={"X-API-Key": API_KEY},
            data={"strategy": STRATEGY},
            files=multipart_files,
        )
    finally:
        for fh in open_files:
            fh.close()

    data = r.json()
    assert data.get("cache_hit") is True, "Segunda chamada deveria ser cache hit"
    assert data.get("cache_key") == cache_key, "cache_key mudou entre chamadas"
    print(f"[OK] Cache hit confirmado — cache_key: {cache_key}")


def test_export(cache_key: str):
    print("\n=== GET /export/{cache_key} ===")
    r = requests.get(
        f"{BASE_URL}/export/{cache_key}",
        headers={"X-API-Key": API_KEY},
    )
    print(f"Status: {r.status_code}")
    assert r.status_code == 200, f"Export falhou: {r.text}"
    assert "spreadsheetml" in r.headers.get("content-type", ""), "Content-Type não é xlsx"

    out_path = Path(f"analise_{cache_key[:8]}.xlsx")
    out_path.write_bytes(r.content)
    print(f"[OK] Arquivo salvo: {out_path.resolve()}")


def test_cache_status():
    print("\n=== GET /cache/status ===")
    r = requests.get(
        f"{BASE_URL}/cache/status",
        headers={"X-API-Key": API_KEY},
    )
    print(f"Status: {r.status_code}")
    assert r.status_code == 200, f"Cache status falhou: {r.text}"
    data = r.json()
    print(json.dumps(data, indent=2, ensure_ascii=False))
    for campo in ["status", "total_chaves", "memoria_usada", "hits", "misses", "hit_rate", "uptime_horas"]:
        assert campo in data, f"Campo ausente no cache status: {campo}"
    assert data["status"] == "ok", "Redis não está ok"
    print("[OK] Cache status válido")


def test_auth_rejected():
    print("\n=== Auth: chave inválida deve retornar 401 ===")
    r = requests.get(f"{BASE_URL}/cache/status", headers={"X-API-Key": "chave-errada"})
    assert r.status_code == 401, f"Esperado 401, recebeu {r.status_code}"
    print("[OK] 401 retornado corretamente")


def test_invalid_strategy():
    print("\n=== POST /analyze: estratégia inválida deve retornar 422 ===")

    open_files = []
    try:
        multipart_files = []
        for path in FILES:
            fh = open(path, "rb")
            open_files.append(fh)
            multipart_files.append(("files", (path.name, fh)))

        r = requests.post(
            f"{BASE_URL}/analyze",
            headers={"X-API-Key": API_KEY},
            data={"strategy": "Estratégia Inexistente"},
            files=multipart_files,
        )
    finally:
        for fh in open_files:
            fh.close()

    assert r.status_code == 422, f"Esperado 422, recebeu {r.status_code}"
    print("[OK] 422 retornado corretamente")


if __name__ == "__main__":
    print("=" * 50)
    print(f"Testando: {BASE_URL}")
    print(f"Estratégia: {STRATEGY}")
    print("=" * 50)

    test_strategies()
    cache_key = test_analyze()
    if cache_key:
        test_cache_hit(cache_key)
        test_export(cache_key)
    test_cache_status()
    test_auth_rejected()
    test_invalid_strategy()

    print("\n" + "=" * 50)
    print("Todos os testes passaram.")
    print("=" * 50)
