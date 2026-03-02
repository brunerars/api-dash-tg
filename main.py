from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from routers.analysis import router

api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

app = FastAPI(
    title="dash-tg API",
    description="Dashboard eSoccer — Análise de duplas multi-estratégia",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, tags=["analysis"])


@app.get("/health", tags=["infra"])
def health() -> dict:
    return {"status": "ok"}
