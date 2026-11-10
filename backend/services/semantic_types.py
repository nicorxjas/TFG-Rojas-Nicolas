from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class SemanticIntent(BaseModel):
    summary: str = ""
    domains: list[str] = Field(default_factory=list)
    task_type: Optional[str] = None
    required_grain: Optional[str | list[str]] = None


class MetricCandidate(BaseModel):
    key: str
    name: str = ""
    description: str = ""
    reason: str = ""
    confidence: float = 0.0


class VirtualMetric(BaseModel):
    key: str
    name: str
    description: str = ""
    type: Literal["comparison", "math", "ratio", "conditional_count", "flag"] = "comparison"
    operator: Optional[Literal["lt", "lte", "gt", "gte", "eq", "neq"]] = None
    left: Optional[str] = None
    right: Optional[str] = None
    aggregation: Optional[Literal["count_rows", "flag", "sum", "avg"]] = "count_rows"
    dependencies: list[str] = Field(default_factory=list)
    expression: Optional[dict[str, Any] | str] = None


class SemanticQuerySpec(BaseModel):
    id: str = ""
    label: str = "analisis"
    purpose: str = ""
    query: dict[str, Any] = Field(default_factory=dict)
    virtual_metrics: list[str] = Field(default_factory=list)


class AnalysisPlan(BaseModel):
    plan_id: str = ""
    prompt: str = ""
    connection_id: Optional[str] = None
    intent: SemanticIntent | dict[str, Any] = Field(default_factory=SemanticIntent)
    virtual_metrics: list[VirtualMetric | dict[str, Any]] = Field(default_factory=list)
    queries: list[SemanticQuerySpec | dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    generated_at: Optional[str] = None


class EvidencePack(BaseModel):
    evidence_id: str
    label: str = ""
    purpose: str = ""
    query: dict[str, Any] = Field(default_factory=dict)
    compiled_query: Optional[dict[str, Any]] = None
    provider: Optional[str] = None
    row_count: int = 0
    data: list[dict[str, Any]] = Field(default_factory=list)
    virtual_metric_results: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    fingerprint: str = ""


class VerifiedClaim(BaseModel):
    claim: str
    evidence_id: str
    metric_refs: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    status: Literal["verified", "rejected", "insufficient_evidence"] = "verified"


class AgentRunResult(BaseModel):
    agent_id: Optional[str] = None
    agent_name: str = ""
    tools_used: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    claims: list[VerifiedClaim | dict[str, Any]] = Field(default_factory=list)
    narrative: str = ""
    warnings: list[str] = Field(default_factory=list)
