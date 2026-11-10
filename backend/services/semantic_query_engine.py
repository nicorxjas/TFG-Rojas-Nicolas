import asyncio
import json
import os
import re
from datetime import date
from typing import Any, Optional

import httpx
from fastapi import HTTPException

from services import supabase_rest as sb
from services.semantic_filters import validate_filters
from services.semantic_catalog import (
    dax_column_ref,
    fetch_semantic_catalog,
    get_connection,
    list_connections,
    normalize_alias,
    powerbi_client_for_connection,
)


MAX_POWERBI_LIMIT = 10000
DEFAULT_LIMIT = 100


def normalize_query_payload(payload: dict[str, Any]) -> dict[str, Any]:
    query = dict(payload.get("query") or payload)
    if "metrics" in query and "measures" not in query:
        query["measures"] = query["metrics"]
    query.setdefault("measures", [])
    query.setdefault("dimensions", [])
    query.setdefault("filters", [])
    query.setdefault("timeDimensions", [])
    query["limit"] = int(query.get("limit") or DEFAULT_LIMIT)
    return query


def _normalized_order(order: Any) -> list[tuple[str, str]]:
    if not isinstance(order, dict):
        return []
    return [
        (str(member), str(direction).lower())
        for member, direction in order.items()
        if isinstance(member, str) and str(direction).lower() in {"asc", "desc"}
    ]


def _sortable_value(value: Any) -> tuple[int, Any]:
    try:
        return 0, float(value)
    except (TypeError, ValueError):
        return 1, str(value).casefold()


def apply_post_compute_order(
    rows: list[dict[str, Any]],
    order: Any,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Order computed metric rows after their dependencies have been evaluated."""
    ordered = list(rows)
    for member, direction in reversed(_normalized_order(order)):
        present = [row for row in ordered if row.get(member) is not None]
        missing = [row for row in ordered if row.get(member) is None]
        present.sort(key=lambda row: _sortable_value(row.get(member)), reverse=direction == "desc")
        ordered = present + missing
    if limit is not None:
        ordered = ordered[:max(0, int(limit))]
    return ordered


async def execute_cube_semantic_query(query: dict[str, Any], *, metric_catalog: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    from api.cube import post_process_cube_response, process_computed_metrics
    from api.semantic_metrics import build_metric_catalog

    if metric_catalog is None:
        metric_catalog = await build_metric_catalog(include_all_users=False)

    requested_limit = max(1, min(int(query.get("limit") or DEFAULT_LIMIT), MAX_POWERBI_LIMIT))
    order_items = _normalized_order(query.get("order"))
    custom_metric_keys = {
        metric.get("key")
        for metric in metric_catalog
        if metric.get("source") == "custom" and metric.get("key")
    }
    requires_post_compute_order = any(member in custom_metric_keys for member, _ in order_items)
    cube_query = dict(query)
    if requires_post_compute_order:
        cube_query.pop("order", None)
        cube_query["limit"] = MAX_POWERBI_LIMIT
        cube_query["measures"] = list(dict.fromkeys([
            *(query.get("measures") or []),
            *(member for member, _ in order_items if member in custom_metric_keys),
        ]))

    rewritten_query, original_measures, computed_info = process_computed_metrics(cube_query, metric_catalog)

    cube_url = os.getenv("CUBE_API_URL") or "http://localhost:4000/cubejs-api/v1/load"
    cube_token = os.getenv("CUBEJS_API_SECRET", "")
    async with httpx.AsyncClient(trust_env=False) as client:
        resp = await client.get(
            cube_url,
            params={"query": json.dumps(rewritten_query)},
            headers={"Authorization": cube_token},
            timeout=20.0,
        )
        resp.raise_for_status()
    raw = resp.json()
    if raw.get("error"):
        raise HTTPException(status_code=502, detail="La fuente no pudo completar la consulta. Volvé a intentarlo.")
    if requires_post_compute_order and len(raw.get("data") or []) >= MAX_POWERBI_LIMIT:
        raise HTTPException(
            status_code=422,
            detail="No puedo determinar un ranking completo con tantos resultados. Acotá el período o los filtros para evaluar todos los candidatos.",
        )
    processed = post_process_cube_response(raw, original_measures, computed_info, reverse_map={})
    if requires_post_compute_order:
        processed["data"] = apply_post_compute_order(
            processed.get("data") or [],
            query.get("order"),
            requested_limit,
        )
        sort_only_metrics = set(cube_query["measures"]) - set(query.get("measures") or [])
        processed["data"] = [
            {key: value for key, value in row.items() if key not in sort_only_metrics}
            for row in processed["data"]
        ]
    return {
        "provider": "cube",
        "query": {"intent": query, "compiled": rewritten_query},
        "data": processed.get("data", []),
        "raw": processed,
    }


async def validate_query_against_catalog(
    query: dict[str, Any],
    *,
    user_id: str,
    connection_id: str,
    metric_catalog: list[dict[str, Any]],
    semantic_catalog: Optional[dict[str, Any]] = None,
    internal_aggregate_members: Optional[set[str]] = None,
) -> None:
    catalog = semantic_catalog or await fetch_semantic_catalog(user_id, connection_id)
    catalog_metrics = {
        metric.get("key")
        for metric in catalog.get("metrics") or []
        if metric.get("key")
    }
    catalog_fields = {
        field.get("semantic_key"): field
        for field in catalog.get("fields") or []
        if field.get("semantic_key") and not field.get("is_hidden") and field.get("is_ai_enabled", True)
    }
    custom_metrics = {
        metric.get("key"): metric
        for metric in metric_catalog
        if metric.get("source") == "custom" and metric.get("key")
    }
    aggregate_helpers = {
        metric.get("key")
        for metric in metric_catalog
        if metric.get("source") == "aggregate_helper" and metric.get("key")
    }

    allowed_measures = set(catalog_metrics) | set(custom_metrics.keys())
    # Internal probes may only use declared helpers, never arbitrary members.
    allowed_measures |= aggregate_helpers.intersection(internal_aggregate_members or set())
    allowed_custom_dependencies = set(catalog_metrics) | aggregate_helpers
    allowed_dimensions = {
        key
        for key, field in catalog_fields.items()
        if field.get("field_kind") != "measure"
    }
    allowed_time_dimensions = {
        key
        for key, field in catalog_fields.items()
        if field.get("field_kind") == "time"
    }

    def require_member(member: Any, allowed: set[str], member_type: str) -> str:
        if not isinstance(member, str) or member not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"{member_type} no existe en el catalogo semantico activo: {member}",
            )
        return member

    measures_to_validate = list(dict.fromkeys([
        *(query.get("measures") or []),
        *(member for member, _ in _normalized_order(query.get("order")) if member in custom_metrics),
    ]))
    for measure in measures_to_validate:
        measure_key = require_member(measure, allowed_measures, "La metrica")
        custom_metric = custom_metrics.get(measure_key)
        if custom_metric:
            for dependency in custom_metric.get("cube_dependencies") or []:
                require_member(dependency, allowed_custom_dependencies, "La dependencia de la metrica custom")

    for dimension in query.get("dimensions") or []:
        require_member(dimension, allowed_dimensions, "La dimension")

    for item in query.get("timeDimensions") or []:
        if not isinstance(item, dict):
            continue
        dimension = item.get("dimension")
        if dimension:
            require_member(dimension, allowed_time_dimensions, "La dimension temporal")

    def require_filter_member(member: str) -> None:
        require_member(member, allowed_measures | allowed_dimensions | allowed_time_dimensions, "El filtro")
        if member in custom_metrics:
            raise ValueError("Los filtros sobre metricas personalizadas aun no se pueden ejecutar de forma validada.")
    try:
        validate_filters(query.get("filters", []), require_filter_member)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    for member, _ in _normalized_order(query.get("order")):
        require_member(
            member,
            allowed_measures | allowed_dimensions | allowed_time_dimensions,
            "El campo de orden",
        )


def _member_index(fields: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index = {}
    for field in fields:
        candidates = {
            field.get("semantic_key", ""),
            field.get("name", ""),
            field.get("display_name", ""),
        }
        metadata = field.get("metadata") or {}
        if metadata.get("dax_reference"):
            candidates.add(metadata["dax_reference"])
        for value in candidates:
            if value:
                index[value] = field
                index[normalize_alias(value)] = field
    return index


def _resolve_member(value: str, fields: list[dict[str, Any]], kinds: set[str]) -> dict[str, Any]:
    index = _member_index(fields)
    field = index.get(value) or index.get(normalize_alias(value))
    if not field or field.get("field_kind") not in kinds:
        raise HTTPException(status_code=422, detail=f"No encontre el campo semantico permitido: {value}")
    if field.get("is_hidden") or not field.get("is_ai_enabled", True):
        raise HTTPException(status_code=403, detail=f"El campo no esta habilitado para IA: {value}")
    return field


def _dax_string(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = str(value).replace('"', '""')
    return f'"{text}"'


def _date_expr(value: str) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(value))
    if not match:
        raise HTTPException(status_code=422, detail=f"Fecha invalida para Power BI: {value}")
    year, month, day = match.groups()
    try:
        date(int(year), int(month), int(day))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Fecha invalida para Power BI: {value}")
    return f"DATE({int(year)}, {int(month)}, {int(day)})"


def _dax_filter_literal(value: Any, field: dict[str, Any]) -> str:
    kind = str(field.get("data_type") or "").lower()
    if kind in {"number", "numeric", "integer", "int", "int64", "decimal", "float", "double", "currency"}:
        text = str(value)
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
            raise HTTPException(status_code=422, detail="El filtro numérico requiere un valor decimal válido.")
        return text
    if kind in {"date", "datetime", "timestamp", "datetime2"}:
        return _date_expr(value)
    return _dax_string(value)


def _field_dax_ref(field: dict[str, Any]) -> str:
    metadata = field.get("metadata") or {}
    dax_ref = metadata.get("dax_reference")
    if dax_ref:
        return dax_ref
    table = (field.get("semantic_key") or "").split(".", 1)[0]
    return dax_column_ref(table, field.get("name") or field.get("display_name") or "")


def _build_filter_expression(filter_item: dict[str, Any], fields: list[dict[str, Any]]) -> Optional[str]:
    group = next((key for key in ("and", "or") if key in filter_item), None)
    if group:
        references = []
        def predicate(node):
            logical = next((k for k in ("and", "or") if k in node), None)
            if logical:
                children = node[logical]
                if not isinstance(children, list) or not children:
                    raise HTTPException(status_code=422, detail="Grupo de filtros vacío o inválido.")
                joiner = " && " if logical == "and" else " || "
                return "(" + joiner.join(predicate(child) for child in children) + ")"
            member = node.get("member") or node.get("dimension") or node.get("field")
            field = _resolve_member(str(member), fields, {"dimension", "time", "id", "unknown"})
            ref = _field_dax_ref(field)
            if ref not in references:
                references.append(ref)
            alias = f"[__filter{references.index(ref)}]"
            operator = str(node.get("operator") or "equals").lower()
            values = node.get("values")
            if not isinstance(values, list) or not values or any(v is None for v in values):
                raise HTTPException(status_code=422, detail="El filtro requiere valores explícitos.")
            if operator in {"equals", "in", "notequals", "notin"}:
                test = f"{alias} IN {{{', '.join(_dax_filter_literal(v, field) for v in values)}}}"
                return f"NOT ({test})" if operator in {"notequals", "notin"} else test
            comparator = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}.get(operator)
            if comparator and len(values) == 1:
                return f"{alias} {comparator} {_dax_filter_literal(values[0], field)}"
            raise HTTPException(status_code=422, detail=f"Operador de filtro no soportado para Power BI: {operator}")
        condition = predicate(filter_item)
        if len(references) > 6:
            raise HTTPException(status_code=422, detail="Acotá el filtro combinado a seis campos.")
        tables = [f'SELECTCOLUMNS(ALL({ref}), "__filter{i}", {ref})' for i, ref in enumerate(references)]
        table = tables[0] if len(tables) == 1 else f"CROSSJOIN({', '.join(tables)})"
        return f"TREATAS(FILTER({table}, {condition}), {', '.join(references)})"
    member = filter_item.get("member") or filter_item.get("dimension") or filter_item.get("field")
    if not member:
        raise HTTPException(status_code=422, detail="El filtro no identifica un campo permitido.")
    field = _resolve_member(str(member), fields, {"dimension", "time", "id", "unknown"})
    ref = _field_dax_ref(field)
    operator = str(filter_item.get("operator") or "equals").lower()
    values = filter_item.get("values")
    if values is None:
        values = filter_item.get("value")
    if not isinstance(values, list):
        values = [values]
    values = [v for v in values if v is not None]
    if not values:
        raise HTTPException(status_code=422, detail="El filtro requiere valores explícitos.")
    if operator in {"equals", "in"}:
        return f"TREATAS({{{', '.join(_dax_filter_literal(v, field) for v in values)}}}, {ref})"
    raise HTTPException(status_code=422, detail=f"Operador de filtro no soportado para Power BI: {operator}")


def _build_time_filter(time_dimensions: list[dict[str, Any]], fields: list[dict[str, Any]]) -> Optional[str]:
    if len(time_dimensions) > 1:
        expressions = [_build_time_filter([item], fields) for item in time_dimensions]
        return ", ".join(expr for expr in expressions if expr) or None
    td = next((item for item in time_dimensions if isinstance(item, dict)), None)
    if not td:
        return None
    date_range = td.get("dateRange") or td.get("date_range")
    if not date_range:
        return None
    dimension = td.get("dimension")
    if dimension:
        field = _resolve_member(str(dimension), fields, {"time", "dimension"})
    else:
        field = next((f for f in fields if f.get("field_kind") == "time" and f.get("is_ai_enabled", True)), None)
        if not field:
            raise HTTPException(status_code=422, detail="No hay campo de fecha disponible para filtrar")
    if isinstance(date_range, str):
        raise HTTPException(status_code=422, detail="Power BI requiere dateRange explicito ['YYYY-MM-DD','YYYY-MM-DD']")
    if not isinstance(date_range, list) or len(date_range) != 2:
        raise HTTPException(status_code=422, detail="dateRange invalido para Power BI")
    ref = _field_dax_ref(field)
    return f"FILTER(ALL({ref}), {ref} >= {_date_expr(date_range[0])} && {ref} < ({_date_expr(date_range[1])} + 1))"


def compile_powerbi_dax(query: dict[str, Any], fields: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    limit = max(1, min(int(query.get("limit") or DEFAULT_LIMIT), MAX_POWERBI_LIMIT))
    metric_fields = [_resolve_member(str(m), fields, {"measure"}) for m in query.get("measures", [])]
    if not metric_fields:
        raise HTTPException(status_code=422, detail="Power BI requiere al menos una medida")

    dimension_fields = [
        _resolve_member(str(dim), fields, {"dimension", "time", "id", "unknown"})
        for dim in query.get("dimensions", [])
    ]
    for scope in query.get("timeDimensions") or []:
        grain = scope.get("granularity")
        if not grain:
            continue
        field = _resolve_member(str(scope.get("dimension")), fields, {"time"})
        metadata = field.get("metadata") or {}
        grain_member = (metadata.get("granularity_members") or {}).get(grain)
        timestamp = str(field.get("data_type") or "").lower() in {"datetime", "datetime64", "timestamp", "datetime2"}
        if grain != "day" or timestamp or grain_member:
            if not grain_member:
                raise HTTPException(status_code=422, detail="Esta granularidad requiere una columna temporal publicada en el modelo; no se devolverá un total en su lugar.")
            field = _resolve_member(grain_member, fields, {"dimension", "time"})
        if field not in dimension_fields:
            dimension_fields.append(field)

    filters = []
    for item in query.get("filters", []) or []:
        if isinstance(item, dict):
            expr = _build_filter_expression(item, fields)
            if expr:
                filters.append(expr)
    time_expr = _build_time_filter(query.get("timeDimensions") or [], fields)
    if time_expr:
        filters.append(time_expr)

    measure_pairs = []
    for field in metric_fields:
        label = field.get("display_name") or field.get("name") or field["semantic_key"]
        measure_pairs.append(f'"{label.replace(chr(34), chr(34) + chr(34))}", {_field_dax_ref(field)}')

    if dimension_fields:
        summarize_args = [_field_dax_ref(field) for field in dimension_fields]
        summarize_args.extend(filters)
        summarize_args.extend(measure_pairs)
        table_expr = f"SUMMARIZECOLUMNS({', '.join(summarize_args)})"
        order_items = _normalized_order(query.get("order"))
        if order_items:
            order_member, order_direction = order_items[0]
            order_field = _resolve_member(order_member, fields, {"measure", "dimension", "time", "id", "unknown"})
            dax_direction = "ASC" if order_direction == "asc" else "DESC"
            dax = f"EVALUATE TOPN({limit}, {table_expr}, {_field_dax_ref(order_field)}, {dax_direction})"
        else:
            dax = f"EVALUATE TOPN({limit}, {table_expr})"
    else:
        table_expr = f"ROW({', '.join(measure_pairs)})"
        if filters:
            table_expr = f"CALCULATETABLE({table_expr}, {', '.join(filters)})"
        dax = f"EVALUATE {table_expr}"

    if not dax.strip().upper().startswith("EVALUATE"):
        raise HTTPException(status_code=500, detail="DAX inseguro: falta EVALUATE")

    return dax, {
        "metrics": [field["semantic_key"] for field in metric_fields],
        "dimensions": [field["semantic_key"] for field in dimension_fields],
        "order": dict(_normalized_order(query.get("order"))),
        "limit": limit,
    }


async def execute_powerbi_semantic_query(
    *,
    query: dict[str, Any],
    connection_id: str,
    user_id: str,
    semantic_catalog: Optional[dict[str, Any]] = None,
    connection: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    connection = connection or await get_connection(connection_id, user_id)
    if connection.get("provider") != "powerbi":
        raise HTTPException(status_code=422, detail="La conexion no es Power BI")
    catalog = semantic_catalog or await fetch_semantic_catalog(user_id, connection_id)
    fields = catalog.get("fields") or []
    if not fields:
        raise HTTPException(status_code=422, detail="La conexion no tiene catalogo sincronizado")
    dax, resolved = compile_powerbi_dax(query, fields)
    config = connection.get("config") or {}
    dataset_id = config.get("dataset_id")
    workspace_id = config.get("workspace_id")
    if not dataset_id:
        raise HTTPException(status_code=422, detail="La conexion no tiene dataset seleccionado")
    client = await powerbi_client_for_connection(connection)
    raw = await client.execute_dax(dataset_id, dax, workspace_id=workspace_id)
    rows = (((raw.get("results") or [{}])[0].get("tables") or [{}])[0].get("rows") or [])
    # Provider aliases are transport details. Evidence always uses the exact
    # catalog keys requested by the caller, as the Cube adapter does.
    normalized_rows = []
    for row in rows:
        normalized = {}
        for key in [*resolved["metrics"], *resolved["dimensions"]]:
            field = _resolve_member(key, fields, {"measure", "dimension", "time", "id", "unknown"})
            ref = _field_dax_ref(field)
            label = field.get("display_name") or field.get("name") or key
            aliases = [key, ref, ref.replace("'", ""), f"[{label}]"]
            for alias in aliases:
                if alias in row:
                    normalized[key] = row[alias]
                    break
        normalized_rows.append(normalized)
    normalized_rows = apply_post_compute_order(normalized_rows, query.get("order"), resolved["limit"])
    return {
        "provider": "powerbi",
        "connection_id": connection_id,
        "model_id": (catalog.get("models") or [{}])[0].get("id"),
        "query": {"intent": query, "compiled": dax, "resolved": resolved},
        "data": normalized_rows,
        "raw": raw,
    }


async def _resolve_query_connection(connection_id: Optional[str], user_id: Optional[str]) -> Optional[dict[str, Any]]:
    if connection_id:
        if not user_id:
            raise HTTPException(status_code=401, detail="Authorization requerido para conexiones semanticas")
        return await get_connection(connection_id, user_id)

    if not user_id:
        return None

    connections = await list_connections(user_id)
    ready_connections = [
        connection
        for connection in connections
        if connection.get("status") in {"ready", "connected", "oauth_connected"}
    ]
    if not ready_connections:
        return None
    return next((connection for connection in ready_connections if connection.get("is_default")), ready_connections[0])


async def execute_semantic_query(
    payload: dict[str, Any],
    *,
    user_id: Optional[str] = None,
    metric_catalog: Optional[list[dict[str, Any]]] = None,
    semantic_catalog: Optional[dict[str, Any]] = None,
    resolved_connection: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    query = normalize_query_payload(payload)
    connection_id = payload.get("connection_id") or query.get("connection_id")
    provider = payload.get("provider") or query.get("provider")
    connection = resolved_connection or await _resolve_query_connection(connection_id, user_id)

    if connection:
        resolved_connection_id = connection["id"]
        if connection.get("provider") == "powerbi":
            return await execute_powerbi_semantic_query(
                query=query,
                connection_id=resolved_connection_id,
                user_id=user_id or "",
                semantic_catalog=semantic_catalog,
                connection=connection,
            )
        if connection.get("provider") == "cube":
            if not user_id:
                raise HTTPException(status_code=401, detail="Authorization requerido para conexiones semanticas")
            from api.semantic_metrics import build_metric_catalog

            metric_catalog = metric_catalog or await build_metric_catalog(
                user_id=user_id,
                connection_id=resolved_connection_id,
                provider_catalog=semantic_catalog,
            )
            await validate_query_against_catalog(
                query,
                user_id=user_id,
                connection_id=resolved_connection_id,
                metric_catalog=metric_catalog,
                semantic_catalog=semantic_catalog,
            )
            return await execute_cube_semantic_query(query, metric_catalog=metric_catalog)
        raise HTTPException(status_code=422, detail="Provider semantico no soportado para esta conexion")

    if provider == "powerbi":
        raise HTTPException(status_code=422, detail="Power BI requiere connection_id")

    raise HTTPException(
        status_code=422,
        detail="Conecta una fuente de datos antes de consultar. Las consultas solo se ejecutan contra conexiones activas.",
    )


async def execute_semantic_query_batch(
    payloads: list[dict[str, Any]],
    *,
    user_id: Optional[str] = None,
    connection_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    if not payloads:
        return []

    resolved_connection_id = connection_id or payloads[0].get("connection_id")
    connection = await _resolve_query_connection(resolved_connection_id, user_id)
    if not connection:
        raise HTTPException(
            status_code=422,
            detail="Conecta una fuente de datos antes de consultar. Las consultas solo se ejecutan contra conexiones activas.",
        )

    resolved_connection_id = connection["id"]
    semantic_catalog: Optional[dict[str, Any]] = None
    metric_catalog: Optional[list[dict[str, Any]]] = None

    if connection.get("provider") in {"cube", "powerbi"}:
        if not user_id:
            raise HTTPException(status_code=401, detail="Authorization requerido para conexiones semanticas")
        semantic_catalog = await fetch_semantic_catalog(user_id, resolved_connection_id)

    if connection.get("provider") == "cube":
        from api.semantic_metrics import build_metric_catalog

        metric_catalog = await build_metric_catalog(
            user_id=user_id,
            connection_id=resolved_connection_id,
            provider_catalog=semantic_catalog,
        )

    semaphore = asyncio.Semaphore(4)

    async def run(payload: dict[str, Any]) -> dict[str, Any]:
        query_payload = dict(payload)
        query_payload["connection_id"] = resolved_connection_id
        try:
            async with semaphore:
                result = await execute_semantic_query(
                    query_payload,
                    user_id=user_id,
                    metric_catalog=metric_catalog,
                    semantic_catalog=semantic_catalog,
                    resolved_connection=connection,
                )
            result["ok"] = True
            return result
        except HTTPException as exc:
            return {
                "ok": False,
                "data": [],
                "error": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                "status_code": exc.status_code,
            }
        except Exception as exc:
            return {
                "ok": False,
                "data": [],
                "error": str(exc),
                "status_code": 500,
            }

    return await asyncio.gather(*(run(payload) for payload in payloads))


async def get_semantic_time_bounds(*, user_id: str, connection_id: str,
                                   dimension: str, filters: Optional[list[dict[str, Any]]] = None) -> Optional[list[str]]:
    """Read authorized factual bounds, without publishing internal measures."""
    connection = await get_connection(connection_id, user_id)
    catalog = await fetch_semantic_catalog(user_id, connection_id)
    fields = catalog.get("fields") or []
    field = next((f for f in fields if f.get("semantic_key") == dimension
                  and f.get("field_kind") == "time" and not f.get("is_hidden")
                  and f.get("is_ai_enabled", True)), None)
    if not field:
        return None
    filters = filters or []
    if connection.get("provider") == "cube":
        from api.semantic_metrics import build_metric_catalog
        metrics = await build_metric_catalog(user_id=user_id, connection_id=connection_id, provider_catalog=catalog)
        helpers = {}
        for metric in metrics:
            if metric.get("source") != "aggregate_helper":
                continue
            for operation in ("min", "max"):
                if re.fullmatch(rf"{operation}\(\s*{re.escape(dimension)}\s*\)", metric.get("expression") or ""):
                    helpers[operation] = metric["key"]
        if set(helpers) != {"min", "max"}:
            return None
        query = {"measures": [helpers["min"], helpers["max"]], "filters": filters, "limit": 1}
        await validate_query_against_catalog(query, user_id=user_id, connection_id=connection_id,
                                             metric_catalog=metrics, semantic_catalog=catalog,
                                             internal_aggregate_members=set(helpers.values()))
        result = await execute_cube_semantic_query(query, metric_catalog=metrics)
        rows = result.get("data") or []
        if not rows:
            return None
        values = [rows[0].get(helpers[operation]) for operation in ("min", "max")]
    elif connection.get("provider") == "powerbi":
        ref = _field_dax_ref(field)
        filter_expressions = [_build_filter_expression(item, fields) for item in filters]
        if any(expr is None for expr in filter_expressions):
            raise HTTPException(status_code=422, detail="No se pudo conservar el filtro de cobertura.")
        expression = f'ROW("__minimum", MIN({ref}), "__maximum", MAX({ref}))'
        if filter_expressions:
            expression = f"CALCULATETABLE({expression}, {', '.join(filter_expressions)})"
        config = connection.get("config") or {}
        client = await powerbi_client_for_connection(connection)
        raw = await client.execute_dax(config.get("dataset_id"), f"EVALUATE {expression}", workspace_id=config.get("workspace_id"))
        rows = (((raw.get("results") or [{}])[0].get("tables") or [{}])[0].get("rows") or [])
        if not rows:
            return None
        values = [rows[0].get(k, rows[0].get(f"[{k}]")) for k in ("__minimum", "__maximum")]
    else:
        return None
    if any(not value or not re.match(r"^\d{4}-\d{2}-\d{2}", str(value)) for value in values):
        return None
    return [str(value)[:10] for value in values]
