import re
import unicodedata
from collections import deque
from typing import Any


STOP_TOKENS = {
    "a", "al", "de", "del", "el", "en", "la", "las", "los", "por", "para", "con",
    "and", "by", "of", "the", "to", "excel", "dim", "fact", "mensual", "monthly",
    "total", "suma", "sum", "count", "cantidad", "filas", "fecha", "date",
}


def normalize_text(value: Any) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value or ""))
    text = re.sub(r"([A-Za-z])(\d)", r"\1 \2", text)
    text = re.sub(r"(\d)([A-Za-z])", r"\1 \2", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-zA-Z0-9]+", " ", text.lower()).strip()


def tokens_for(value: Any) -> set[str]:
    return {token for token in normalize_text(value).split() if token and token not in STOP_TOKENS}


def cube_from_member(member: Any) -> str | None:
    if not isinstance(member, str) or "." not in member:
        return None
    cube_name = member.split(".", 1)[0]
    return cube_name or None


def _metric_dependencies(metric: dict[str, Any]) -> list[str]:
    deps = metric.get("cube_dependencies") or metric.get("provider_dependencies")
    if deps:
        return [dep for dep in deps if isinstance(dep, str)]
    key = metric.get("key")
    return [key] if isinstance(key, str) else []


def _field_item(field: dict[str, Any], tables_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    metadata = field.get("metadata") or {}
    table = tables_by_id.get(field.get("table_id")) or {}
    table_metadata = table.get("metadata") or {}
    key = field.get("semantic_key")
    display = field.get("business_name") or field.get("suggested_business_name") or field.get("display_name") or field.get("name") or key
    description = field.get("description") or field.get("suggested_description") or ""
    table_label = table.get("business_name") or table.get("display_name") or table_metadata.get("table_name") or table.get("name")
    search_text = " ".join(str(value or "") for value in [
        key,
        display,
        description,
        field.get("name"),
        table_label,
        metadata.get("sheet_name"),
        metadata.get("table_name"),
        " ".join(field.get("aliases") or metadata.get("aliases") or []),
    ])
    return {
        "key": key,
        "name": display,
        "description": description,
        "kind": field.get("field_kind") or "unknown",
        "data_type": field.get("data_type") or metadata.get("data_type") or "unknown",
        "table": table.get("name") or cube_from_member(key),
        "table_label": table_label,
        "tokens": sorted(tokens_for(search_text)),
        "metadata": metadata,
        "aliases": field.get("aliases") or metadata.get("aliases") or [],
    }


def build_semantic_graph(catalog: dict[str, Any], metric_catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    metric_catalog = metric_catalog or []
    tables = catalog.get("tables") or []
    tables_by_id = {table.get("id"): table for table in tables if table.get("id")}

    metrics_by_key: dict[str, dict[str, Any]] = {}
    for metric in catalog.get("metrics") or []:
        key = metric.get("key")
        if not key or metric.get("source") == "aggregate_helper":
            continue
        search_text = " ".join(str(value or "") for value in [
            key,
            metric.get("name"),
            metric.get("description"),
            metric.get("expression"),
            metric.get("business_area"),
            metric.get("business_formula"),
            " ".join(metric.get("aliases") or []),
        ])
        metrics_by_key[key] = {
            "key": key,
            "name": metric.get("name") or key,
            "description": metric.get("description") or "",
            "format": metric.get("format") or "number",
            "source": metric.get("source") or metric.get("provider") or "provider",
            "provider": metric.get("provider"),
            "expression": metric.get("expression"),
            "business_area": metric.get("business_area"),
            "business_formula": metric.get("business_formula") or metric.get("description") or "",
            "aliases": metric.get("aliases") or [],
            "cube_dependencies": _metric_dependencies(metric),
            "tokens": sorted(tokens_for(search_text)),
            **{name: metric.get(name, (metric.get("metadata") or {}).get(name))
               for name in ("unit", "grain", "aggregation", "non_additive_dimensions")
               if metric.get(name, (metric.get("metadata") or {}).get(name)) is not None},
        }
    for metric in metric_catalog:
        key = metric.get("key")
        if not key or key in metrics_by_key or metric.get("source") == "aggregate_helper":
            continue
        search_text = " ".join(str(value or "") for value in [
            key,
            metric.get("name"),
            metric.get("description"),
            metric.get("expression"),
            metric.get("business_area"),
            metric.get("business_formula"),
            " ".join(metric.get("aliases") or []),
        ])
        metrics_by_key[key] = {
            "key": key,
            "name": metric.get("name") or key,
            "description": metric.get("description") or "",
            "format": metric.get("format") or "number",
            "source": metric.get("source") or "custom",
            "provider": metric.get("provider"),
            "expression": metric.get("expression"),
            "business_area": metric.get("business_area"),
            "business_formula": metric.get("business_formula") or metric.get("description") or "",
            "aliases": metric.get("aliases") or [],
            "cube_dependencies": _metric_dependencies(metric),
            "tokens": sorted(tokens_for(search_text)),
            **{name: metric.get(name, (metric.get("metadata") or {}).get(name))
               for name in ("unit", "grain", "aggregation", "non_additive_dimensions")
               if metric.get(name, (metric.get("metadata") or {}).get(name)) is not None},
        }

    dimensions = []
    time_dimensions = []
    fields_by_key = {}
    for field in catalog.get("fields") or []:
        key = field.get("semantic_key")
        if not key or field.get("is_hidden") or not field.get("is_ai_enabled", True):
            continue
        item = _field_item(field, tables_by_id)
        fields_by_key[key] = item
        if item["kind"] == "measure":
            continue
        if item["kind"] == "time":
            time_dimensions.append(item)
        else:
            dimensions.append(item)

    relationships = []
    graph: dict[str, set[str]] = {}
    for relationship in catalog.get("relationships") or []:
        if relationship.get("is_active", True) is False:
            continue
        from_member = ".".join(part for part in [relationship.get("from_table"), relationship.get("from_field")] if part)
        to_member = ".".join(part for part in [relationship.get("to_table"), relationship.get("to_field")] if part)
        from_cube = cube_from_member(from_member)
        to_cube = cube_from_member(to_member)
        if not from_cube or not to_cube:
            continue
        relationships.append({
            "from": from_member,
            "to": to_member,
            "from_cube": from_cube,
            "to_cube": to_cube,
            "active": True,
        })
        graph.setdefault(from_cube, set()).add(to_cube)

    return {
        "metrics": list(metrics_by_key.values()),
        "metrics_by_key": metrics_by_key,
        "dimensions": dimensions,
        "time_dimensions": time_dimensions,
        "fields_by_key": fields_by_key,
        "relationships": relationships,
        "graph": graph,
        "metric_keys": set(metrics_by_key.keys()),
        "dimension_keys": {item["key"] for item in dimensions},
        "time_keys": {item["key"] for item in time_dimensions},
    }


def metric_source_cubes(graph: dict[str, Any], measure_key: str | None) -> set[str]:
    if not measure_key:
        return set()
    metric = graph.get("metrics_by_key", {}).get(measure_key)
    dependencies = (metric or {}).get("cube_dependencies") or [measure_key]
    cubes = {
        cube
        for cube in (cube_from_member(dependency) for dependency in dependencies)
        if cube and cube != "Metricas"
    }
    direct_cube = cube_from_member(measure_key)
    if not cubes and direct_cube and direct_cube != "Metricas":
        cubes.add(direct_cube)
    return cubes


def reachable_cubes(graph: dict[str, Any], source_cube: str | None) -> set[str]:
    if not source_cube:
        return set()
    seen = {source_cube}
    pending = deque([source_cube])
    adjacency = graph.get("graph") or {}
    while pending:
        cube = pending.popleft()
        for neighbor in adjacency.get(cube, set()):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            pending.append(neighbor)
    return seen


def member_compatible(graph: dict[str, Any], source_cube: str | None, member: str | None) -> bool:
    if source_cube and member in graph.get("metrics_by_key", {}):
        sources = metric_source_cubes(graph, member)
        return bool(sources) and sources.issubset(reachable_cubes(graph, source_cube))
    member_cube = cube_from_member(member)
    if not source_cube or not member_cube:
        return True
    return member_cube in reachable_cubes(graph, source_cube)


def measure_compatible(graph: dict[str, Any], source_cube: str | None, measure_key: str | None) -> bool:
    source_cubes = metric_source_cubes(graph, measure_key)
    if not source_cube or not source_cubes:
        return True
    return source_cubes == {source_cube}


def choose_source_cube(
    graph: dict[str, Any],
    measures: list[str],
    dimensions: list[str] | None = None,
    time_dimensions: list[dict[str, Any]] | None = None,
) -> str | None:
    candidates: list[str] = []
    for measure in measures:
        for cube in sorted(metric_source_cubes(graph, measure)):
            if cube not in candidates:
                candidates.append(cube)
    if not candidates:
        return None
    dimensions = dimensions or []
    time_dimensions = time_dimensions or []

    def score(candidate: str) -> tuple[int, int]:
        value = 0
        for measure in measures:
            value += 3 if measure_compatible(graph, candidate, measure) else -3
        for dimension in dimensions:
            value += 1 if member_compatible(graph, candidate, dimension) else -2
        for item in time_dimensions:
            dimension = item.get("dimension") if isinstance(item, dict) else None
            time_cube = cube_from_member(dimension)
            if time_cube == candidate:
                value += 6
            elif member_compatible(graph, candidate, dimension):
                value += 2
            else:
                value -= 4
        return value, -candidates.index(candidate)

    return max(candidates, key=score)


def preferred_time_dimension(graph: dict[str, Any], source_cube: str | None, prompt: str = "") -> str | None:
    fields = graph.get("time_dimensions") or []
    prompt_tokens = tokens_for(prompt)
    compatible = [
        field for field in fields
        if member_compatible(graph, source_cube, field.get("key"))
    ]
    if source_cube:
        same_cube = next((field for field in compatible if str(field.get("key", "")).startswith(f"{source_cube}.")), None)
        if same_cube:
            return same_cube["key"]
    if prompt_tokens:
        ranked = sorted(
            compatible,
            key=lambda field: len(prompt_tokens.intersection(set(field.get("tokens") or []))),
            reverse=True,
        )
        if ranked and len(prompt_tokens.intersection(set(ranked[0].get("tokens") or []))):
            return ranked[0]["key"]
    return compatible[0]["key"] if compatible else (fields[0]["key"] if fields else None)


def rank_items(items: list[dict[str, Any]], prompt: str, *, source_cube: str | None = None, graph: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    prompt_tokens = tokens_for(prompt)

    def score(item: dict[str, Any]) -> tuple[int, int, str]:
        item_tokens = set(item.get("tokens") or [])
        token_score = len(prompt_tokens.intersection(item_tokens)) * 5
        name_score = 1 if normalize_text(item.get("name")) in normalize_text(prompt) else 0
        compatible_score = 0
        if graph is not None and source_cube:
            compatible_score = 2 if member_compatible(graph, source_cube, item.get("key")) else -100
        return token_score + name_score + compatible_score, -len(item_tokens), item.get("key") or ""

    return sorted(items, key=score, reverse=True)
