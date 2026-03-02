from fastapi import Header, HTTPException
from config.settings import API_KEYS


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="API Key inválida")
    return x_api_key
