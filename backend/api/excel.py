from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, Header, HTTPException, Request

from services.excel_connector import create_excel_connection_from_upload
from services.semantic_catalog import list_connections
from services.supabase_rest import user_id_from_authorization


router = APIRouter(prefix="/connectors/excel", tags=["excel"])


def _friendly_excel_error(detail: object) -> str:
    if isinstance(detail, dict) and detail.get("code") == "company_context_required":
        return str(detail.get("message") or "Completa el contexto de empresa antes de procesar Excel.")
    text = detail if isinstance(detail, str) else str(detail)
    lowered = text.lower()
    if "supabase_service_role_key" in lowered:
        return "Falta configurar las credenciales server-side de Supabase para guardar la conexion."
    if "supabase_url" in lowered:
        return "Falta configurar la URL de Supabase en el backend."
    if any(token in lowered for token in ("connector_instances", "semantic_models", "semantic_fields", "42p01", "pgrst205")):
        return "Faltan aplicar las migraciones de conectores semanticos en Supabase."
    if "foreign key" in lowered and "connector" in lowered:
        return "El conector Excel no esta registrado en la tabla de conectores. Aplica la migracion de conectores."
    if "no encontre hojas" in lowered:
        return "No encontre hojas con datos tabulares. Revisa que cada hoja tenga encabezados y filas de datos."
    if "duckdb" in lowered or "extension excel" in lowered or "xlsx" in lowered or "workbook" in lowered or "25 mb" in lowered:
        return text
    return "No pude procesar el workbook Excel. Revisa que sea un .xlsx con hojas tabulares y que las migraciones esten aplicadas."


def _raise_excel_error(exc: HTTPException) -> None:
    if isinstance(exc.detail, dict) and exc.detail.get("code") == "company_context_required":
        raise exc
    raise HTTPException(status_code=exc.status_code, detail={"message": _friendly_excel_error(exc.detail)}) from exc


@router.get("/connections")
async def get_excel_connections(authorization: str = Header(...)):
    user_id = user_id_from_authorization(authorization)
    try:
        excel_connections = [
            conn
            for conn in await list_connections(user_id)
            if conn.get("connector_key") == "excel" and conn.get("status") in {"review", "ready", "connected"}
        ]
        active_connection = next(
            (conn for conn in excel_connections if conn.get("is_default")),
            excel_connections[0] if excel_connections else None,
        )
        connections = [active_connection] if active_connection else []
    except HTTPException as exc:
        _raise_excel_error(exc)
    return {"connections": connections}


@router.post("/upload")
async def upload_excel_workbook(
    request: Request,
    authorization: str = Header(...),
    x_file_name: Optional[str] = Header(default=None),
):
    user_id = user_id_from_authorization(authorization)
    content = await request.body()
    if not content:
        raise HTTPException(status_code=422, detail="Subi un workbook .xlsx para conectar Excel")
    file_name = unquote(x_file_name or "workbook.xlsx")
    try:
        result = await create_excel_connection_from_upload(user_id, file_name, content)
    except HTTPException as exc:
        _raise_excel_error(exc)
    return result
