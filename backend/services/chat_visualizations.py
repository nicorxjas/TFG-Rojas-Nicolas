"""Declarative chat UI built only from executed query results (never LLM values)."""
import math
import re


def build_chat_visualization(query, result, metadata, prompt=""):
    rows = result.get("data") or []
    measures = query.get("measures") or []
    dimensions = query.get("dimensions") or []
    times = [t for t in query.get("timeDimensions", []) if t.get("granularity")]
    # A single grouping keeps each point unambiguous. Large results stay in text.
    if len(dimensions) + len(times) != 1 or not 2 <= len(rows) <= 100 or not measures:
        return None
    if re.search(r"(?:solo|s[oó]lo)\s+(?:texto|tabla)|sin\s+gr[aá]ficos", prompt, re.I):
        return None
    dimension = dimensions[0] if dimensions else times[0]["dimension"]
    time_key = f'{dimension}.{times[0]["granularity"]}' if times else dimension
    points = []
    for row in rows:
        label = row.get(time_key, row.get(dimension))
        if label is None:
            return None
        values = {}
        for index, measure in enumerate(measures):
            raw = row.get(measure)
            if raw is None or isinstance(raw, bool):
                return None
            try:
                value = float(raw)
            except (ValueError, TypeError):
                return None
            if not math.isfinite(value):
                return None
            values[f"m{index}"] = value
        points.append({"label": str(label), "values": values})
    if len({p["label"] for p in points}) != len(points):
        return None
    if times:
        points.sort(key=lambda p: p["label"])
    series = []
    for index, measure in enumerate(measures):
        meta = metadata.get(measure) or {}
        expression = str(meta.get("expression") or "")
        additive = bool(re.fullmatch(r"\s*(?:sum|count)\([^()]+\)\s*", expression, re.I))
        series.append({"key": f"m{index}", "label": meta.get("name") or measure,
                       "format": meta.get("format") if meta.get("format") in {"number", "currency", "percent"} else "number",
                       "additive": additive})
    order = query.get("order") or {}
    primary = next((i for i, m in enumerate(measures) if isinstance(order, dict) and m in order), 0)
    if not times and isinstance(order, dict) and measures[primary] in order:
        points.sort(key=lambda p: p["values"][f"m{primary}"], reverse=str(order[measures[primary]]).lower() == "desc")
    preferred = "line" if times else "horizontal-bar"
    for pattern, kind in [(r"\b(?:torta|pie)\b", "pie"), (r"\b(?:dona|donut)\b", "donut"), (r"\b[aá]rea\b", "area"), (r"\bl[ií]neas?\b", "line"), (r"\bbarras? vertical", "bar")]:
        if re.search(pattern, prompt, re.I):
            preferred = kind
            break
    ranges = [t.get("dateRange") for t in query.get("timeDimensions", []) if t.get("dateRange")]
    scope = f'{len(points)} {"períodos" if times else "categorías"} de la consulta'
    if ranges:
        scope += " · " + (" – ".join(str(value) for value in ranges[0]) if isinstance(ranges[0], list) else str(ranges[0]))
    return {"version": 1, "title": series[primary]["label"], "kind": "temporal" if times else "categorical",
            "preferred": preferred, "primarySeries": f"m{primary}", "series": series, "data": points,
            "scope": scope,
            "source": "Resultado de la consulta al modelo semántico"}
