"""Checks grounded in declared metadata, without industry-specific defaults."""
from services.semantic_graph import metric_source_cubes

SEMANTIC_FIELDS = ("unit", "grain", "aggregation", "non_additive_dimensions")


def declared_semantics(metric):
    metadata = metric.get("metadata") or {}
    return {key: metric.get(key, metadata.get(key)) for key in SEMANTIC_FIELDS
            if metric.get(key, metadata.get(key)) is not None}


def validate_plan_semantics(plan, graph):
    errors = []
    metrics = graph.get("metrics_by_key") or {}
    for comparison in plan.get("virtual_metrics") or []:
        left = metrics.get(comparison.get("left"))
        right = metrics.get(comparison.get("right"))
        if not left or not right:
            errors.append("La comparacion requiere dos metricas publicadas.")
            continue
        if metric_source_cubes(graph, left["key"]) != metric_source_cubes(graph, right["key"]):
            errors.append("La comparacion mezcla fuentes incompatibles.")
        for field in ("unit", "grain"):
            if left.get(field) and right.get(field) and left[field] != right[field]:
                errors.append(f"La comparacion combina {field} diferentes; requiere una conversion o regla validada.")
        left_format, right_format = left.get("format"), right.get("format")
        if left_format and right_format and left_format != right_format:
            errors.append("La comparacion combina formatos distintos; revisa unidad y escala.")
    for step in plan.get("queries") or []:
        query = step.get("query") or {}
        for key in query.get("measures") or []:
            metric = metrics.get(key) or {}
            for dimension in metric.get("non_additive_dimensions") or []:
                retained = dimension in (query.get("dimensions") or [])
                for time in query.get("timeDimensions") or []:
                    if time.get("dimension") != dimension:
                        continue
                    period = time.get("dateRange") or []
                    # A yearly bucket still aggregates monthly snapshots. A
                    # time breakdown is safe only at its declared native grain.
                    retained |= (bool(time.get("granularity")) and time["granularity"] == metric.get("grain")) or (len(period) == 2 and period[0] == period[1])
                if not retained:
                    errors.append(f"{key} no permite agregar sobre {dimension}; precisa el corte o desglose segun su definicion.")
    return errors
