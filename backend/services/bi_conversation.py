"""Explicit, connection-scoped state validated against the current catalog."""
from copy import deepcopy
from services.semantic_filters import validate_filters


def resolve_conversation_state(history, connection_id, graph, fingerprint):
    for message in reversed(history):
        if message.get("role") not in {"assistant", "model"}:
            continue
        state = message.get("semantic_context")
        if not isinstance(state, dict):
            continue
        if connection_id and state.get("connection_id") != connection_id:
            return {}, "connection_changed"
        if state.get("catalog_fingerprint") and state["catalog_fingerprint"] != fingerprint:
            return {}, "catalog_changed"
        allowed = set(graph.get("metric_keys") or []) | set(graph.get("dimension_keys") or []) | set(graph.get("time_keys") or [])
        query = state.get("query") or {}
        if not isinstance(query, dict) or not isinstance(state.get("selected_entities", []), list):
            return {}, "invalid_state"
        if state.get("scope_reset") and not query.get("measures"):
            return {}, "explicit_scope_reset"
        if any(not isinstance(item, dict) for item in state.get("selected_entities") or []):
            return {}, "invalid_state"
        if any(not isinstance(query.get(key, []), list) for key in ("measures", "dimensions", "timeDimensions")) or not isinstance(query.get("order", {}), dict):
            return {}, "invalid_state"
        if any(not isinstance(item, dict) for item in query.get("timeDimensions") or []):
            return {}, "invalid_state"
        referenced = [*(query.get("measures") or []), *(query.get("dimensions") or []),
                      *(query.get("order") or {}).keys(),
                      *[item.get("dimension") for item in query.get("timeDimensions") or []],
                      *[item.get("member") for item in state.get("selected_entities") or []]]
        referenced += [state[key] for key in ("primary_measure", "selection_measure") if state.get(key)]
        if any(not isinstance(key, str) or key not in allowed for key in referenced):
            return {}, "members_changed"
        def require_member(member):
            if member not in allowed:
                raise ValueError("Unknown state member")
        try:
            validate_filters(query.get("filters") or [], require_member)
        except ValueError:
            return {}, "invalid_filters"
        keep = ("query", "primary_measure", "selection_measure", "selected_entities", "metric_names",
                "pending_request", "clarification_kind", "scope_reset")
        return {"version": 3, "connection_id": connection_id, "catalog_fingerprint": fingerprint,
                **{key: deepcopy(state[key]) for key in keep if key in state}}, None
    return {}, None
