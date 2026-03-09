from __future__ import annotations

import io
from datetime import date as date_type
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
from esoccer_dashboard.services.loader import LoadResult, load_tips_enviadas
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
# Helper interno: pipeline completo dado files_contents já em memória
# ---------------------------------------------------------------------------
async def _analyze_with_strategy(
    strategy_name: str,
    files_contents: list[tuple[str, bytes]],
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    estrategia = get_strategy_internal(strategy_name)  # garantido válido pelo chamador

    files_bytes = [c for _, c in files_contents]
    cache_key = gerar_cache_key(files_bytes, strategy_name, date_from, date_to)

    def compute() -> dict:
        adapters = [_UploadFileAdapter(name, content) for name, content in files_contents]

        # 1. Carregar
        load_result = load_tips_enviadas(adapters)
        df = load_result.df

        # 1b. Filtrar por período (se informado) — antes da normalização e dedup
        if date_from or date_to:
            if date_from:
                df = df[df["Data"] >= date_type.fromisoformat(date_from)]
            if date_to:
                df = df[df["Data"] <= date_type.fromisoformat(date_to)]
            if df.empty:
                raise HTTPException(
                    status_code=422,
                    detail="Nenhum jogo encontrado no período especificado.",
                )
            df = df.reset_index(drop=True)
            load_result = LoadResult(df=df, total_jogos_brutos=len(df))

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

        result: dict = {
            "cache_key": cache_key,
            "strategy": strategy_name,
            "total_jogos_brutos": load_result.total_jogos_brutos,
            "total_jogos_apos_dedup": dedup_result.total_jogos_apos_dedup,
            "duplas": duplas,
        }
        if date_from:
            result["date_from"] = date_from
        if date_to:
            result["date_to"] = date_to
        return result

    result, cache_hit = get_or_compute(cache_key, compute)
    result["cache_hit"] = cache_hit
    return result


# ---------------------------------------------------------------------------
# GET /strategies
# ---------------------------------------------------------------------------
@router.get("/strategies", tags=["análise"], summary="Listar estratégias disponíveis")
def list_strategies() -> dict:
    """Retorna as estratégias configuradas com seus parâmetros principais (`min_jogos`, `min_green_pct`).
    Use o campo `id` como valor do campo `strategy` no `/analyze`."""
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
# POST /analyze  (upload de arquivos)
# ---------------------------------------------------------------------------
@router.post(
    "/analyze",
    tags=["análise"],
    summary="Analisar arquivos (upload)",
    response_description="Métricas calculadas por dupla, com `cache_key` para export posterior.",
)
async def analyze(
    _key: AuthDep,
    files: list[UploadFile] = File(...),
    strategy: str = Form(...),
    date_from: str | None = Form(None, description="Data inicial do período (YYYY-MM-DD). Opcional."),
    date_to: str | None = Form(None, description="Data final do período (YYYY-MM-DD). Opcional."),
) -> dict:
    if get_strategy_internal(strategy) is None:
        raise HTTPException(
            status_code=422,
            detail=f"Estratégia '{strategy}' não encontrada. Use GET /strategies para listar as disponíveis.",
        )

    for label, value in (("date_from", date_from), ("date_to", date_to)):
        if value is not None:
            try:
                date_type.fromisoformat(value)
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail=f"'{label}' inválido: '{value}'. Use o formato YYYY-MM-DD.",
                )

    filenames = [uf.filename or "arquivo.xlsx" for uf in files]
    seen = set()
    duplicates = [f for f in filenames if f in seen or seen.add(f)]
    if duplicates:
        raise HTTPException(
            status_code=422,
            detail=f"Arquivos com nome repetido não são permitidos: {duplicates}",
        )

    files_contents: list[tuple[str, bytes]] = []
    for uf in files:
        content = await uf.read()
        files_contents.append((uf.filename or "arquivo.xlsx", content))

    return await _analyze_with_strategy(strategy, files_contents, date_from, date_to)



def _store_xlsx(df: pd.DataFrame, cache_key: str) -> None:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Análise")
    store_export(cache_key, buf.getvalue())


# ---------------------------------------------------------------------------
# GET /export/{cache_key}
# ---------------------------------------------------------------------------
@router.get("/export/{cache_key}", tags=["export"], summary="Baixar resultado como .xlsx")
def export_xlsx(_key: AuthDep, cache_key: str) -> StreamingResponse:
    """Retorna o resultado de uma análise já processada como arquivo `.xlsx`.
    O `cache_key` é obtido no response do `POST /analyze`. TTL do export: 1h."""
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
@router.get("/cache/status", tags=["cache"], summary="Status do Redis")
def cache_status(_key: AuthDep) -> dict:
    """Retorna estatísticas do Redis: total de chaves, memória, hit rate e uptime."""
    try:
        return get_cache_stats()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Redis indisponível: {exc}") from exc


# ---------------------------------------------------------------------------
# DELETE /cache/{cache_key}
# ---------------------------------------------------------------------------
@router.delete("/cache/{cache_key}", tags=["cache"], summary="Invalidar entrada do cache")
def invalidate_cache(_key: AuthDep, cache_key: str) -> dict:
    """Remove manualmente uma entrada do cache pelo `cache_key`."""
    deleted = delete_cache_key(cache_key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cache key não encontrada.")
    return {"deleted": True, "cache_key": cache_key}
