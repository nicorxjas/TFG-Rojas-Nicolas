from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from services import supabase_rest as sb
from services.semantic_catalog import clear_semantic_catalog_cache, fetch_semantic_catalog
from services.supabase_rest import user_id_from_authorization
from api.semantic_metrics import build_metric_catalog, compile_metric_expression, metric_key_for_name


router = APIRouter(prefix="/semantic-metrics", tags=["semantic-metrics"])


class CreateMetricDraftRequest(BaseModel):
    connection_id: Optional[str] = None
    name: str
    description: str = ""
    expression: dict[str, Any] | str = Field(default_factory=dict)
    compiled_payload: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    source_prompt: str = ""


@router.post("/drafts", status_code=201)
async def create_metric_draft(
    request: CreateMetricDraftRequest,
    authorization: str = Header(...),
):
    user_id = user_id_from_authorization(authorization)
    if not request.name.strip():
        raise HTTPException(status_code=422, detail="La sugerencia de indicador necesita nombre.")
    row = {
        "owner_user_id": user_id,
        "connection_id": request.connection_id,
        "name": request.name.strip(),
        "description": request.description.strip(),
        "expression": request.expression,
        "compiled_payload": request.compiled_payload,
        "dependencies": request.dependencies,
        "status": "draft",
        "created_by_ai": True,
        "source_prompt": request.source_prompt,
    }
    rows = await sb.rest_post("semantic_metric_drafts", row)
    return rows[0] if rows else row


async def _get_draft(draft_id: str, user_id: str) -> dict[str, Any]:
    rows = await sb.rest_get(
        "semantic_metric_drafts",
        {
            "select": "*",
            "id": f"eq.{draft_id}",
            "owner_user_id": f"eq.{user_id}",
            "limit": "1",
        },
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Sugerencia de indicador no encontrada.")
    return rows[0]


def _draft_expression(draft: dict[str, Any]) -> str:
    expression = draft.get("expression")
    if isinstance(expression, str):
        return expression.strip()
    if isinstance(expression, dict):
        return str(expression.get("expression") or expression.get("text") or "").strip()
    return ""


def _filter_approved_catalog(metrics: list[dict[str, Any]], provider_catalog: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    if not provider_catalog:
        return metrics
    approved_field_ids = {
        field.get("id")
        for field in provider_catalog.get("fields") or []
        if (field.get("approval_status") or "approved") == "approved"
    }
    approved_field_keys = {
        field.get("semantic_key")
        for field in provider_catalog.get("fields") or []
        if (field.get("approval_status") or "approved") == "approved"
    }
    return [
        metric
        for metric in metrics
        if (
            metric.get("source") in {"custom", "aggregate_helper"}
            or metric.get("field_id") in approved_field_ids
            or metric.get("key") in approved_field_keys
        )
    ]


@router.post("/drafts/{draft_id}/approve")
async def approve_metric_draft(draft_id: str, authorization: str = Header(...)):
    user_id = user_id_from_authorization(authorization)
    draft = await _get_draft(draft_id, user_id)
    if draft.get("status") == "approved":
        return {"draft": draft, "metric": None}
    if draft.get("status") == "rejected":
        raise HTTPException(status_code=409, detail="Esta sugerencia ya fue rechazada.")

    connection_id = draft.get("connection_id")
    provider_catalog = None
    if connection_id:
        provider_catalog = await fetch_semantic_catalog(user_id, connection_id, include_review=True)
    catalog = _filter_approved_catalog(
        await build_metric_catalog(user_id=user_id, connection_id=connection_id, provider_catalog=provider_catalog),
        provider_catalog,
    )
    expression = _draft_expression(draft)
    if not expression:
        raise HTTPException(status_code=422, detail="La sugerencia no tiene una definicion valida.")

    try:
        compiled = compile_metric_expression(expression, catalog)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now = datetime.now(timezone.utc).isoformat()
    metric_key = metric_key_for_name(draft["name"])
    metric_row = {
        "user_id": user_id,
        "name": draft["name"].strip(),
        "slug": metric_key.split(".", 1)[1],
        "metric_key": metric_key,
        "description": (draft.get("description") or "").strip(),
        "expression": expression,
        "compiled_expression": compiled["compiled_expression"],
        "variables": compiled["variables"],
        "dependencies": compiled["dependencies"],
        "cube_dependencies": compiled["cube_dependencies"],
        "format": (draft.get("compiled_payload") or {}).get("format") or "number",
        "status": "active",
        "created_by_ai": bool(draft.get("created_by_ai", True)),
        "approved_at": now,
    }
    existing_metric = await sb.rest_get(
        "semantic_metrics",
        {
            "select": "id",
            "user_id": f"eq.{user_id}",
            "slug": f"eq.{metric_row['slug']}",
            "limit": "1",
        },
    )
    if existing_metric:
        update_row = {key: value for key, value in metric_row.items() if key not in {"user_id", "slug", "metric_key"}}
        update_row["updated_at"] = now
        metric_rows = await sb.rest_patch(
            "semantic_metrics",
            update_row,
            params={"id": f"eq.{existing_metric[0]['id']}", "user_id": f"eq.{user_id}"},
        )
    else:
        metric_rows = await sb.rest_post("semantic_metrics", metric_row)
    metric = metric_rows[0] if metric_rows else metric_row
    updated_rows = await sb.rest_patch(
        "semantic_metric_drafts",
        {
            "status": "approved",
            "compiled_payload": {
                **(draft.get("compiled_payload") or {}),
                **compiled,
                "semantic_metric_id": metric.get("id"),
            },
            "updated_at": now,
        },
        params={"id": f"eq.{draft_id}", "owner_user_id": f"eq.{user_id}"},
    )
    clear_semantic_catalog_cache(user_id, connection_id)
    return {"draft": updated_rows[0] if updated_rows else draft, "metric": metric}


@router.post("/drafts/{draft_id}/reject")
async def reject_metric_draft(draft_id: str, authorization: str = Header(...)):
    user_id = user_id_from_authorization(authorization)
    await _get_draft(draft_id, user_id)
    rows = await sb.rest_patch(
        "semantic_metric_drafts",
        {
            "status": "rejected",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        params={"id": f"eq.{draft_id}", "owner_user_id": f"eq.{user_id}"},
    )
    return {"draft": rows[0] if rows else {"id": draft_id, "status": "rejected"}}
