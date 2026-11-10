from typing import Any, Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from services.semantic_planner import compile_analysis_plan, execute_analysis_plan
from services.semantic_query_engine import execute_semantic_query, execute_semantic_query_batch
from services.supabase_rest import user_id_from_authorization


router = APIRouter(prefix="/semantic-query", tags=["semantic-query"])


class SemanticQueryRequest(BaseModel):
    connection_id: Optional[str] = None
    provider: Optional[str] = None
    query: dict = {}
    measures: list[str] = []
    metrics: list[str] = []
    dimensions: list[str] = []
    filters: list[dict] = []
    timeDimensions: list[dict] = []
    order: dict[str, str] = Field(default_factory=dict)
    limit: Optional[int] = None
    intent: Optional[str | dict[str, Any]] = None
    virtual_metrics: list[dict[str, Any]] = Field(default_factory=list)
    required_grain: Optional[str | list[str]] = None
    explain: bool = False


class SemanticQueryBatchRequest(BaseModel):
    connection_id: Optional[str] = None
    queries: list[dict[str, Any]] = Field(default_factory=list)


def _intent_prompt(request: SemanticQueryRequest) -> str:
    if isinstance(request.intent, str) and request.intent.strip():
        return request.intent.strip()
    if isinstance(request.intent, dict):
        value = request.intent.get("summary") or request.intent.get("description") or request.intent.get("task")
        if value:
            return str(value)
    return ""


def _inline_plan(request: SemanticQueryRequest) -> dict[str, Any]:
    query = request.query or {}
    virtual_keys = [metric.get("key") for metric in request.virtual_metrics if metric.get("key")]
    return {
        "plan_id": "inline_semantic_query",
        "prompt": _intent_prompt(request),
        "connection_id": request.connection_id,
        "intent": request.intent or {},
        "virtual_metrics": request.virtual_metrics,
        "queries": [
            {
                "id": "inline",
                "label": "semantic_query",
                "purpose": _intent_prompt(request),
                "query": query,
                "virtual_metrics": virtual_keys,
            }
        ],
        "warnings": [],
        "validation_errors": [],
    }


@router.post("/batch")
async def query_semantic_model_batch(
    request: SemanticQueryBatchRequest,
    authorization: Optional[str] = Header(default=None),
):
    user_id = user_id_from_authorization(authorization) if authorization else None
    payloads = [{"connection_id": request.connection_id, "query": query} for query in request.queries[:50]]
    results = await execute_semantic_query_batch(
        payloads,
        user_id=user_id,
        connection_id=request.connection_id,
    )
    return {"results": results}


@router.post("")
async def query_semantic_model(
    request: SemanticQueryRequest,
    authorization: Optional[str] = Header(default=None),
):
    user_id = user_id_from_authorization(authorization) if authorization else None
    prompt = _intent_prompt(request)

    if prompt and not request.query:
        if not user_id:
            user_id = user_id_from_authorization(authorization)
        plan = await compile_analysis_plan(
            prompt=prompt,
            user_id=user_id,
            connection_id=request.connection_id,
            context={"required_grain": request.required_grain} if request.required_grain else {},
        )
        if request.virtual_metrics:
            existing = {metric.get("key") for metric in plan.get("virtual_metrics") or []}
            plan["virtual_metrics"] = (plan.get("virtual_metrics") or []) + [
                metric for metric in request.virtual_metrics if metric.get("key") not in existing
            ]
        return await execute_analysis_plan(
            plan=plan,
            user_id=user_id,
            connection_id=request.connection_id,
            persist=False,
        )

    if request.virtual_metrics and request.query:
        if not user_id:
            user_id = user_id_from_authorization(authorization)
        return await execute_analysis_plan(
            plan=_inline_plan(request),
            user_id=user_id,
            connection_id=request.connection_id,
            persist=False,
        )

    payload = request.dict(exclude_none=True)
    for key in ["intent", "virtual_metrics", "required_grain", "explain"]:
        payload.pop(key, None)
    result = await execute_semantic_query(payload, user_id=user_id)
    if request.explain:
        result["compiled_query"] = (result.get("query") or {}).get("compiled")
        result["evidence"] = {
            "row_count": len(result.get("data") or []),
            "sample_rows": (result.get("data") or [])[:20],
        }
        result["warnings"] = []
        result["validation_errors"] = []
    return result
