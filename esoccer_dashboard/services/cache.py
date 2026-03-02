from __future__ import annotations

import base64
import hashlib
import json

import redis

from config.settings import REDIS_URL, CACHE_TTL_ANALYSIS, CACHE_TTL_EXPORT

_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=False)
    return _client


def gerar_cache_key(files_bytes: list[bytes], strategy: str) -> str:
    h = hashlib.md5()
    for b in sorted(files_bytes):
        h.update(b)
    h.update(strategy.encode())
    return h.hexdigest()


def get_or_compute(
    cache_key: str,
    compute_fn,
    ttl: int = CACHE_TTL_ANALYSIS,
) -> tuple[dict, bool]:
    r = get_redis_client()
    cached = r.get(f"analysis:{cache_key}")
    if cached:
        return json.loads(cached), True

    result = compute_fn()
    r.setex(f"analysis:{cache_key}", ttl, json.dumps(result))
    return result, False


def store_export(cache_key: str, xlsx_bytes: bytes) -> None:
    r = get_redis_client()
    encoded = base64.b64encode(xlsx_bytes).decode("ascii")
    r.setex(f"export:{cache_key}", CACHE_TTL_EXPORT, encoded)


def get_export(cache_key: str) -> bytes | None:
    r = get_redis_client()
    raw = r.get(f"export:{cache_key}")
    if raw is None:
        return None
    return base64.b64decode(raw)


def delete_cache_key(cache_key: str) -> bool:
    r = get_redis_client()
    deleted = r.delete(f"analysis:{cache_key}", f"export:{cache_key}")
    return deleted > 0


def get_cache_stats() -> dict:
    r = get_redis_client()
    info = r.info()
    keyspace = r.info("keyspace")

    total_chaves = sum(
        v.get("keys", 0) if isinstance(v, dict) else 0
        for v in keyspace.values()
    )

    memoria_bytes = info.get("used_memory", 0)
    if memoria_bytes >= 1_048_576:
        memoria_str = f"{memoria_bytes / 1_048_576:.2f} MB"
    elif memoria_bytes >= 1024:
        memoria_str = f"{memoria_bytes / 1024:.2f} KB"
    else:
        memoria_str = f"{memoria_bytes} B"

    hits = info.get("keyspace_hits", 0)
    misses = info.get("keyspace_misses", 0)
    total_ops = hits + misses
    hit_rate = f"{(hits / total_ops * 100):.1f}%" if total_ops else "0.0%"

    uptime_segundos = info.get("uptime_in_seconds", 0)
    uptime_horas = round(uptime_segundos / 3600, 1)

    return {
        "status": "ok",
        "total_chaves": total_chaves,
        "memoria_usada": memoria_str,
        "hits": hits,
        "misses": misses,
        "hit_rate": hit_rate,
        "uptime_horas": uptime_horas,
    }
