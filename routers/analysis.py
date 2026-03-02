from __future__ import annotations

import io
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from config.strategies import ESTRATEGIAS, get_strategy_internal
from esoccer_dashboard.services.cache import (
    delete_cache_key,
    gerar_cache_key,
    get_cache_stats,
    get_export,
    get_or_compute,
    store_export,
)
from esoccer_dashboard.services.deduplicator import deduplicate_clusters
from esoccer_dashboard.services.loader import load_tips_enviadas
from esoccer_dashboard.services.metrics import compute_metrics
from esoccer_dashboard.services.normalizer import add_dupla_normalizada
from middleware.auth import verify_api_key

router = APIRouter()

AuthDep = Annotated[str, Depends(verify_api_key)]


# ---------------------------------------------------------------------------
# Adapter: FastAPI UploadFile → UploadedLike (protocolo do loader)
# ---------------------------------------------------------------------------
class _UploadFileAdapter:
    def __init__(self, filename: str, content: bytes) -> None:
        self.name = filename
        self._content = content

    def getvalue(self) -> bytes:
        return self._content


# ---------------------------------------------------------------------------
# GET /strategies
# ---------------------------------------------------------------------------
@router.get("/strategies")
def list_strategies() -> dict:
    return {
        "strategies": [
            {
                "id": name,
                "descricao": cfg["descricao"],
                "min_jogos": cfg["min_jogos"],
                "min_green_pct": cfg["min_green_pct"],
            }
            for name, cfg in ESTRATEGIAS.items()
        ]
    }


# ---------------------------------------------------------------------------
# POST /analyze
# ---------------------------------------------------------------------------
@router.post("/analyze")
async def analyze(
    _key: AuthDep,
    files: list[UploadFile] = File(...),
    strategy: str = Form(...),
) -> dict:
    estrategia = get_strategy_internal(strategy)
    if estrategia is None:
        raise HTTPException(
            status_code=422,
            detail=f"Estratégia '{strategy}' não encontrada. Use GET /strategies para listar as disponíveis.",
        )

    # Ler bytes de todos os arquivos
    files_contents: list[tuple[str, bytes]] = []
    for uf in files:
        content = await uf.read()
        files_contents.append((uf.filename or "arquivo.xlsx", content))

    files_bytes = [c for _, c in files_contents]
    cache_key = gerar_cache_key(files_bytes, strategy)

    def compute() -> dict:
        adapters = [_UploadFileAdapter(name, content) for name, content in files_contents]

        # 1. Carregar
        load_result = load_tips_enviadas(adapters)

        # 2. Normalizar dupla
        df = add_dupla_normalizada(load_result.df)

        # 3. Deduplicar — usando dedup_key da estratégia
        dedup_result = deduplicate_clusters(
            df,
            dedup_key=estrategia["dedup_key_internal"],
        )

        # 4. Calcular métricas — usando group_by e janela_horas da estratégia
        metrics_result = compute_metrics(
            dedup_result.df,
            group_by=estrategia["group_by_internal"],
            sistema_red_janela_horas=estrategia["sistema_red_janela_horas"],
        )

        # 5. Aplicar filtros — usando min_jogos e min_green_pct da estratégia
        mdf = metrics_result.df
        if not mdf.empty:
            mdf = mdf[
                (mdf["quantidade_entradas"] >= estrategia["min_jogos"])
                & (mdf["percentual_green"] >= estrategia["min_green_pct"])
            ].copy()

        # 6. Serializar para dict (JSON-safe)
        duplas = mdf.to_dict(orient="records") if not mdf.empty else []
        for row in duplas:
            for k, v in row.items():
                if hasattr(v, "item"):
                    row[k] = v.item()

        # 7. Gerar e armazenar xlsx para export
        _store_xlsx(mdf, cache_key)

        return {
            "cache_key": cache_key,
            "strategy": strategy,
            "total_jogos_brutos": load_result.total_jogos_brutos,
            "total_jogos_apos_dedup": dedup_result.total_jogos_apos_dedup,
            "duplas": duplas,
        }

    result, cache_hit = get_or_compute(cache_key, compute)
    result["cache_hit"] = cache_hit
    return result


def _store_xlsx(df: pd.DataFrame, cache_key: str) -> None:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Análise")
    store_export(cache_key, buf.getvalue())


# ---------------------------------------------------------------------------
# GET /export/{cache_key}
# ---------------------------------------------------------------------------
@router.get("/export/{cache_key}")
def export_xlsx(_key: AuthDep, cache_key: str) -> StreamingResponse:
    xlsx_bytes = get_export(cache_key)
    if xlsx_bytes is None:
        raise HTTPException(
            status_code=404,
            detail="Export não encontrado. Rode /analyze primeiro ou o cache expirou (TTL 1h).",
        )
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=analise_{cache_key[:8]}.xlsx"},
    )


# ---------------------------------------------------------------------------
# GET /cache/status
# ---------------------------------------------------------------------------
@router.get("/cache/status")
def cache_status(_key: AuthDep) -> dict:
    try:
        return get_cache_stats()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Redis indisponível: {exc}") from exc


# ---------------------------------------------------------------------------
# DELETE /cache/{cache_key}
# ---------------------------------------------------------------------------
@router.delete("/cache/{cache_key}")
def invalidate_cache(_key: AuthDep, cache_key: str) -> dict:
    deleted = delete_cache_key(cache_key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cache key não encontrada.")
    return {"deleted": True, "cache_key": cache_key}
