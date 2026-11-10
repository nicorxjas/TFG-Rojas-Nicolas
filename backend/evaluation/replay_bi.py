"""Replay recorded model responses through the current harness without any LLM/data calls."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.bi_runtime import run_planner
from services.semantic_graph import build_semantic_graph
from services.semantic_planner import _compile_raw_plan, extract_date_range_from_text
from services.bi_semantic_validation import validate_plan_semantics


async def replay(path):
    trace = json.loads(path.read_text(encoding="utf-8"))
    events = trace["events"]
    end = next(index for index in range(len(events)-1, -1, -1) if events[index]["event"] == "validated_plan")
    expected = events[end]["payload"]
    events = events[(expected.get("harness") or {}).get("span_start_event", 0):end+1]
    snapshot = next(item["payload"] for item in events if item["event"] == "catalog_snapshot")
    first_input = next(item["payload"] for item in events if item["event"] == "model_input")
    request = json.loads(first_input[1]["content"])
    groups = snapshot["members"]
    catalog = {"metrics": groups["metrics"], "fields": [
        {"semantic_key": field["key"], "business_name": field.get("name"), "description": field.get("description"),
         "field_kind": "time" if kind == "time_dimensions" else "dimension", "data_type": field.get("data_type")}
        for kind in ("dimensions", "time_dimensions") for field in groups[kind]],
        "relationships": [{"from_table": rel["from_cube"], "from_field": rel["from"].split(".", 1)[1],
                           "to_table": rel["to_cube"], "to_field": rel["to"].split(".", 1)[1]}
                          for rel in snapshot["relationships"]]}
    graph = build_semantic_graph(catalog)
    has_text = any(item["event"] == "completion_text" for item in events)
    outputs = iter(item["payload"] for item in events if item["event"] == ("completion_text" if has_text else "model_output"))
    async def recorded(*args, **kwargs):
        try:
            value = next(outputs)
            return json.loads(value) if has_text else value
        except StopIteration:
            raise ValueError("No quedan respuestas grabadas.")
    def validate(plan):
        if not plan.get("queries"):
            return []
        compiled = _compile_raw_plan(plan, graph, request["prompt"], extract_date_range_from_text(request["prompt"]),
                                     allow_time_breakdown=request["context"].get("surface") == "recommendation")
        return [*compiled["validation_errors"], *validate_plan_semantics(plan, graph)]
    result = await run_planner(request["prompt"], graph, request["context"], "Replay", validate, complete=recorded)
    comparable = lambda plan: {key: value for key, value in plan.items() if key != "harness"}
    return {"trace_id": trace["trace_id"], "matches": comparable(result) == comparable(expected), "plan": result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    result = asyncio.run(replay(args.trace))
    print(json.dumps(result, ensure_ascii=True, indent=2))
    sys.exit(0 if result["matches"] else 1)
