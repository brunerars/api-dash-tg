from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.security import APIKeyHeader

from routers.analysis import router

api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

_DESCRIPTION = """
## dash-tg API — eSoccer Dashboard

Processa arquivos `.xlsx` de tips e retorna métricas por dupla de jogadores.

### Fluxo típico

1. `GET /strategies` — lista as estratégias disponíveis
2. `POST /analyze` — envia os arquivos e escolhe a estratégia → recebe `cache_key`
3. `GET /export/{cache_key}` — baixa o resultado como `.xlsx`

### Autenticação

Todas as rotas (exceto `/health`) exigem o header:
```
X-API-Key: <sua_chave>
```

Clique em **Authorize** acima e cole sua chave para testar direto no Swagger.
"""

_TAGS = [
    {
        "name": "análise",
        "description": "Processamento de arquivos e cálculo de métricas por estratégia.",
    },
    {
        "name": "export",
        "description": "Download do resultado de uma análise já processada como `.xlsx`.",
    },
    {
        "name": "cache",
        "description": "Administração do cache Redis. Uso interno.",
    },
    {
        "name": "infra",
        "description": "Health check do serviço.",
    },
]

app = FastAPI(
    title="dash-tg API",
    description=_DESCRIPTION,
    version="1.1.0",
    openapi_tags=_TAGS,
    swagger_ui_parameters={"persistAuthorization": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["infra"], summary="Health check")
def health() -> dict:
    """Retorna `ok` se o serviço está no ar. Não requer autenticação."""
    return {"status": "ok"}


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        tags=_TAGS,
        routes=app.routes,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }
    for path in schema.get("paths", {}).values():
        for operation in path.values():
            if isinstance(operation, dict) and operation.get("tags") != ["infra"]:
                operation.setdefault("security", [{"ApiKeyAuth": []}])
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
