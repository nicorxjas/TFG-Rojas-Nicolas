import asyncio
import base64
import json
import os
from typing import Any, Optional

import httpx
from fastapi import HTTPException


def load_backend_env() -> None:
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip("'\" "))


load_backend_env()


_CLIENTS: dict[int, httpx.AsyncClient] = {}


def _client() -> httpx.AsyncClient:
    loop_id = id(asyncio.get_running_loop())
    client = _CLIENTS.get(loop_id)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=30, max_keepalive_connections=12, keepalive_expiry=30.0),
        )
        _CLIENTS[loop_id] = client
    return client


async def close_clients() -> None:
    for client in list(_CLIENTS.values()):
        await client.aclose()
    _CLIENTS.clear()


def supabase_url() -> str:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise HTTPException(status_code=500, detail="SUPABASE_URL no esta configurado")
    return url


def service_role_key() -> str:
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not key:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY no esta configurado")
    return key


def service_headers(prefer: str = "return=representation") -> dict[str, str]:
    key = service_role_key()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def decode_jwt_sub(token: str) -> str:
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token invalido") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="No se pudo identificar el usuario")
    return user_id


def user_id_from_authorization(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization requerido")
    token = authorization.replace("Bearer ", "").strip()
    return decode_jwt_sub(token)


async def rest_get(table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    resp = await _client().get(
        f"{supabase_url()}/rest/v1/{table}",
        headers=service_headers(""),
        params=params,
        timeout=15.0,
    )
    if resp.status_code not in (200, 206):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


async def rest_post(
    table: str,
    payload: dict[str, Any] | list[dict[str, Any]],
    *,
    params: Optional[dict[str, Any]] = None,
    prefer: str = "return=representation",
) -> list[dict[str, Any]]:
    resp = await _client().post(
        f"{supabase_url()}/rest/v1/{table}",
        headers=service_headers(prefer),
        params=params or {},
        json=payload,
        timeout=20.0,
    )
    if resp.status_code not in (200, 201, 204):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json() if resp.text else []


async def rest_patch(
    table: str,
    payload: dict[str, Any],
    *,
    params: dict[str, Any],
    prefer: str = "return=representation",
) -> list[dict[str, Any]]:
    resp = await _client().patch(
        f"{supabase_url()}/rest/v1/{table}",
        headers=service_headers(prefer),
        params=params,
        json=payload,
        timeout=15.0,
    )
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json() if resp.text else []


async def rest_delete(table: str, *, params: dict[str, Any]) -> None:
    resp = await _client().delete(
        f"{supabase_url()}/rest/v1/{table}",
        headers=service_headers(""),
        params=params,
        timeout=20.0,
    )
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
