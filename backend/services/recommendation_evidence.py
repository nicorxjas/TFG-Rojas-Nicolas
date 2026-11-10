"""Bind recommendation observations to returned cells, never model-written values."""

import math
import re
from datetime import date, datetime
from typing import Callable


def recommendation_response_schema(facts: list[dict]) -> dict:
    action = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "title": {"type": "string"}, "proposal": {"type": "string"}, "hypothesis": {"type": "string"},
            "fact_ids": {"type": "array", "minItems": 1, "maxItems": 3,
                         "items": {"type": "string", "enum": [fact["id"] for fact in facts]}},
            "monitoring_measures": {"type": "array", "minItems": 1, "maxItems": 3,
                                    "items": {"type": "string", "enum": list(dict.fromkeys(fact["measure"] for fact in facts))}},
        },
        "required": ["title", "proposal", "hypothesis", "fact_ids", "monitoring_measures"],
    }
    return {"type": "json_schema", "json_schema": {"name": "business_recommendations", "strict": True, "schema": {
        "type": "object", "additionalProperties": False,
        "properties": {"actions": {"type": "array", "minItems": 1, "maxItems": 4, "items": action}},
        "required": ["actions"],
    }}}


def _field_metadata(item: dict, member: str) -> dict:
    for key in ("field_metadata", "dimension_metadata", "member_metadata"):
        metadata = item.get(key) or {}
        if isinstance(metadata, dict) and isinstance(metadata.get(member), dict):
            field = metadata[member]
            return {**(field.get("metadata") or {}), **field}
    return {}


def _field_name(metadata: dict, member: str) -> str:
    return metadata.get("business_name") or metadata.get("name") or metadata.get("display_name") or member


def _temporal_field(metadata: dict, value) -> bool:
    """Use declared semantics or a complete date format, never the cube's name."""
    kind = str(metadata.get("field_kind") or metadata.get("kind") or "").lower()
    semantic_type = str(metadata.get("semantic_type") or "").lower()
    if metadata.get("is_temporal") is False or kind == "id" or semantic_type in {"id", "identifier", "code", "entity", "category"}:
        return False
    data_type = str(metadata.get("data_type") or "").lower()
    formatting = str(metadata.get("format") or metadata.get("format_string") or "").lower()
    if (metadata.get("is_temporal") is True or kind in {"time", "temporal"}
            or semantic_type in {"date", "datetime", "time", "period", "year_month"}
            or "date" in data_type or "timestamp" in data_type
            or formatting in {"date", "datetime", "timestamp", "yyyy-mm", "yyyy-mm-dd"}):
        return True
    if isinstance(value, (date, datetime)):
        return True
    if not isinstance(value, str):
        return False
    # A label containing a date remains an entity. Only complete, valid ISO
    # values provide a fallback when the catalog does not declare the kind.
    if re.fullmatch(r"\d{4}-\d{2}", value):
        try:
            date.fromisoformat(value + "-01")
            return True
        except ValueError:
            return False
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?", value):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    return False


def _period_label(value, granularity=None) -> str:
    label = str(value)
    if granularity == "month" and re.match(r"^\d{4}-\d{2}(?:-|$)", label):
        return label[:7]
    if granularity == "year" and re.match(r"^\d{4}(?:-|$)", label):
        return label[:4]
    if granularity == "quarter" and re.match(r"^\d{4}-\d{2}-", label):
        return f"{label[:4]} T{(int(label[5:7]) - 1) // 3 + 1}"
    return label[:10] if re.match(r"^\d{4}-\d{2}-\d{2}(?:[T ]|$)", label) else label


def _coverage_qualification(coverage: dict) -> str | None:
    if coverage.get("period_complete") is not False:
        return None
    note = "La cobertura del período solicitado es incompleta."
    available = coverage.get("available_period")
    if isinstance(available, (list, tuple)) and len(available) == 2:
        note += " Fechas disponibles en la fuente: " + " a ".join(str(value) for value in available) + "."
    reason = coverage.get("incompleteness_reason")
    if reason:
        note += " " + str(reason)
    return note


def recommendation_facts(digest: list[dict]) -> list[dict]:
    facts = []
    for evidence_index, item in enumerate(digest):
        query = item.get("query") or {}
        metadata = item.get("metric_metadata") or {}
        for row_index, row in enumerate(item.get("sample_rows") or []):
            entities, periods, dimensions, times, qualification = [], [], [], [], []
            for member in query.get("dimensions") or []:
                field = _field_metadata(item, member)
                value = row.get(member)
                temporal = _temporal_field(field, value)
                binding = {"member": member, "name": _field_name(field, member),
                           "value": value, "missing": value in (None, ""), "temporal": temporal}
                dimensions.append(binding)
                if binding["missing"]:
                    qualification.append(f"{'Fecha' if temporal else 'Grupo'} sin dato en {binding['name']}; este valor no es un total global.")
                elif temporal:
                    periods.append(_period_label(value))
                else:
                    entities.append(str(value))
            for time in query.get("timeDimensions") or []:
                member = time["dimension"]
                granularity = time.get("granularity")
                returned_member = f"{member}.{granularity}" if granularity and f"{member}.{granularity}" in row else member
                period = row.get(returned_member)
                field = _field_metadata(item, member)
                binding = {"member": member, "returned_member": returned_member,
                           "name": _field_name(field, member), "value": period,
                           "granularity": granularity, "date_range": time.get("dateRange"),
                           "missing": bool(granularity) and period in (None, "")}
                times.append(binding)
                if granularity:
                    if binding["missing"]:
                        qualification.append(f"Fecha sin dato en {binding['name']}; el rango solicitado no identifica la fecha de este grupo.")
                    else:
                        periods.append(_period_label(period, granularity))
                elif time.get("dateRange"):
                    periods.append(" a ".join(str(value) for value in time["dateRange"]))
            # Filters belong to the observation even when not present in the row.
            def filter_labels(filters):
                labels = []
                for node in filters:
                    if "and" in node or "or" in node:
                        operator = "and" if "and" in node else "or"
                        joiner = " y " if operator == "and" else " o "
                        labels.append("(" + joiner.join(filter_labels(node[operator])) + ")")
                    else:
                        values = ", ".join(str(value) for value in node.get("values") or [])
                        labels.append(f"{node.get('operator')}: {values}")
                return labels

            coverage = dict(item.get("coverage") or {})
            coverage_note = _coverage_qualification(coverage)
            if coverage_note:
                qualification.append(coverage_note)
            scope = {"entities": entities, "periods": list(dict.fromkeys(periods)),
                     "filters": filter_labels(query.get("filters") or []),
                     "grouped": bool(dimensions or any(time["granularity"] for time in times)),
                     "dimensions": dimensions, "time_dimensions": times,
                     "qualification": qualification,
                     "coverage": coverage, "warnings": list(item.get("warnings") or [])}
            for measure in query.get("measures") or []:
                value = row.get(measure)
                if value in (None, "") or isinstance(value, bool):
                    continue
                try:
                    if not math.isfinite(float(value)):
                        continue
                except (TypeError, ValueError):
                    continue
                facts.append({
                    "id": f"e{evidence_index}r{row_index}m{len(facts)}",
                    "measure": measure, "name": metadata.get(measure, {}).get("name") or measure,
                    "value": value, "metadata": metadata, "scope": scope,
                    "definition": metadata.get(measure, {}).get("business_formula") or metadata.get(measure, {}).get("description"),
                    "scope_note": "Valor observado en el alcance declarado; no demuestra ranking global, precio unitario ni causalidad. " + " ".join(qualification),
                })
    return facts


def render_recommendations(payload: dict, facts: list[dict], format_value: Callable, *, partial: bool = False) -> str:
    """Reject invented references/figures before publishing any part of the answer."""
    by_id = {fact["id"]: fact for fact in facts}
    metric_names = {fact["measure"]: fact["name"] for fact in facts}
    entity_names = sorted({name for fact in facts for name in fact["scope"]["entities"]}, key=len, reverse=True)
    actions = payload.get("actions") if isinstance(payload, dict) else None
    if not isinstance(actions, list) or not 1 <= len(actions) <= 4:
        raise ValueError("Las recomendaciones requieren acciones acotadas y sustentadas.")
    sections = []
    unverified_periods = False
    missing_periods = False
    evidence_notes = []
    for index, action in enumerate(actions, 1):
        if not isinstance(action, dict):
            raise ValueError("Accion invalida.")
        refs = action.get("fact_ids")
        measures = action.get("monitoring_measures")
        if not isinstance(refs, list) or not 1 <= len(refs) <= 3 or any(not isinstance(ref, str) or ref not in by_id for ref in refs):
            raise ValueError("La accion cita evidencia inexistente.")
        if not isinstance(measures, list) or not 1 <= len(measures) <= 3 or any(not isinstance(key, str) or key not in metric_names for key in measures):
            raise ValueError("La accion requiere metricas no verificadas.")
        for field in ("title", "proposal", "hypothesis"):
            value = action.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 1800:
                raise ValueError("Texto de recomendacion invalido.")
            # Entity names may contain digits (a model number or customer label).
            # All measured figures must be rendered from cells, never from prose.
            without_entities = value
            for name in entity_names:
                without_entities = re.sub(re.escape(name), "", without_entities, flags=re.IGNORECASE)
            if re.search(r"\d|[%$€£]", without_entities):
                raise ValueError("Las cifras deben proceder de referencias a evidencia.")
        observations = []
        for ref in dict.fromkeys(refs):
            fact = by_id[ref]
            scope = fact["scope"]
            dimensions = scope.get("dimensions") or []
            times = scope.get("time_dimensions") or []
            absent_period = (any(binding.get("temporal") and binding.get("missing") for binding in dimensions)
                             or any(binding.get("missing") for binding in times))
            missing_periods = missing_periods or absent_period
            coverage = scope.get("coverage") or {}
            unverified_periods = unverified_periods or (
                bool(scope["periods"] or absent_period) and coverage.get("period_complete") is None)
            subject_parts = [str(binding["value"]) if not binding["missing"] else f"Grupo sin dato ({binding['name']})"
                             for binding in dimensions if not binding.get("temporal")]
            if not dimensions:
                subject_parts = scope["entities"]
            subject = " / ".join(subject_parts)
            if not subject:
                subject = "Grupo temporal" if scope.get("grouped") else "Total consultado"
            period_parts = list(scope["periods"])
            if absent_period:
                period_parts.append("fecha sin dato")
            period = " / ".join(period_parts) or "histórico disponible"
            filters = "; alcance: " + "; ".join(scope["filters"]) if scope["filters"] else ""
            amount = format_value(fact["measure"], fact["value"], fact["metadata"])
            observations.append(f"{subject}: {fact['name']} **{amount}** ({period}{filters}).")
            coverage_note = _coverage_qualification(coverage)
            if coverage_note:
                evidence_notes.append(coverage_note)
            evidence_notes.extend(str(warning) for warning in scope.get("warnings") or [])
        sections.append(
            f"**{index}. {action['title'].strip()}**\n\n"
            + " ".join(observations)
            + f"\n\n{action['proposal'].strip()}\n\n"
            + f"Hipótesis a validar: {action['hypothesis'].strip()}\n\n"
            + "Medir con: " + ", ".join(dict.fromkeys(metric_names[key] for key in measures)) + "."
        )
    notes = []
    if partial:
        notes.append("Parte de las consultas no pudo completarse; estas propuestas usan solamente los resultados disponibles.")
    if missing_periods:
        notes.append("Hay grupos sin fecha; sus valores conservan ese alcance y no representan un total global ni un período identificado.")
    if unverified_periods:
        notes.append("La cobertura completa de los períodos no está verificada; los datos temporales no prueban por sí solos una caída o un crecimiento.")
    notes.extend(dict.fromkeys(evidence_notes))
    return "\n\n".join([*notes, *sections])
