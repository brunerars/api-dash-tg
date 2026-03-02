import os
from dotenv import load_dotenv

load_dotenv()

API_KEYS: set[str] = set(
    k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()
)

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

CACHE_TTL_ANALYSIS: int = int(os.getenv("CACHE_TTL_ANALYSIS", "86400"))
CACHE_TTL_EXPORT: int = int(os.getenv("CACHE_TTL_EXPORT", "3600"))
