"""Provider-independent contracts at the BI inference boundary."""
from datetime import date
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = "bi-harness/1"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatIntent(Contract):
    mode: Literal["guidance", "recommendation", "data", "artifact", "general"]
    needs_data: bool = False
    reason: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def derive_data_requirement(self):
        self.needs_data = self.mode in {"data", "recommendation"}
        return self


class TimeScope(Contract):
    dimension: str
    granularity: Literal["day", "week", "month", "quarter", "year"] | None = None
    dateRange: list[str] | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.dateRange is not None:
            if len(self.dateRange) != 2:
                raise ValueError("El periodo requiere inicio y fin ISO.")
            start, end = [date.fromisoformat(value) for value in self.dateRange]
            if start > end:
                raise ValueError("La fecha inicial es posterior a la final.")
        return self


class Query(Contract):
    measures: list[str] = Field(min_length=1, max_length=6)
    dimensions: list[str] = Field(default_factory=list, max_length=6)
    timeDimensions: list[TimeScope] = Field(default_factory=list, max_length=4)
    filters: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    order: dict[str, Literal["asc", "desc"]] = Field(default_factory=dict)
    limit: int = Field(default=100, ge=1, le=10000, strict=True)

    @model_validator(mode="after")
    def canonical_filters(self):
        from services.semantic_filters import validate_filters
        validate_filters(self.filters, lambda member: None)
        def canonical(nodes):
            result = []
            for node in nodes:
                group = next((key for key in ("and", "or") if key in node), None)
                if group:
                    result.append({group: canonical(node[group])})
                    continue
                names = [node[key] for key in ("member", "dimension", "measure") if key in node]
                if len(set(names)) != 1 or set(node) - {"member", "dimension", "measure", "operator", "values"}:
                    raise ValueError("El filtro debe tener un unico miembro y propiedades conocidas.")
                result.append({"member": names[0], "operator": node["operator"],
                               **({"values": node["values"]} if "values" in node else {})})
            return result
        self.filters = canonical(self.filters)
        return self


class QueryStep(Contract):
    id: str = ""
    label: str = "Consulta"
    purpose: str = ""
    query: Query
    virtual_metrics: list[str] = Field(default_factory=list)


class PlanIntent(Contract):
    summary: str = ""
    domains: list[str] = Field(default_factory=list)
    task_type: str | None = None
    required_grain: str | list[str] | None = None


class Comparison(Contract):
    key: str
    name: str = "Comparacion"
    description: str = ""
    type: Literal["comparison"] = "comparison"
    left: str
    operator: Literal["lt", "lte", "gt", "gte", "eq", "neq"]
    right: str
    aggregation: Literal["count_rows"] = "count_rows"


class Plan(Contract):
    intent: PlanIntent = Field(default_factory=PlanIntent)
    queries: list[QueryStep] = Field(default_factory=list, max_length=4)
    virtual_metrics: list[Comparison] = Field(default_factory=list, max_length=4)
    warnings: list[str] = Field(default_factory=list)
    clarification: str | None = None
    missing_metric_request: str | None = None

    @model_validator(mode="after")
    def exclusive_outcome(self):
        if sum([bool(self.queries), bool(self.clarification), bool(self.missing_metric_request)]) != 1:
            raise ValueError("Elegir un unico resultado: consultas, aclaracion o metrica faltante.")
        if self.virtual_metrics and not self.queries:
            raise ValueError("Una metrica virtual requiere consultas verificables.")
        return self


class CatalogAction(Contract):
    tool: Literal["search_catalog", "get_members", "get_relationships"]
    text: str = Field(default="", max_length=1000)
    kind: Literal["all", "metrics", "dimensions", "time_dimensions"] = "all"
    keys: list[str] = Field(default_factory=list, max_length=20)
    source: str | None = None
    offset: int = Field(default=0, ge=0, le=100000, strict=True)


class MetricResolution(Contract):
    status: Literal["existing", "missing", "not_metric", "insufficient"]
    existing_metric_key: str | None = None
    name: str | None = None
    description: str | None = None
    expression: str | None = None
    format: str | None = None
    proposed_calculation: str | None = None
    missing_components: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


def validation_feedback(error: Exception) -> list[str]:
    """Send only validation locations/messages back, never raw exception inputs."""
    if hasattr(error, "errors"):
        return [f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors()[:8]]
    return [str(error)[:1000]]
