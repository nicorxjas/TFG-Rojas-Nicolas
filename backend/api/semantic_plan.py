from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from services.semantic_planner import compile_analysis_plan, execute_analysis_plan
from services.supabase_rest import user_id_from_authorization


router = APIRouter(prefix="/semantic-plan", tags=["semantic-plan"])


class CompilePlanRequest(BaseModel):
    prompt: str = ""
    connection_id: Optional[str] = None
    intent: Optional[str | dict[str, Any]] = None
    virtual_metrics: list[dict[str, Any]] = Field(default_factory=list)
    required_grain: Optional[str | list[str]] = None
    context: dict[str, Any] = Field(default_factory=dict)
    use_llm: bool = True


class ExecutePlanRequest(BaseModel):
    prompt: str = ""
    connection_id: Optional[str] = None
    plan: Optional[dict[str, Any]] = None
    intent: Optional[str | dict[str, Any]] = None
    virtual_metrics: list[dict[str, Any]] = Field(default_factory=list)
    required_grain: Optional[str | list[str]] = None
    context: dict[str, Any] = Field(default_factory=dict)
    persist: bool = False


def _planning_prompt(request: CompilePlanRequest | ExecutePlanRequest) -> str:
    if request.prompt.strip():
        return request.prompt.strip()
    if isinstance(request.intent, str) and request.intent.strip():
        return request.intent.strip()
    if isinstance(request.intent, dict):
        summary = request.intent.get("summary") or request.intent.get("description") or request.intent.get("task")
        if summary:
            return str(summary)
    raise HTTPException(status_code=422, detail="El planner requiere prompt o intent.")


@router.post("/compile")
async def compile_semantic_plan(
    request: CompilePlanRequest,
    authorization: str = Header(...),
):
    user_id = user_id_from_authorization(authorization)
    context = dict(request.context or {})
    if request.intent is not None:
        context["intent"] = request.intent
    if request.required_grain is not None:
        context["required_grain"] = request.required_grain
    plan = await compile_analysis_plan(
        prompt=_planning_prompt(request),
        user_id=user_id,
        connection_id=request.connection_id,
        context=context,
        use_llm=request.use_llm,
    )
    if request.virtual_metrics:
        existing = {metric.get("key") for metric in plan.get("virtual_metrics") or []}
        plan["virtual_metrics"] = (plan.get("virtual_metrics") or []) + [
            metric for metric in request.virtual_metrics if metric.get("key") not in existing
        ]
    return plan


@router.post("/execute")
async def execute_semantic_plan(
    request: ExecutePlanRequest,
    authorization: str = Header(...),
):
    user_id = user_id_from_authorization(authorization)
    if request.plan:
        plan = request.plan
    else:
        context = dict(request.context or {})
        if request.intent is not None:
            context["intent"] = request.intent
        if request.required_grain is not None:
            context["required_grain"] = request.required_grain
        plan = await compile_analysis_plan(
            prompt=_planning_prompt(request),
            user_id=user_id,
            connection_id=request.connection_id,
            context=context,
            use_llm=True,
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
        persist=request.persist,
    )
