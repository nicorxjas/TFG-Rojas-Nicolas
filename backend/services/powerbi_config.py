from typing import Any, Optional

from fastapi import HTTPException

from services import supabase_rest as sb
from services.powerbi_client import (
    DEFAULT_DELEGATED_SCOPES,
    PowerBIAppConfig,
    default_redirect_uri,
    env_app_config,
)
from services.token_crypto import seal_json, unseal_json


CONNECTOR_KEY = "powerbi"


def _normalize_tenant_id(value: Optional[str]) -> str:
    return (value or "common").strip() or "common"


def _normalize_redirect_uri(value: Optional[str]) -> str:
    return (value or default_redirect_uri()).strip() or default_redirect_uri()


def _normalize_scopes(value: Any) -> list[str]:
    if isinstance(value, list):
        scopes = [str(scope).strip() for scope in value if str(scope).strip()]
        return scopes or DEFAULT_DELEGATED_SCOPES
    return DEFAULT_DELEGATED_SCOPES


def _config_response(
    *,
    configured: bool,
    tenant_id: str,
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    source: str,
    secret_configured: bool,
) -> dict[str, Any]:
    return {
        "configured": configured,
        "source": source,
        "tenant_id": tenant_id,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "default_redirect_uri": default_redirect_uri(),
        "scopes": scopes,
        "secret_configured": secret_configured,
    }


async def get_saved_powerbi_app_config_row(user_id: str) -> Optional[dict[str, Any]]:
    rows = await sb.rest_get(
        "connector_app_configs",
        {
            "select": "*",
            "owner_user_id": f"eq.{user_id}",
            "connector_key": f"eq.{CONNECTOR_KEY}",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


async def get_saved_powerbi_secret(user_id: str) -> Optional[dict[str, Any]]:
    rows = await sb.rest_get(
        "connector_app_secrets",
        {
            "select": "*",
            "owner_user_id": f"eq.{user_id}",
            "connector_key": f"eq.{CONNECTOR_KEY}",
            "limit": "1",
        },
    )
    if not rows:
        return None
    return unseal_json(rows[0].get("secret_payload") or {})


async def get_powerbi_app_config_status(user_id: str) -> dict[str, Any]:
    row = await get_saved_powerbi_app_config_row(user_id)
    if row:
        return _config_response(
            configured=bool(row.get("client_id") and row.get("secret_configured")),
            tenant_id=_normalize_tenant_id(row.get("tenant_id")),
            client_id=row.get("client_id") or "",
            redirect_uri=_normalize_redirect_uri(row.get("redirect_uri")),
            scopes=_normalize_scopes(row.get("scopes")),
            source="database",
            secret_configured=bool(row.get("secret_configured")),
        )

    env_config = env_app_config()
    if env_config:
        return _config_response(
            configured=True,
            tenant_id=env_config.tenant_id,
            client_id=env_config.client_id,
            redirect_uri=env_config.redirect_uri,
            scopes=env_config.scopes,
            source="environment",
            secret_configured=True,
        )

    return _config_response(
        configured=False,
        tenant_id="common",
        client_id="",
        redirect_uri=default_redirect_uri(),
        scopes=DEFAULT_DELEGATED_SCOPES,
        source="missing",
        secret_configured=False,
    )


async def get_powerbi_app_config(user_id: str) -> Optional[PowerBIAppConfig]:
    row = await get_saved_powerbi_app_config_row(user_id)
    if row:
        secret = await get_saved_powerbi_secret(user_id)
        client_secret = (secret or {}).get("client_secret") or ""
        return PowerBIAppConfig(
            tenant_id=_normalize_tenant_id(row.get("tenant_id")),
            client_id=(row.get("client_id") or "").strip(),
            client_secret=client_secret,
            redirect_uri=_normalize_redirect_uri(row.get("redirect_uri")),
            scopes=_normalize_scopes(row.get("scopes")),
            source="database",
        )

    return env_app_config()


async def save_powerbi_app_config(
    *,
    user_id: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scopes: Optional[list[str]] = None,
) -> dict[str, Any]:
    normalized_client_id = client_id.strip()
    normalized_client_secret = client_secret.strip()
    normalized_tenant_id = _normalize_tenant_id(tenant_id)
    normalized_redirect_uri = _normalize_redirect_uri(redirect_uri)
    normalized_scopes = _normalize_scopes(scopes)

    existing_secret = await get_saved_powerbi_secret(user_id)
    has_secret = bool(normalized_client_secret or (existing_secret or {}).get("client_secret"))

    missing = []
    if not normalized_client_id:
        missing.append("client_id")
    if not has_secret:
        missing.append("client_secret")
    if not normalized_redirect_uri:
        missing.append("redirect_uri")
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "POWERBI_APP_CONFIG_INCOMPLETE",
                "message": "Completa Client ID, Client Secret y Redirect URI para conectar Power BI.",
                "missing": missing,
            },
        )

    rows = await sb.rest_post(
        "connector_app_configs",
        {
            "owner_user_id": user_id,
            "connector_key": CONNECTOR_KEY,
            "provider": "powerbi",
            "tenant_id": normalized_tenant_id,
            "client_id": normalized_client_id,
            "redirect_uri": normalized_redirect_uri,
            "scopes": normalized_scopes,
            "secret_configured": has_secret,
        },
        params={"on_conflict": "owner_user_id,connector_key"},
        prefer="resolution=merge-duplicates,return=representation",
    )

    if normalized_client_secret:
        await sb.rest_post(
            "connector_app_secrets",
            {
                "owner_user_id": user_id,
                "connector_key": CONNECTOR_KEY,
                "secret_payload": seal_json({"client_secret": normalized_client_secret}),
                "secret_version": 1,
            },
            params={"on_conflict": "owner_user_id,connector_key"},
            prefer="resolution=merge-duplicates",
        )

    row = rows[0]
    return _config_response(
        configured=True,
        tenant_id=_normalize_tenant_id(row.get("tenant_id")),
        client_id=row.get("client_id") or "",
        redirect_uri=_normalize_redirect_uri(row.get("redirect_uri")),
        scopes=_normalize_scopes(row.get("scopes")),
        source="database",
        secret_configured=True,
    )
