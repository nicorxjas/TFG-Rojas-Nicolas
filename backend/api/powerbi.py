import time
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from services import supabase_rest as sb
from services.powerbi_client import (
    build_authorization_url,
    exchange_code_for_token,
    frontend_base_url,
    powerbi_config_required_error,
    sign_state,
    validate_app_config,
    verify_state,
)
from services.powerbi_config import (
    get_powerbi_app_config,
    get_powerbi_app_config_status,
    save_powerbi_app_config,
)
from services.semantic_catalog import (
    create_powerbi_oauth_connection,
    get_connection,
    list_connections,
    powerbi_client_for_connection,
    sync_powerbi_connection,
)
from services.supabase_rest import user_id_from_authorization


router = APIRouter(prefix="/connectors/powerbi", tags=["powerbi"])


class StartAuthRequest(BaseModel):
    redirect_path: str = "/settings/conectores"


class AppConfigRequest(BaseModel):
    tenant_id: str = "common"
    client_id: str
    client_secret: str = ""
    redirect_uri: str = ""
    scopes: Optional[list[str]] = None


class ConnectDatasetRequest(BaseModel):
    connection_id: str
    workspace_id: str
    workspace_name: str = ""
    dataset_id: str
    dataset_name: str = ""
    sync_now: bool = True


@router.get("/connections")
async def get_powerbi_connections(authorization: str = Header(...)):
    user_id = user_id_from_authorization(authorization)
    connections = [conn for conn in await list_connections(user_id) if conn.get("connector_key") == "powerbi"]
    return {"connections": connections}


@router.get("/app-config")
async def get_powerbi_app_configuration(authorization: str = Header(...)):
    user_id = user_id_from_authorization(authorization)
    return {"app_config": await get_powerbi_app_config_status(user_id)}


@router.post("/app-config")
async def save_powerbi_app_configuration(request: AppConfigRequest, authorization: str = Header(...)):
    user_id = user_id_from_authorization(authorization)
    app_config = await save_powerbi_app_config(
        user_id=user_id,
        tenant_id=request.tenant_id,
        client_id=request.client_id,
        client_secret=request.client_secret,
        redirect_uri=request.redirect_uri,
        scopes=request.scopes,
    )
    return {"app_config": app_config}


@router.post("/start-auth")
async def start_powerbi_auth(request: StartAuthRequest, authorization: str = Header(...)):
    user_id = user_id_from_authorization(authorization)
    app_config = await get_powerbi_app_config(user_id)
    missing = validate_app_config(app_config)
    if missing:
        raise powerbi_config_required_error(missing)
    state = sign_state({
        "user_id": user_id,
        "redirect_path": request.redirect_path,
        "iat": int(time.time()),
        "exp": int(time.time()) + 900,
    })
    return {"auth_url": build_authorization_url(state, app_config)}


@router.get("/callback")
async def powerbi_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    error_description: Optional[str] = Query(default=None),
):
    redirect_path = "/settings/conectores"
    try:
        if not state:
            raise HTTPException(status_code=400, detail="Estado OAuth faltante")
        state_payload = verify_state(state)
        user_id = state_payload["user_id"]
        redirect_path = state_payload.get("redirect_path") or redirect_path
        if error:
            raise HTTPException(status_code=400, detail=error_description or error)
        if not code:
            raise HTTPException(status_code=400, detail="Codigo OAuth faltante")
        app_config = await get_powerbi_app_config(user_id)
        missing = validate_app_config(app_config)
        if missing:
            raise powerbi_config_required_error(missing)
        token_payload = await exchange_code_for_token(code, app_config)
        connection = await create_powerbi_oauth_connection(user_id, token_payload)
        query = urlencode({"powerbi": "connected", "connection_id": connection["id"]})
    except Exception as exc:
        detail = getattr(exc, "detail", None) or str(exc)
        if isinstance(detail, dict):
            detail = detail.get("message") or "No pude completar la conexion con Power BI."
        query = urlencode({"powerbi": "error", "message": str(detail)[:240]})

    return RedirectResponse(f"{frontend_base_url()}{redirect_path}?{query}")


@router.get("/workspaces")
async def list_powerbi_workspaces(
    connection_id: str,
    authorization: str = Header(...),
):
    user_id = user_id_from_authorization(authorization)
    connection = await get_connection(connection_id, user_id)
    client = await powerbi_client_for_connection(connection)

    workspaces = await client.list_workspaces()
    result = []
    for workspace in workspaces:
        workspace_id = workspace.get("id")
        if not workspace_id:
            continue
        try:
            datasets = await client.list_datasets(workspace_id)
        except Exception:
            datasets = []
        result.append({
            "id": workspace_id,
            "name": workspace.get("name") or "Workspace",
            "is_read_only": workspace.get("isReadOnly", False),
            "datasets": [
                {
                    "id": dataset.get("id"),
                    "name": dataset.get("name"),
                    "configured_by": dataset.get("configuredBy"),
                    "is_refreshable": dataset.get("isRefreshable"),
                    "is_effective_identity_required": dataset.get("isEffectiveIdentityRequired"),
                    "is_on_prem_gateway_required": dataset.get("isOnPremGatewayRequired"),
                }
                for dataset in datasets
                if dataset.get("id")
            ],
        })
    return {"workspaces": result}


@router.post("/connect")
async def connect_powerbi_dataset(
    request: ConnectDatasetRequest,
    background_tasks: BackgroundTasks,
    authorization: str = Header(...),
):
    user_id = user_id_from_authorization(authorization)
    connection = await get_connection(request.connection_id, user_id)
    current_config = connection.get("config") or {}
    next_config = {
        **current_config,
        "workspace_id": request.workspace_id,
        "workspace_name": request.workspace_name,
        "dataset_id": request.dataset_id,
        "dataset_name": request.dataset_name,
    }

    await sb.rest_patch(
        "connector_instances",
        {"is_default": False},
        params={"owner_user_id": f"eq.{user_id}", "connector_key": "eq.powerbi", "is_default": "eq.true"},
        prefer="",
    )
    updated = await sb.rest_patch(
        "connector_instances",
        {
            "name": request.dataset_name or request.workspace_name or "Power BI",
            "status": "connected",
            "is_default": True,
            "config": next_config,
            "health": {"metadata": "pending_sync"},
            "last_error": None,
        },
        params={"id": f"eq.{request.connection_id}", "owner_user_id": f"eq.{user_id}"},
    )

    if request.sync_now:
        background_tasks.add_task(sync_powerbi_connection, request.connection_id, user_id)

    return {"connection": updated[0] if updated else None, "sync_queued": request.sync_now}


@router.post("/{connection_id}/sync")
async def sync_powerbi(connection_id: str, authorization: str = Header(...)):
    user_id = user_id_from_authorization(authorization)
    result = await sync_powerbi_connection(connection_id, user_id)
    return result
