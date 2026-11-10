"""Read-only discovery of the already authorized, approved semantic graph."""
import hashlib
import json
from services.bi_contracts import CatalogAction
from services.semantic_graph import normalize_text, tokens_for, metric_source_cubes, member_compatible

MEMBER_FIELDS = ("key", "name", "description", "business_formula", "expression", "aliases",
                 "format", "unit", "grain", "aggregation", "non_additive_dimensions",
                 "cube_dependencies", "kind", "data_type", "table_label")


def member_metadata(item):
    return {key: item[key] for key in MEMBER_FIELDS if item.get(key) not in (None, "", [])}


class CatalogTools:
    PAGE_SIZE = 20

    def __init__(self, graph):
        self.graph = graph
        self.groups = {kind: [member_metadata(item) for item in graph.get(kind) or []]
                       for kind in ("metrics", "dimensions", "time_dimensions")}
        self.members = {item["key"]: item for group in self.groups.values() for item in group}
        self.fingerprint = hashlib.sha256(json.dumps({
            "members": sorted(self.members.values(), key=lambda item: item["key"]),
            "relationships": graph.get("relationships") or [],
        }, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

    def search(self, text="", kind="all", offset=0):
        items = list(self.members.values()) if kind == "all" else self.groups[kind]
        words = tokens_for(text)
        phrase = normalize_text(text)
        scored = []
        for item in items:
            identities = [item.get("name", ""), item["key"], *(item.get("aliases") or [])]
            haystack = json.dumps(item, ensure_ascii=False)
            score = len(words & tokens_for(haystack))
            if phrase and any(normalize_text(name) == phrase for name in identities):
                score += 100
            if not words or score:
                scored.append((score, item))
        scored.sort(key=lambda row: (-row[0], row[1]["key"]))
        return {"items": [item for _, item in scored[offset:offset+self.PAGE_SIZE]],
                "total_matches": len(scored), "offset": offset,
                "next_offset": offset+self.PAGE_SIZE if offset+self.PAGE_SIZE < len(scored) else None,
                "search_note": "Coincidencias de metadatos; ausencia de coincidencias no prueba ausencia del concepto."}

    def execute(self, raw):
        action = CatalogAction.model_validate(raw)
        if action.tool == "search_catalog":
            return self.search(action.text, action.kind, action.offset)
        if action.tool == "get_members":
            unknown = [key for key in action.keys if key not in self.members]
            if unknown:
                raise ValueError(f"Miembros no publicados: {', '.join(unknown)}")
            return {"items": [self.members[key] for key in action.keys]}
        relationships = [rel for rel in self.graph.get("relationships") or []
                         if not action.source or action.source in (rel.get("from_cube"), rel.get("to_cube"))]
        offset = action.offset
        return {"items": relationships[offset:offset+self.PAGE_SIZE], "total_matches": len(relationships),
                "next_offset": offset+self.PAGE_SIZE if offset+self.PAGE_SIZE < len(relationships) else None}

    def seed(self, prompt, state=None):
        ranked = self.search(prompt, "metrics")
        # Small catalogs are inexpensive to expose completely. Large ones are
        # searchable/paginated; they never become a silently truncated catalog.
        metrics = self.groups["metrics"] if len(self.groups["metrics"]) <= 20 else ranked["items"][:12]
        state_keys = set((state or {}).get("query", {}).get("measures") or [])
        metrics = list({item["key"]: item for item in [*metrics, *[
            self.members[key] for key in state_keys if key in self.members]]}.values())
        sources = {source for item in metrics for source in metric_source_cubes(self.graph, item["key"])}
        dimensions = [item for item in self.groups["dimensions"] if not sources or any(
            member_compatible(self.graph, source, item["key"]) for source in sources)]
        times = [item for item in self.groups["time_dimensions"] if not sources or any(
            member_compatible(self.graph, source, item["key"]) for source in sources)]
        return {"fingerprint": self.fingerprint, "counts": {key: len(value) for key, value in self.groups.items()},
                "metrics": metrics, "dimensions": dimensions[:20], "timeDimensions": times[:10],
                "relationships": (self.graph.get("relationships") or [])[:20],
                "discovery_required": len(metrics) < len(self.groups["metrics"]),
                "note": "Vista inicial. Usa las herramientas para explorar los miembros restantes y leer sus definiciones."}
