import asyncio
import copy
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from services import supabase_rest as sb
from services.powerbi_client import PowerBIClient, refresh_delegated_token, service_principal_token
from services.powerbi_config import get_powerbi_app_config
from services.token_crypto import seal_json, unseal_json


SENSITIVE_NAME_RE = re.compile(r"(email|mail|telefono|phone|dni|documento|address|direccion|ssn)", re.I)
CATALOG_READY_STATUSES = {"ready", "connected"}
CATALOG_REVIEW_STATUSES = {"review"}
SEMANTIC_CATALOG_CACHE_TTL_SECONDS = int(os.getenv("SEMANTIC_CATALOG_CACHE_TTL_SECONDS", "30"))
_SEMANTIC_CATALOG_CACHE: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}


def clear_semantic_catalog_cache(user_id: Optional[str] = None, connection_id: Optional[str] = None) -> None:
    for key in list(_SEMANTIC_CATALOG_CACHE.keys()):
        key_user_id, key_connection_id, _scope = key
        if user_id and key_user_id != user_id:
            continue
        if connection_id and key_connection_id not in {connection_id, ""}:
            continue
        _SEMANTIC_CATALOG_CACHE.pop(key, None)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_alias(value: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")


def powerbi_column_key(table_name: str, column_name: str) -> str:
    return f"{table_name}.{column_name}"


def powerbi_measure_key(table_name: str, measure_name: str) -> str:
    return f"{table_name}.{measure_name}"


def dax_column_ref(table_name: str, column_name: str) -> str:
    safe_table = table_name.replace("'", "''")
    safe_col = column_name.replace("]", "]]")
    return f"'{safe_table}'[{safe_col}]"


def dax_measure_ref(measure_name: str) -> str:
    safe_measure = measure_name.replace("]", "]]")
    return f"[{safe_measure}]"


def infer_field_kind(name: str, data_type: Optional[str]) -> str:
    data = (data_type or "").lower()
    normalized = normalize_alias(name)
    if "date" in data or "time" in data or normalized in {"fecha", "date", "periodo"}:
        return "time"
    if normalized.endswith("_id") or normalized.endswith("id") or normalized.startswith("id_"):
        return "id"
    return "dimension"


def is_sensitive_field(name: str) -> bool:
    return bool(SENSITIVE_NAME_RE.search(name or ""))


def _is_numeric_data_type(data_type: Optional[str]) -> bool:
    return (data_type or "").lower() in {"integer", "number", "numeric", "decimal", "float", "double"}


def _looks_like_excel_fact_table(table: Optional[dict[str, Any]]) -> bool:
    if not table:
        return False
    metadata = table.get("metadata") or {}
    values = [
        table.get("name", ""),
        table.get("display_name", ""),
        metadata.get("sheet_name", ""),
        metadata.get("table_name", ""),
    ]
    normalized = normalize_alias(" ".join(str(value or "") for value in values))
    return normalized == "fact" or normalized.startswith("fact_") or "_fact_" in normalized


def _looks_like_excel_dim_table(table: Optional[dict[str, Any]]) -> bool:
    if not table:
        return False
    metadata = table.get("metadata") or {}
    values = [
        table.get("name", ""),
        table.get("display_name", ""),
        metadata.get("sheet_name", ""),
        metadata.get("table_name", ""),
    ]
    normalized = normalize_alias(" ".join(str(value or "") for value in values))
    return normalized == "dim" or normalized.startswith("dim_") or "_dim_" in normalized


def _excel_table_tokens(table: dict[str, Any]) -> set[str]:
    metadata = table.get("metadata") or {}
    text = normalize_alias(" ".join(str(value or "") for value in [
        table.get("name", ""),
        table.get("display_name", ""),
        metadata.get("sheet_name", ""),
        metadata.get("table_name", ""),
    ]))
    return {
        token
        for token in text.split("_")
        if token and token not in {"excel", "dim", "fact", "mensual", "monthly", "detalle", "maestro"}
    }


def _excel_dimension_key_fields(table: dict[str, Any], fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table_fields = [field for field in fields if field.get("table_id") == table.get("id")]
    id_fields = [field for field in table_fields if (field.get("field_kind") or "") == "id"]
    table_tokens = _excel_table_tokens(table)
    matching_ids = [
        field
        for field in id_fields
        if any(token in normalize_alias(field.get("name") or field.get("semantic_key") or "") for token in table_tokens)
    ]
    if matching_ids:
        return [matching_ids[0]]
    if len(id_fields) == 1:
        return [id_fields[0]]

    time_fields = [field for field in table_fields if (field.get("field_kind") or "") == "time"]
    if len(time_fields) == 1 and table_tokens.intersection({"fecha", "date", "periodo"}):
        return [time_fields[0]]

    return []


def _with_inferred_excel_relationships(
    relationships: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    excel_tables = [
        table
        for table in tables
        if (table.get("metadata") or {}).get("source") == "excel"
    ]
    if not excel_tables:
        return relationships

    table_by_id = {table.get("id"): table for table in excel_tables if table.get("id")}
    fields_by_table: dict[str, list[dict[str, Any]]] = {}
    for field in fields:
        table_id = field.get("table_id")
        if table_id in table_by_id:
            fields_by_table.setdefault(table_id, []).append(field)

    inferred = list(relationships or [])
    seen = {
        (
            relationship.get("from_table"),
            relationship.get("from_field"),
            relationship.get("to_table"),
            relationship.get("to_field"),
        )
        for relationship in inferred
    }
    dimensions = [table for table in excel_tables if _looks_like_excel_dim_table(table)]

    for source_table in excel_tables:
        source_fields = {
            field.get("name"): field
            for field in fields_by_table.get(source_table.get("id"), [])
            if field.get("name")
        }
        for target_table in dimensions:
            if source_table.get("id") == target_table.get("id"):
                continue
            for target_key in _excel_dimension_key_fields(target_table, fields):
                key_name = target_key.get("name")
                if not key_name or key_name not in source_fields:
                    continue
                relationship_key = (
                    source_table.get("name"),
                    key_name,
                    target_table.get("name"),
                    key_name,
                )
                if relationship_key in seen:
                    continue
                seen.add(relationship_key)
                inferred.append({
                    "id": f"inferred:{':'.join(str(part) for part in relationship_key)}",
                    "owner_user_id": source_table.get("owner_user_id"),
                    "model_id": source_table.get("model_id"),
                    "from_table": source_table.get("name"),
                    "from_field": key_name,
                    "to_table": target_table.get("name"),
                    "to_field": key_name,
                    "cardinality": "many_to_one",
                    "cross_filter_behavior": "single",
                    "is_active": True,
                    "metadata": {
                        "source": "excel",
                        "provider": "cube",
                        "generated": True,
                        "inferred_from": "shared_dimension_key",
                    },
                })
                break

    return inferred


def _normalized_excel_field_kind(field: dict[str, Any], table: Optional[dict[str, Any]]) -> str:
    current_kind = field.get("field_kind") or "dimension"
    if current_kind == "measure":
        return "measure"

    inferred = infer_field_kind(
        field.get("name") or field.get("display_name") or "",
        field.get("data_type"),
    )
    if inferred in {"time", "id"}:
        return inferred
    if _is_numeric_data_type(field.get("data_type")) and _looks_like_excel_fact_table(table):
        return "measure"
    return inferred or current_kind


def _approval_status(item: dict[str, Any]) -> str:
    return str(item.get("approval_status") or "approved")


def _catalog_display_name(item: dict[str, Any]) -> str:
    return (
        item.get("business_name")
        or item.get("suggested_business_name")
        or item.get("display_name")
        or item.get("name")
        or ""
    )


def _catalog_description(item: dict[str, Any]) -> str:
    return item.get("description") or item.get("suggested_description") or ""


def _is_catalog_visible(item: dict[str, Any], *, include_review: bool) -> bool:
    if item.get("is_hidden"):
        return False
    status = _approval_status(item)
    if include_review:
        return status != "rejected"
    return status == "approved"


def _field_visible_for_catalog(field: dict[str, Any], *, include_review: bool) -> bool:
    if _looks_like_excel_technical_field(field):
        return False
    if field.get("is_ai_enabled", True) is False:
        return False
    return _is_catalog_visible(field, include_review=include_review)


def _excel_internal_aggregate_metrics(
    fields: list[dict[str, Any]],
    table_by_id: dict[str, dict[str, Any]],
    visible_table_ids: set[str],
) -> list[dict[str, Any]]:
    """Expose safe formula operands without exposing technical dimensions to the planner."""
    helpers: list[dict[str, Any]] = []
    for field in fields:
        metadata = field.get("metadata") or {}
        table_id = field.get("table_id")
        semantic_key = field.get("semantic_key")
        if (
            metadata.get("source") != "excel"
            or metadata.get("provider", "cube") != "cube"
            or table_id not in visible_table_ids
            or not semantic_key
            or field.get("is_sensitive")
        ):
            continue

        kind = field.get("field_kind")
        if kind not in {"time", "id"}:
            continue
        table = table_by_id.get(table_id) or {}
        table_display = _catalog_display_name(table) or table.get("name") or "el area de negocio"
        field_display = _catalog_display_name(field) or field.get("name") or semantic_key
        time_precision = "dia" if str(field.get("data_type") or "").lower() == "date" else "segundo"
        definitions = (
            (
                ("min", "Primera", f"Fecha inicial de {table_display}, con precision de {time_precision}."),
                ("max", "Ultima", f"Fecha final de {table_display}, con precision de {time_precision}."),
            )
            if kind == "time"
            else ((
                "count_distinct",
                "Cantidad unica de",
                f"Cuenta valores unicos de {field_display} en {table_display}.",
            ),)
        )
        for suffix, title_prefix, description in definitions:
            helper_key = f"{semantic_key}_{suffix}"
            helpers.append({
                "field_id": field.get("id"),
                "key": helper_key,
                "name": f"{title_prefix} {field_display}",
                "description": description,
                "format": "datetime" if kind == "time" else "number",
                "source": "aggregate_helper",
                "provider": "cube",
                "model_id": field.get("model_id"),
                "expression": f"{suffix}({semantic_key})",
                "business_area": table_display,
                "business_formula": description,
                "provider_dependencies": [helper_key],
            })
    return helpers


def _looks_like_excel_technical_field(field: dict[str, Any]) -> bool:
    metadata = field.get("metadata") or {}
    if (metadata.get("source") or field.get("source")) != "excel":
        return False
    if field.get("field_kind") == "id":
        return True

    normalized = normalize_alias(" ".join(str(value or "") for value in [
        field.get("name"),
        field.get("display_name"),
        field.get("business_name"),
        field.get("suggested_business_name"),
        field.get("semantic_key"),
        metadata.get("physical_column"),
        metadata.get("physical_display_name"),
    ]))
    tokens = set(normalized.split("_"))
    if tokens.intersection({"id", "codigo", "cod", "clave", "llave", "key", "pk", "fk", "hash"}):
        return True
    if any(
        normalized.startswith(prefix) and len(normalized) > len(prefix) + 1
        for prefix in ("id", "codigo", "cod", "clave", "key")
    ):
        return True
    return any(
        normalized.startswith(prefix) or normalized.endswith(suffix)
        for prefix, suffix in (
            ("id_", "_id"),
            ("codigo_", "_codigo"),
            ("cod_", "_cod"),
            ("clave_", "_clave"),
            ("key_", "_key"),
        )
    )


async def list_connections(user_id: str) -> list[dict[str, Any]]:
    return await sb.rest_get(
        "connector_instances",
        {
            "select": "id,connector_key,provider,name,auth_mode,status,is_default,config,health,last_sync_at,last_error,created_at,updated_at",
            "owner_user_id": f"eq.{user_id}",
            "order": "updated_at.desc",
        },
    )


async def get_connection(connection_id: str, user_id: Optional[str] = None) -> dict[str, Any]:
    params = {
        "select": "*",
        "id": f"eq.{connection_id}",
        "limit": "1",
    }
    if user_id:
        params["owner_user_id"] = f"eq.{user_id}"
    rows = await sb.rest_get("connector_instances", params)
    if not rows:
        raise HTTPException(status_code=404, detail="Conexion no encontrada")
    return rows[0]


def _catalog_connections_for_scope(
    connections: list[dict[str, Any]],
    connection_id: Optional[str] = None,
    *,
    include_review: bool = False,
) -> list[dict[str, Any]]:
    allowed_statuses = CATALOG_READY_STATUSES | (CATALOG_REVIEW_STATUSES if include_review else set())
    ready_connections = [
        connection
        for connection in connections
        if connection.get("status") in allowed_statuses
    ]
    if connection_id:
        return [connection for connection in ready_connections if connection.get("id") == connection_id]

    excel_connections = [
        connection for connection in ready_connections
        if connection.get("connector_key") == "excel"
    ]
    active_excel = next(
        (connection for connection in excel_connections if connection.get("is_default")),
        excel_connections[0] if excel_connections else None,
    )

    scoped_connections = []
    for connection in ready_connections:
        if (
            connection.get("connector_key") == "excel"
            and active_excel
            and connection.get("id") != active_excel.get("id")
        ):
            continue
        scoped_connections.append(connection)
    return scoped_connections


async def create_powerbi_oauth_connection(user_id: str, token_payload: dict[str, Any]) -> dict[str, Any]:
    row = {
        "owner_user_id": user_id,
        "connector_key": "powerbi",
        "provider": "powerbi",
        "name": "Power BI",
        "auth_mode": "delegated_user",
        "status": "oauth_connected",
        "config": {
            "scopes": token_payload.get("scope", ""),
            "token_type": token_payload.get("token_type", "Bearer"),
        },
        "health": {"oauth": "connected"},
    }
    created = await sb.rest_post("connector_instances", row)
    connection = created[0]
    await save_connection_secret(connection["id"], user_id, token_payload)
    return connection


async def save_connection_secret(connection_id: str, user_id: str, token_payload: dict[str, Any]) -> None:
    sealed = seal_json(token_payload)
    await sb.rest_post(
        "connector_secrets",
        {
            "connection_id": connection_id,
            "owner_user_id": user_id,
            "secret_payload": sealed,
            "secret_version": 1,
        },
        params={"on_conflict": "connection_id"},
        prefer="resolution=merge-duplicates",
    )


async def get_connection_secret(connection_id: str, user_id: Optional[str] = None) -> dict[str, Any]:
    params = {
        "select": "*",
        "connection_id": f"eq.{connection_id}",
        "limit": "1",
    }
    if user_id:
        params["owner_user_id"] = f"eq.{user_id}"
    rows = await sb.rest_get("connector_secrets", params)
    if not rows:
        raise HTTPException(status_code=404, detail="Secreto de conexion no encontrado")
    return unseal_json(rows[0].get("secret_payload") or {})


async def powerbi_client_for_connection(connection: dict[str, Any]) -> PowerBIClient:
    auth_mode = connection.get("auth_mode")
    user_id = connection["owner_user_id"]
    app_config = await get_powerbi_app_config(user_id)

    if auth_mode == "service_principal":
        token_payload = await service_principal_token(app_config)
        return PowerBIClient(token_payload["access_token"])

    token_payload = await get_connection_secret(connection["id"], user_id)
    if int(token_payload.get("expires_at", 0)) <= int(time.time()) + 90:
        token_payload = await refresh_delegated_token(token_payload, app_config)
        await save_connection_secret(connection["id"], user_id, token_payload)
    return PowerBIClient(token_payload["access_token"])


def normalize_powerbi_scan_result(
    scan_result: dict[str, Any],
    *,
    workspace_id: str,
    dataset_id: str,
    dataset_name: str = "",
) -> dict[str, Any]:
    target_workspace = None
    target_dataset = None

    for workspace in scan_result.get("workspaces", []) or []:
        if str(workspace.get("id")) == str(workspace_id):
            target_workspace = workspace
        for dataset in workspace.get("datasets", []) or []:
            if str(dataset.get("id")) == str(dataset_id):
                target_workspace = workspace
                target_dataset = dataset
                break
        if target_dataset:
            break

    if not target_dataset:
        raise HTTPException(status_code=422, detail="El scan no devolvio el semantic model seleccionado")

    model_name = target_dataset.get("name") or dataset_name or "Power BI Semantic Model"
    tables = []
    fields = []
    relationships = []

    for table in target_dataset.get("tables", []) or []:
        table_name = table.get("name") or table.get("displayName")
        if not table_name:
            continue
        table_hidden = bool(table.get("isHidden", False))
        table_row = {
            "external_table_id": table.get("id") or table_name,
            "name": table_name,
            "display_name": table.get("displayName") or table_name,
            "description": table.get("description") or "",
            "is_hidden": table_hidden,
            "metadata": {
                "source": "powerbi",
                "storageMode": table.get("storageMode"),
            },
        }
        tables.append(table_row)

        for column in table.get("columns", []) or []:
            column_name = column.get("name")
            if not column_name:
                continue
            hidden = bool(column.get("isHidden", table_hidden))
            sensitive = is_sensitive_field(column_name)
            data_type = column.get("dataType") or column.get("type")
            fields.append({
                "table_name": table_name,
                "external_field_id": column.get("id") or column_name,
                "semantic_key": powerbi_column_key(table_name, column_name),
                "name": column_name,
                "display_name": column.get("displayName") or column_name,
                "description": column.get("description") or "",
                "field_kind": infer_field_kind(column_name, data_type),
                "data_type": data_type,
                "expression": column.get("expression"),
                "expression_language": "m" if column.get("expression") else None,
                "format_string": column.get("formatString"),
                "is_hidden": hidden,
                "is_sensitive": sensitive,
                "is_ai_enabled": not hidden and not sensitive,
                "metadata": {
                    "source": "powerbi",
                    "dax_reference": dax_column_ref(table_name, column_name),
                    "sourceColumn": column.get("sourceColumn"),
                },
            })

        for measure in table.get("measures", []) or []:
            measure_name = measure.get("name")
            if not measure_name:
                continue
            hidden = bool(measure.get("isHidden", table_hidden))
            sensitive = is_sensitive_field(measure_name)
            fields.append({
                "table_name": table_name,
                "external_field_id": measure.get("id") or measure_name,
                "semantic_key": powerbi_measure_key(table_name, measure_name),
                "name": measure_name,
                "display_name": measure.get("displayName") or measure_name,
                "description": measure.get("description") or "",
                "field_kind": "measure",
                "data_type": "number",
                "expression": measure.get("expression"),
                "expression_language": "dax",
                "format_string": measure.get("formatString"),
                "is_hidden": hidden,
                "is_sensitive": sensitive,
                "is_ai_enabled": not hidden and not sensitive,
                "metadata": {
                    "source": "powerbi",
                    "dax_reference": dax_measure_ref(measure_name),
                },
            })

    for rel in target_dataset.get("relationships", []) or []:
        relationships.append({
            "from_table": rel.get("fromTable") or rel.get("fromTableName") or "",
            "from_field": rel.get("fromColumn") or rel.get("fromColumnName") or "",
            "to_table": rel.get("toTable") or rel.get("toTableName") or "",
            "to_field": rel.get("toColumn") or rel.get("toColumnName") or "",
            "cardinality": rel.get("cardinality") or rel.get("relationshipType"),
            "cross_filter_behavior": rel.get("crossFilteringBehavior") or rel.get("crossFilterDirection"),
            "is_active": rel.get("isActive", True),
            "metadata": {"source": "powerbi", "raw": rel},
        })

    return {
        "model": {
            "external_model_id": dataset_id,
            "workspace_id": workspace_id,
            "dataset_id": dataset_id,
            "name": model_name,
            "description": target_dataset.get("description") or "",
            "metadata": {
                "workspace_name": (target_workspace or {}).get("name"),
                "configured_by": target_dataset.get("configuredBy"),
                "sensitivityLabel": target_dataset.get("sensitivityLabel"),
                "source": "powerbi_scanner",
            },
        },
        "tables": tables,
        "fields": fields,
        "relationships": relationships,
    }


async def persist_catalog(
    *,
    owner_user_id: str,
    connection_id: str,
    provider: str,
    normalized: dict[str, Any],
    preserve_existing_approvals: bool = True,
) -> dict[str, Any]:
    model_payload = {
        "owner_user_id": owner_user_id,
        "connection_id": connection_id,
        "provider": provider,
        **normalized["model"],
        "is_default": True,
    }
    model_rows = await sb.rest_post(
        "semantic_models",
        model_payload,
        params={"on_conflict": "connection_id,external_model_id"},
        prefer="resolution=merge-duplicates,return=representation",
    )
    model = model_rows[0]
    model_id = model["id"]
    existing_fields_by_key: dict[str, dict[str, Any]] = {}
    existing_tables_by_name: dict[str, dict[str, Any]] = {}
    try:
        existing_tables = await sb.rest_get(
            "semantic_tables",
            {
                "select": "name,external_table_id,description,business_name,suggested_business_name,suggested_description,approval_status,approved_at,approved_by",
                "model_id": f"eq.{model_id}",
            },
        )
        for row in existing_tables:
            for key in (row.get("name"), row.get("external_table_id")):
                if key and key not in existing_tables_by_name:
                    existing_tables_by_name[key] = row

        existing_fields = await sb.rest_get(
            "semantic_fields",
            {
                "select": "semantic_key,description,business_name,suggested_business_name,suggested_description,approval_status,approved_at,approved_by",
                "model_id": f"eq.{model_id}",
            },
        )
        existing_fields_by_key = {
            row["semantic_key"]: row
            for row in existing_fields
            if row.get("semantic_key")
        }
    except Exception:
        existing_fields_by_key = {}
        existing_tables_by_name = {}

    await sb.rest_delete("semantic_relationships", params={"model_id": f"eq.{model_id}"})
    await sb.rest_delete("semantic_fields", params={"model_id": f"eq.{model_id}"})
    await sb.rest_delete("semantic_tables", params={"model_id": f"eq.{model_id}"})

    table_map: dict[str, str] = {}
    table_payload = []
    for table in normalized.get("tables", []):
        table = dict(table)
        existing_table = existing_tables_by_name.get(table.get("name") or "") or existing_tables_by_name.get(table.get("external_table_id") or "")
        if existing_table:
            if preserve_existing_approvals:
                for key in (
                    "description",
                    "business_name",
                    "suggested_business_name",
                    "suggested_description",
                    "approval_status",
                    "approved_at",
                    "approved_by",
                ):
                    if existing_table.get(key):
                        table[key] = existing_table[key]
            else:
                table["approval_status"] = table.get("approval_status") or "review"
                if not table.get("suggested_business_name") and existing_table.get("business_name"):
                    table["suggested_business_name"] = existing_table["business_name"]
                if not table.get("suggested_description") and existing_table.get("description"):
                    table["suggested_description"] = existing_table["description"]
        table.setdefault("business_name", table.get("display_name") or table.get("name") or "")
        table.setdefault("approval_status", "approved")
        table_payload.append({
            "owner_user_id": owner_user_id,
            "model_id": model_id,
            **table,
        })
    if table_payload:
        created_tables = await sb.rest_post("semantic_tables", table_payload)
        table_map = {row["name"]: row["id"] for row in created_tables}

    field_payload = []
    for raw_field in normalized.get("fields", []):
        field = dict(raw_field)
        table_name = field.pop("table_name", None)
        semantic_key = field.get("semantic_key")
        existing_field = existing_fields_by_key.get(semantic_key or "")
        if existing_field:
            if preserve_existing_approvals:
                for key in (
                    "description",
                    "business_name",
                    "suggested_business_name",
                    "suggested_description",
                    "approval_status",
                    "approved_at",
                    "approved_by",
                ):
                    if existing_field.get(key):
                        field[key] = existing_field[key]
            else:
                if not field.get("suggested_business_name") and existing_field.get("business_name"):
                    field["suggested_business_name"] = existing_field["business_name"]
                if not field.get("suggested_description") and existing_field.get("description"):
                    field["suggested_description"] = existing_field["description"]
        field.setdefault("business_name", field.get("display_name") or field.get("name") or "")
        field.setdefault("approval_status", "approved")
        field_payload.append({
            "owner_user_id": owner_user_id,
            "model_id": model_id,
            "table_id": table_map.get(table_name or ""),
            **field,
        })
    if field_payload:
        await sb.rest_post("semantic_fields", field_payload)

    rel_payload = []
    for rel in normalized.get("relationships", []):
        if not rel.get("from_table") or not rel.get("to_table"):
            continue
        rel_payload.append({
            "owner_user_id": owner_user_id,
            "model_id": model_id,
            **rel,
        })
    if rel_payload:
        await sb.rest_post("semantic_relationships", rel_payload)

    clear_semantic_catalog_cache(owner_user_id, connection_id)
    return {
        "model": model,
        "tables": len(table_payload),
        "fields": len(field_payload),
        "relationships": len(rel_payload),
    }


async def create_sync_run(owner_user_id: str, connection_id: str) -> dict[str, Any]:
    rows = await sb.rest_post(
        "semantic_sync_runs",
        {
            "owner_user_id": owner_user_id,
            "connection_id": connection_id,
            "status": "running",
        },
    )
    return rows[0]


async def finish_sync_run(sync_id: str, status: str, *, error: str = "", counters: Optional[dict[str, Any]] = None, scan_id: Optional[str] = None) -> None:
    payload = {
        "status": status,
        "completed_at": utc_now_iso(),
        "error_message": error or None,
        "counters": counters or {},
    }
    if scan_id:
        payload["scan_id"] = scan_id
    await sb.rest_patch("semantic_sync_runs", payload, params={"id": f"eq.{sync_id}"}, prefer="")


async def sync_powerbi_connection(connection_id: str, user_id: Optional[str] = None) -> dict[str, Any]:
    connection = await get_connection(connection_id, user_id)
    owner_user_id = connection["owner_user_id"]
    config = connection.get("config") or {}
    workspace_id = config.get("workspace_id")
    dataset_id = config.get("dataset_id")
    dataset_name = config.get("dataset_name", "")
    if not workspace_id or not dataset_id:
        raise HTTPException(status_code=422, detail="La conexion Power BI no tiene workspace/dataset seleccionado")

    sync = await create_sync_run(owner_user_id, connection_id)
    scan_id = None
    try:
        await sb.rest_patch(
            "connector_instances",
            {"status": "syncing", "last_error": None},
            params={"id": f"eq.{connection_id}"},
            prefer="",
        )
        client = await powerbi_client_for_connection(connection)
        scan = await client.start_workspace_scan([workspace_id])
        scan_id = scan.get("id")
        if not scan_id:
            raise HTTPException(status_code=502, detail="Power BI no devolvio scan id")

        timeout_seconds = int(float(os.getenv("POWERBI_SCAN_TIMEOUT_SECONDS", "45")))
        started = time.time()
        status = scan.get("status", "NotStarted")
        while status not in {"Succeeded", "Failed"} and time.time() - started < timeout_seconds:
            await asyncio.sleep(2)
            status_payload = await client.get_scan_status(scan_id)
            status = status_payload.get("status", status)
        if status != "Succeeded":
            raise HTTPException(status_code=504, detail=f"Power BI metadata scan no finalizo: {status}")

        scan_result = await client.get_scan_result(scan_id)
        normalized = normalize_powerbi_scan_result(
            scan_result,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            dataset_name=dataset_name,
        )
        counters = await persist_catalog(
            owner_user_id=owner_user_id,
            connection_id=connection_id,
            provider="powerbi",
            normalized=normalized,
        )
        await sb.rest_patch(
            "connector_instances",
            {
                "status": "ready",
                "last_sync_at": utc_now_iso(),
                "last_error": None,
                "health": {"metadata": "ready", "scan_id": scan_id},
            },
            params={"id": f"eq.{connection_id}"},
            prefer="",
        )
        clear_semantic_catalog_cache(owner_user_id, connection_id)
        await finish_sync_run(sync["id"], "success", counters=counters, scan_id=scan_id)
        return {"status": "success", "scan_id": scan_id, **counters}
    except Exception as exc:
        error = getattr(exc, "detail", None) or str(exc)
        await sb.rest_patch(
            "connector_instances",
            {
                "status": "error",
                "last_error": str(error),
                "health": {"metadata": "error", "scan_id": scan_id},
            },
            params={"id": f"eq.{connection_id}"},
            prefer="",
        )
        clear_semantic_catalog_cache(owner_user_id, connection_id)
        await finish_sync_run(sync["id"], "failed", error=str(error), scan_id=scan_id)
        raise


async def fetch_semantic_catalog(
    user_id: Optional[str],
    connection_id: Optional[str] = None,
    *,
    include_review: bool = False,
) -> dict[str, Any]:
    cache_key = (user_id or "", connection_id or "", "review" if include_review else "ready")
    cache_enabled = bool(user_id) and not include_review and SEMANTIC_CATALOG_CACHE_TTL_SECONDS > 0
    if cache_enabled:
        cached = _SEMANTIC_CATALOG_CACHE.get(cache_key)
        if cached and time.monotonic() - cached[0] < SEMANTIC_CATALOG_CACHE_TTL_SECONDS:
            return copy.deepcopy(cached[1])

    connections = await list_connections(user_id) if user_id else []
    catalog_connections = _catalog_connections_for_scope(connections, connection_id, include_review=include_review)
    selected_connection_id = (
        connection_id
        or (catalog_connections[0].get("id") if len(catalog_connections) == 1 else None)
    )
    selected_connection_ids = [connection_id] if connection_id else [
        connection.get("id") for connection in catalog_connections if connection.get("id")
    ]

    models: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    fields: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    sync_runs: list[dict[str, Any]] = []

    if selected_connection_ids and user_id:
        connection_filter = (
            f"eq.{selected_connection_ids[0]}"
            if len(selected_connection_ids) == 1
            else f"in.({','.join(selected_connection_ids)})"
        )
        models = await sb.rest_get(
            "semantic_models",
            {
                "select": "*",
                "owner_user_id": f"eq.{user_id}",
                "connection_id": connection_filter,
                "order": "updated_at.desc",
            },
        )
        model_ids = [m["id"] for m in models]
        sync_filter = (
            f"eq.{selected_connection_ids[0]}"
            if len(selected_connection_ids) == 1
            else f"in.({','.join(selected_connection_ids)})"
        )
        if model_ids:
            id_filter = f"in.({','.join(model_ids)})"
            tables, fields, relationships, aliases, sync_runs = await asyncio.gather(
                sb.rest_get("semantic_tables", {"select": "*", "model_id": id_filter, "order": "name.asc"}),
                sb.rest_get("semantic_fields", {"select": "*", "model_id": id_filter, "order": "field_kind.desc,name.asc"}),
                sb.rest_get("semantic_relationships", {"select": "*", "model_id": id_filter}),
                sb.rest_get("semantic_aliases", {"select": "*", "model_id": id_filter}),
                sb.rest_get(
                    "semantic_sync_runs",
                    {
                        "select": "*",
                        "connection_id": sync_filter,
                        "order": "started_at.desc",
                        "limit": "20",
                    },
                ),
            )
        else:
            sync_runs = await sb.rest_get(
                "semantic_sync_runs",
                {
                    "select": "*",
                    "connection_id": sync_filter,
                    "order": "started_at.desc",
                    "limit": "20",
                },
            )

    table_by_id = {table.get("id"): table for table in tables if table.get("id")}
    normalized_fields = []
    for field in fields:
        metadata = field.get("metadata") or {}
        if metadata.get("source") == "excel":
            field = dict(field)
            metadata = dict(metadata)
            field["field_kind"] = _normalized_excel_field_kind(field, table_by_id.get(field.get("table_id")))
            if field["field_kind"] == "measure":
                metadata.setdefault("aggregation", "sum")
            field["metadata"] = metadata
        normalized_fields.append(field)
    fields = normalized_fields
    relationships = _with_inferred_excel_relationships(relationships, tables, fields)
    visible_tables = [
        table
        for table in tables
        if _is_catalog_visible(table, include_review=include_review)
    ]
    visible_table_ids = {table.get("id") for table in visible_tables if table.get("id")}
    has_tables = bool(tables)
    visible_fields = [
        field
        for field in fields
        if (
            (not has_tables or field.get("table_id") in visible_table_ids)
            and _field_visible_for_catalog(field, include_review=include_review)
        )
    ]

    aliases_by_key = {}
    for alias in aliases:
        if alias.get("entity_type") in {"field", "measure"} and alias.get("alias"):
            aliases_by_key.setdefault(alias.get("semantic_key"), []).append(alias["alias"])
    visible_fields = [{**field, "aliases": list(dict.fromkeys([
        *(field.get("aliases") or []), *((field.get("metadata") or {}).get("aliases") or []),
        *aliases_by_key.get(field.get("semantic_key"), []),
    ]))} for field in visible_fields]
    metrics = []
    for field in visible_fields:
        if field.get("field_kind") != "measure":
            continue
        metadata = field.get("metadata") or {}
        source = metadata.get("source") or "powerbi"
        provider_name = metadata.get("provider") or source
        table = table_by_id.get(field.get("table_id")) or {}
        table_display = _catalog_display_name(table) or table.get("name") or "el area de negocio"
        expression = field.get("expression")
        if source == "excel" and not expression:
            expression = f"{metadata.get('aggregation', 'sum')}({field['semantic_key']})"
        metric_name = _catalog_display_name(field)
        if source == "excel" and field.get("name") == "count" and metadata.get("aggregation") == "count":
            table_text = normalize_alias(" ".join(str(value or "") for value in [
                table.get("name"),
                table.get("display_name"),
                (table.get("metadata") or {}).get("table_name"),
                (table.get("metadata") or {}).get("sheet_name"),
            ]))
            if "producto" in table_text:
                metric_name = "Cantidad de productos"
            elif "cliente" in table_text:
                metric_name = "Cantidad de clientes"
            elif "proveedor" in table_text:
                metric_name = "Cantidad de proveedores"
            else:
                metric_name = f"Cantidad de {_catalog_display_name(table) or 'registros'}"
            if not expression or expression == "count":
                expression = f"count({field['semantic_key']})"
        metrics.append({
            "field_id": field.get("id"),
            "key": field["semantic_key"],
            "aliases": field.get("aliases") or [],
            "name": metric_name,
            "description": _catalog_description(field),
            "format": "number",
            "source": source,
            "provider": provider_name,
            "model_id": field.get("model_id"),
            "expression": expression,
            "business_area": table_display,
            "business_formula": (
                _catalog_description(field)
                or (
                    f"Cuenta registros de {table_display}."
                    if (metadata.get("aggregation") == "count" or str(expression or "").lower().startswith("count("))
                    else f"Suma {metric_name.lower()} para analizar {table_display}."
                )
            ),
            "provider_dependencies": [field["semantic_key"]],
            **{key: metadata[key] for key in ("unit", "grain", "aggregation", "non_additive_dimensions") if key in metadata},
        })

    metric_keys = {metric.get("key") for metric in metrics}
    for table in visible_tables:
        metadata = table.get("metadata") or {}
        if metadata.get("source") != "excel":
            continue
        table_name = table.get("name")
        if not table_name:
            continue
        table_text = normalize_alias(" ".join(str(value or "") for value in [
            table_name,
            table.get("display_name"),
            metadata.get("table_name"),
            metadata.get("sheet_name"),
        ]))
        if "fact" in table_text:
            continue
        count_key = f"{table_name}.count"
        if count_key in metric_keys:
            continue
        if "producto" in table_text:
            metric_name = "Cantidad de productos"
        elif "cliente" in table_text:
            metric_name = "Cantidad de clientes"
        elif "proveedor" in table_text:
            metric_name = "Cantidad de proveedores"
        else:
            metric_name = f"Cantidad de {_catalog_display_name(table) or table_name}"
        metrics.append({
            "field_id": None,
            "key": count_key,
            "name": metric_name,
            "description": f"Conteo de registros en {_catalog_display_name(table) or table_name}.",
            "format": "number",
            "source": "excel",
            "provider": "cube",
            "model_id": table.get("model_id"),
            "expression": f"count({count_key})",
            "business_area": _catalog_display_name(table) or table_name,
            "business_formula": f"Cuenta registros de {_catalog_display_name(table) or table_name}.",
            "provider_dependencies": [count_key],
        })

    metric_keys = {metric.get("key") for metric in metrics}
    metrics.extend(
        helper
        for helper in _excel_internal_aggregate_metrics(fields, table_by_id, visible_table_ids)
        if helper.get("key") not in metric_keys
    )

    result = {
        "connections": catalog_connections,
        "selected_connection_id": selected_connection_id,
        "models": models,
        "tables": visible_tables,
        "fields": visible_fields,
        "relationships": relationships,
        "aliases": aliases,
        "sync_runs": sync_runs,
        "metrics": metrics,
    }
    if cache_enabled:
        _SEMANTIC_CATALOG_CACHE[cache_key] = (time.monotonic(), copy.deepcopy(result))
    return result
