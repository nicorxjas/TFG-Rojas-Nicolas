import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException


POWERBI_API_BASE = "https://api.powerbi.com/v1.0/myorg"
POWERBI_RESOURCE_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
DEFAULT_DELEGATED_SCOPES = [
    "offline_access",
    "openid",
    "profile",
    "https://analysis.windows.net/powerbi/api/Dataset.Read.All",
    "https://analysis.windows.net/powerbi/api/Workspace.Read.All",
    "https://analysis.windows.net/powerbi/api/Report.Read.All",
    "https://analysis.windows.net/powerbi/api/Tenant.Read.All",
]


@dataclass
class PowerBIAppConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str]
    source: str = "database"


def default_redirect_uri() -> str:
    configured = os.getenv("POWERBI_REDIRECT_URI")
    if configured:
        return configured
    api_base = os.getenv("API_PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{api_base}/connectors/powerbi/callback"


def frontend_base_url() -> str:
    return os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")


def env_app_config() -> Optional[PowerBIAppConfig]:
    client_id = os.getenv("POWERBI_CLIENT_ID", "").strip()
    client_secret = os.getenv("POWERBI_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    return PowerBIAppConfig(
        tenant_id=os.getenv("POWERBI_TENANT_ID", "common").strip() or "common",
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=default_redirect_uri(),
        scopes=DEFAULT_DELEGATED_SCOPES,
        source="environment",
    )


def validate_app_config(app_config: Optional[PowerBIAppConfig]) -> list[str]:
    missing = []
    if not app_config:
        return ["client_id", "client_secret", "redirect_uri"]
    if not app_config.client_id:
        missing.append("client_id")
    if not app_config.client_secret:
        missing.append("client_secret")
    if not app_config.redirect_uri:
        missing.append("redirect_uri")
    return missing


def powerbi_config_required_error(missing: list[str]) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "code": "POWERBI_APP_CONFIG_REQUIRED",
            "message": "Configura la aplicacion de Microsoft Entra antes de conectar Power BI.",
            "missing": missing,
        },
    )


def _state_secret() -> bytes:
    secret = os.getenv("POWERBI_OAUTH_STATE_SECRET") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not secret:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "POWERBI_STATE_SECRET_REQUIRED",
                "message": "Falta configurar un secreto server-side para iniciar OAuth.",
            },
        )
    return secret.encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _unb64url(value: str) -> bytes:
    value += "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value.encode("utf-8"))


def sign_state(payload: dict[str, Any]) -> str:
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_state_secret(), body.encode("utf-8"), hashlib.sha256).digest()
    return f"{body}.{_b64url(sig)}"


def verify_state(state: str) -> dict[str, Any]:
    try:
        body, signature = state.split(".", 1)
        expected = _b64url(hmac.new(_state_secret(), body.encode("utf-8"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        payload = json.loads(_unb64url(body).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Estado OAuth invalido") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=400, detail="Estado OAuth expirado")
    return payload


def _token_endpoint(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id or 'common'}/oauth2/v2.0/token"


def _authorization_endpoint(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id or 'common'}/oauth2/v2.0/authorize"


def _friendly_microsoft_error(resp: httpx.Response, fallback: str) -> HTTPException:
    message = fallback
    try:
        payload = resp.json()
        description = payload.get("error_description") or payload.get("error")
        if description:
            message = "Microsoft rechazo la solicitud. Revisa el Tenant ID, Client ID, Client Secret y Redirect URI."
    except Exception:
        pass
    return HTTPException(
        status_code=502 if resp.status_code >= 500 else 400,
        detail={
            "code": "POWERBI_MICROSOFT_AUTH_ERROR",
            "message": message,
            "status": resp.status_code,
        },
    )


def build_authorization_url(state: str, app_config: PowerBIAppConfig) -> str:
    missing = validate_app_config(app_config)
    if missing:
        raise powerbi_config_required_error(missing)
    params = {
        "client_id": app_config.client_id,
        "response_type": "code",
        "redirect_uri": app_config.redirect_uri,
        "response_mode": "query",
        "scope": " ".join(app_config.scopes or DEFAULT_DELEGATED_SCOPES),
        "state": state,
        "prompt": "select_account",
    }
    return f"{_authorization_endpoint(app_config.tenant_id)}?{urlencode(params)}"


async def exchange_code_for_token(code: str, app_config: PowerBIAppConfig) -> dict[str, Any]:
    missing = validate_app_config(app_config)
    if missing:
        raise powerbi_config_required_error(missing)
    data = {
        "client_id": app_config.client_id,
        "client_secret": app_config.client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": app_config.redirect_uri,
        "scope": " ".join(app_config.scopes or DEFAULT_DELEGATED_SCOPES),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _token_endpoint(app_config.tenant_id),
            data=data,
            timeout=20.0,
        )
    if resp.status_code != 200:
        raise _friendly_microsoft_error(
            resp,
            "Microsoft no pudo completar la conexion. Revisa la configuracion de la aplicacion.",
        )
    token = resp.json()
    token["expires_at"] = int(time.time()) + int(token.get("expires_in", 0))
    return token


async def refresh_delegated_token(token_payload: dict[str, Any], app_config: PowerBIAppConfig) -> dict[str, Any]:
    missing = validate_app_config(app_config)
    if missing:
        raise powerbi_config_required_error(missing)
    refresh_token = token_payload.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="La conexion de Power BI no tiene refresh token")
    data = {
        "client_id": app_config.client_id,
        "client_secret": app_config.client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(app_config.scopes or DEFAULT_DELEGATED_SCOPES),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _token_endpoint(app_config.tenant_id),
            data=data,
            timeout=20.0,
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "POWERBI_REFRESH_FAILED",
                "message": "No pude renovar la sesion de Power BI. Vuelve a conectar la cuenta Microsoft.",
            },
        )
    updated = resp.json()
    updated["expires_at"] = int(time.time()) + int(updated.get("expires_in", 0))
    if "refresh_token" not in updated:
        updated["refresh_token"] = refresh_token
    return updated


async def service_principal_token(app_config: PowerBIAppConfig) -> dict[str, Any]:
    missing = validate_app_config(app_config)
    if missing:
        raise powerbi_config_required_error(missing)
    data = {
        "client_id": app_config.client_id,
        "client_secret": app_config.client_secret,
        "grant_type": "client_credentials",
        "scope": POWERBI_RESOURCE_SCOPE,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _token_endpoint(app_config.tenant_id),
            data=data,
            timeout=20.0,
        )
    if resp.status_code != 200:
        raise _friendly_microsoft_error(
            resp,
            "Microsoft no pudo autenticar el service principal de Power BI.",
        )
    token = resp.json()
    token["expires_at"] = int(time.time()) + int(token.get("expires_in", 0))
    return token


class PowerBIClient:
    def __init__(self, access_token: str):
        self.access_token = access_token

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method,
                f"{POWERBI_API_BASE}{path}",
                params=params,
                json=json_body,
                headers=self.headers,
                timeout=timeout,
            )
        if resp.status_code not in (200, 201, 202):
            raise HTTPException(
                status_code=resp.status_code,
                detail={
                    "code": "POWERBI_API_ERROR",
                    "message": "Power BI rechazo la solicitud. Revisa permisos, workspace y modelo seleccionado.",
                    "status": resp.status_code,
                },
            )
        return resp.json() if resp.text else {}

    async def list_workspaces(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/groups")
        return data.get("value", [])

    async def list_datasets(self, workspace_id: str) -> list[dict[str, Any]]:
        path = f"/groups/{workspace_id}/datasets" if workspace_id else "/datasets"
        data = await self._request("GET", path)
        return data.get("value", [])

    async def execute_dax(
        self,
        dataset_id: str,
        dax: str,
        *,
        workspace_id: Optional[str] = None,
        impersonated_user_name: Optional[str] = None,
    ) -> dict[str, Any]:
        path = f"/groups/{workspace_id}/datasets/{dataset_id}/executeQueries" if workspace_id else f"/datasets/{dataset_id}/executeQueries"
        body: dict[str, Any] = {
            "queries": [{"query": dax}],
            "serializerSettings": {"includeNulls": True},
        }
        if impersonated_user_name:
            body["impersonatedUserName"] = impersonated_user_name
        return await self._request("POST", path, json_body=body, timeout=60.0)

    async def start_workspace_scan(self, workspace_ids: list[str]) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/admin/workspaces/getInfo",
            params={
                "lineage": "true",
                "datasourceDetails": "true",
                "datasetSchema": "true",
                "datasetExpressions": "true",
            },
            json_body={"workspaces": workspace_ids},
            timeout=30.0,
        )

    async def get_scan_status(self, scan_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/admin/workspaces/scanStatus/{scan_id}", timeout=15.0)

    async def get_scan_result(self, scan_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/admin/workspaces/scanResult/{scan_id}", timeout=30.0)
