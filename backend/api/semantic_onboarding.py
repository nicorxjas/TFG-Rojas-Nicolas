import json
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from api.llm import llm_client, get_llm_timeout, get_llm_chat_url, get_llm_headers, get_llm_model, llm_is_configured, llm_payload
from api.semantic_metrics import build_metric_catalog, compile_metric_expression
from services import supabase_rest as sb
from services.company_context import company_context_prompt, fetch_company_context, require_company_context
from services.semantic_catalog import clear_semantic_catalog_cache, fetch_semantic_catalog, get_connection, list_connections, utc_now_iso
from services.supabase_rest import user_id_from_authorization


router = APIRouter(prefix="/semantic-model/onboarding", tags=["semantic-onboarding"])


class SuggestOnboardingMetricsRequest(BaseModel):
    connection_id: str
    goal: str = ""
    limit: int = Field(default=6, ge=1, le=10)


def _approval_status(item: dict[str, Any]) -> str:
    return str(item.get("approval_status") or "approved")


def _visible_review_field(field: dict[str, Any]) -> bool:
    return not field.get("is_hidden") and field.get("is_ai_enabled", True) is not False


def _business_table_name(table: Optional[dict[str, Any]]) -> str:
    metadata = (table or {}).get("metadata") or {}
    return str(
        (table or {}).get("business_name")
        or (table or {}).get("suggested_business_name")
        or (table or {}).get("display_name")
        or metadata.get("sheet_name")
        or (table or {}).get("name")
        or "Area de negocio"
    )


def _review_excel_connection(connections: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    review_excel = [
        connection
        for connection in connections
        if connection.get("connector_key") == "excel" and connection.get("status") == "review"
    ]
    return next((connection for connection in review_excel if connection.get("is_default")), review_excel[0] if review_excel else None)


def _field_display_payload(field: dict[str, Any], table: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {
        **field,
        "business_area": _business_table_name(table),
        "effective_name": (
            field.get("business_name")
            or field.get("suggested_business_name")
            or field.get("display_name")
            or field.get("name")
        ),
        "effective_description": field.get("description") or field.get("suggested_description") or "",
    }


def _metric_business_definition(
    metric: dict[str, Any],
    field: Optional[dict[str, Any]] = None,
    table: Optional[dict[str, Any]] = None,
) -> str:
    description = str(metric.get("description") or "").strip()
    if description:
        return description

    area_name = _business_table_name(table)
    metric_name = str(metric.get("name") or (field or {}).get("business_name") or "indicador").strip()
    metadata = (field or {}).get("metadata") or {}
    aggregation = str(metadata.get("aggregation") or "").lower()
    expression = str(metric.get("expression") or "").lower()
    if aggregation == "count" or expression.startswith("count("):
        return f"Cuenta registros de {area_name}."
    if aggregation == "sum" or expression.startswith("sum("):
        return f"Suma {metric_name.lower()} para analizar {area_name}."
    return f"Indicador base para analizar {area_name}."


def _metric_display_payload(
    metric: dict[str, Any],
    field: Optional[dict[str, Any]] = None,
    table: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        **metric,
        "business_area": _business_table_name(table),
        "business_formula": _metric_business_definition(metric, field, table),
    }


async def _drafts_for_connection(user_id: str, connection_id: Optional[str]) -> list[dict[str, Any]]:
    params = {
        "select": "*",
        "owner_user_id": f"eq.{user_id}",
        "order": "created_at.desc",
    }
    if connection_id:
        params["connection_id"] = f"eq.{connection_id}"
    return await sb.rest_get("semantic_metric_drafts", params)


async def _onboarding_catalog(user_id: str, connection_id: Optional[str]) -> tuple[dict[str, Any], Optional[str]]:
    selected_connection_id = connection_id
    if not selected_connection_id:
        connections = await list_connections(user_id)
        active = _review_excel_connection(connections)
        selected_connection_id = active.get("id") if active else None

    catalog = await fetch_semantic_catalog(user_id, selected_connection_id, include_review=True)
    return catalog, selected_connection_id or catalog.get("selected_connection_id")


def _approved_metric_catalog(all_metrics: list[dict[str, Any]], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    approved_field_ids = {
        field.get("id")
        for field in catalog.get("fields") or []
        if _visible_review_field(field) and _approval_status(field) == "approved"
    }
    approved_field_keys = {
        field.get("semantic_key")
        for field in catalog.get("fields") or []
        if _visible_review_field(field) and _approval_status(field) == "approved"
    }
    return [
        metric
        for metric in all_metrics
        if (
            metric.get("source") == "custom"
            or metric.get("field_id") in approved_field_ids
            or metric.get("key") in approved_field_keys
        )
    ]


@router.get("/review-connection")
async def get_review_connection(authorization: str = Header(...)):
    user_id = user_id_from_authorization(authorization)
    connection = _review_excel_connection(await list_connections(user_id))
    return {"connection": connection}


@router.get("")
async def get_semantic_onboarding(connection_id: Optional[str] = None, authorization: str = Header(...)):
    user_id = user_id_from_authorization(authorization)
    company_context = await fetch_company_context(user_id)
    catalog, selected_connection_id = await _onboarding_catalog(user_id, connection_id)
    drafts = await _drafts_for_connection(user_id, selected_connection_id)

    tables = catalog.get("tables") or []
    all_fields = catalog.get("fields") or []
    table_by_id = {table.get("id"): table for table in tables if table.get("id")}
    table_by_name = {table.get("name"): table for table in tables if table.get("name")}
    field_by_id = {field.get("id"): field for field in all_fields if field.get("id")}

    fields = [
        _field_display_payload(field, table_by_id.get(field.get("table_id")))
        for field in all_fields
        if field.get("field_kind") != "measure" and _visible_review_field(field)
    ]
    base_metrics = []
    for metric in catalog.get("metrics") or []:
        if metric.get("source") == "custom":
            continue
        field = field_by_id.get(metric.get("field_id"))
        table = table_by_id.get((field or {}).get("table_id"))
        if table is None:
            table_key = str(metric.get("key") or "").split(".", 1)[0]
            table = table_by_name.get(table_key)
        base_metrics.append({
            **_metric_display_payload(metric, field, table),
            "approval_status": _approval_status(field or {}),
        })
    review_items = [field for field in all_fields if _visible_review_field(field)]
    pending = [field for field in review_items if _approval_status(field) == "review"]

    return {
        "connection_id": selected_connection_id,
        "connection": next(
            (connection for connection in catalog.get("connections") or [] if connection.get("id") == selected_connection_id),
            None,
        ),
        "company_context": company_context,
        "tables": catalog.get("tables") or [],
        "fields": fields,
        "metrics": base_metrics,
        "drafts": drafts,
        "approval_summary": {
            "total": len(review_items),
            "approved": len(review_items) - len(pending),
            "pending": len(pending),
        },
    }


@router.post("/metrics/suggest")
async def suggest_onboarding_metrics(request: SuggestOnboardingMetricsRequest, authorization: str = Header(...)):
    user_id = user_id_from_authorization(authorization)
    company_context = await require_company_context(user_id)
    catalog = await fetch_semantic_catalog(user_id, request.connection_id, include_review=True)
    all_metrics = await build_metric_catalog(user_id=user_id, connection_id=request.connection_id, provider_catalog=catalog)
    metric_catalog = _approved_metric_catalog(all_metrics, catalog)

    if not metric_catalog:
        raise HTTPException(status_code=422, detail="Aproba al menos un indicador base antes de generar sugerencias.")
    if not llm_is_configured():
        raise HTTPException(status_code=503, detail="No hay IA disponible para sugerir indicadores.")

    tables = catalog.get("tables") or []
    all_fields = catalog.get("fields") or []
    table_by_id = {table.get("id"): table for table in tables if table.get("id")}
    table_by_name = {table.get("name"): table for table in tables if table.get("name")}
    field_by_id = {field.get("id"): field for field in all_fields if field.get("id")}

    metric_lines = []
    for metric in metric_catalog:
        field = field_by_id.get(metric.get("field_id"))
        table = table_by_id.get((field or {}).get("table_id"))
        if table is None:
            table_key = str(metric.get("key") or "").split(".", 1)[0]
            table = table_by_name.get(table_key)
        metric_lines.append(
            f"- @{metric['name']}: {_metric_business_definition(metric, field, table)} Area: {_business_table_name(table)}"
        )
    metric_list = "\n".join(metric_lines)
    goal = request.goal.strip() or "Sugerir indicadores ejecutivos utiles para este catalogo."
    payload = llm_payload({
        "model": get_llm_model(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "Sos el agente de gobernanza de indicadores de Nyro BI AI. "
                    "Propones indicadores compuestos como sugerencias para aprobacion humana. "
                    "Usa solamente metricas disponibles con @Nombre y operaciones + - * / y parentesis. "
                    "No inventes campos, SQL ni agregaciones directas. "
                    "La explicacion debe ser ejecutiva y no debe incluir nombres fisicos, SQL, claves internas ni funciones tecnicas. "
                    "Responde solo JSON valido con {\"metrics\":[{\"name\":\"...\",\"description\":\"...\",\"expression\":\"...\",\"format\":\"number|currency|percent\",\"formula_explanation\":\"...\"}]}."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Contexto de empresa obligatorio:\n{company_context_prompt(company_context)}\n\n"
                    f"Metricas atomicas aprobadas:\n{metric_list}\n\n"
                    f"Objetivo: {goal}\n"
                    f"Maximo de sugerencias: {request.limit}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "stream": False,
        "temperature": 0.2,
    })

    try:
        async with llm_client(trust_env=False) as client:
            resp = await client.post(
                get_llm_chat_url(),
                headers=get_llm_headers(),
                json=payload,
                timeout=get_llm_timeout(60.0),
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            suggestion_json = json.loads(content)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="No pude generar indicadores sugeridos con IA.") from exc

    suggestions = suggestion_json.get("metrics") if isinstance(suggestion_json, dict) else None
    if not isinstance(suggestions, list):
        raise HTTPException(status_code=502, detail="La IA no devolvio una lista valida de indicadores.")

    created = []
    for suggestion in suggestions[: request.limit]:
        if not isinstance(suggestion, dict):
            continue
        name = str(suggestion.get("name") or "").strip()
        expression = str(suggestion.get("expression") or "").strip()
        if not name or not expression:
            continue
        try:
            compiled = compile_metric_expression(expression, metric_catalog)
        except ValueError:
            continue
        description = str(suggestion.get("description") or "").strip()
        row = {
            "owner_user_id": user_id,
            "connection_id": request.connection_id,
            "name": name[:140],
            "description": description[:500],
            "expression": expression,
            "compiled_payload": {
                **compiled,
                "format": suggestion.get("format") or "number",
                "formula_explanation": str(suggestion.get("formula_explanation") or "").strip()[:1000],
            },
            "dependencies": compiled.get("dependencies") or [],
            "status": "draft",
            "created_by_ai": True,
            "source_prompt": goal[:1000],
        }
        rows = await sb.rest_post("semantic_metric_drafts", row)
        if rows:
            created.append(rows[0])

    if not created:
        raise HTTPException(status_code=422, detail="No se pudo generar una definicion valida con los indicadores aprobados.")
    return {"drafts": created}


@router.post("/{connection_id}/complete")
async def complete_semantic_onboarding(connection_id: str, authorization: str = Header(...)):
    user_id = user_id_from_authorization(authorization)
    connection = await get_connection(connection_id, user_id)
    if connection.get("connector_key") != "excel":
        raise HTTPException(status_code=422, detail="El onboarding semantico solo aplica a conexiones Excel.")

    catalog = await fetch_semantic_catalog(user_id, connection_id, include_review=True)
    pending = [
        field
        for field in catalog.get("fields") or []
        if _visible_review_field(field) and _approval_status(field) != "approved"
    ]
    if pending:
        raise HTTPException(status_code=422, detail=f"Quedan {len(pending)} conceptos o indicadores sin aprobar.")

    now = datetime.now(timezone.utc).isoformat()
    models = catalog.get("models") or []
    model_ids = [model.get("id") for model in models if model.get("id")]
    if model_ids:
        model_filter = f"in.({','.join(model_ids)})"
        await sb.rest_patch(
            "semantic_tables",
            {
                "approval_status": "approved",
                "approved_at": now,
                "approved_by": user_id,
                "updated_at": now,
            },
            params={
                "owner_user_id": f"eq.{user_id}",
                "model_id": model_filter,
                "approval_status": "eq.review",
            },
            prefer="",
        )

    config = dict(connection.get("config") or {})
    config["onboarding"] = {"status": "complete", "completed_at": now}
    health = dict(connection.get("health") or {})
    health["metadata"] = "ready"
    health["onboarding"] = config["onboarding"]

    await sb.rest_patch(
        "connector_instances",
        {
            "status": "ready",
            "config": config,
            "health": health,
            "last_error": None,
            "last_sync_at": utc_now_iso(),
        },
        params={"id": f"eq.{connection_id}", "owner_user_id": f"eq.{user_id}"},
        prefer="",
    )
    clear_semantic_catalog_cache(user_id, connection_id)
    return {"status": "ready", "connection_id": connection_id}
