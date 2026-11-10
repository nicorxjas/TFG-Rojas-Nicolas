"""Reproducible evaluation of the configured provider; never changes app config.

python backend/evaluation/evaluate_bi.py --output scratch/bi-evaluation.json
Optional --provider/--model explicitly selects a comparison target for this process.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def evaluate_outcome(plan, expected):
    queries = [step["query"] for step in plan.get("queries") or []]
    if expected["outcome"] == "missing":
        return bool(plan.get("missing_metric_request")) and not queries
    if expected["outcome"] == "clarification":
        return bool(plan.get("clarification")) and not queries
    for query in queries:
        if query.get("measures") != expected["measures"]:
            continue
        if "dimensions" in expected and (query.get("dimensions") or []) != expected["dimensions"]:
            continue
        if "filter" in expected and expected["filter"] not in query.get("filters", []):
            continue
        if any(query.get(key, [] if key in {"dimensions", "timeDimensions", "filters"} else None) != expected[key]
               for key in ("timeDimensions", "order", "limit", "filters") if key in expected):
            continue
        return True
    return False


async def evaluate(args):
    from api.llm import get_llm_model, get_llm_provider
    from services.bi_trace import trace_run
    from services.bi_contracts import CONTRACT_VERSION
    from services.semantic_graph import build_semantic_graph
    from services.semantic_planner import _llm_plan, compile_analysis_plan
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    report = {"contract": CONTRACT_VERSION, "provider": get_llm_provider(), "model": get_llm_model(), "compile": args.compile,
              "scope": "Synthetic catalogs, real configured LLM and production harness; no database queries", "cases": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for repeat in range(args.repeats):
        for case in cases:
            metrics = case["metrics"] + [{"key": f"Other.m{i}", "name": f"Conteo {i}", "description": "Registros importados"}
                                          for i in range(case.get("distractors", 0))]
            catalog = {"metrics": metrics, "fields": case.get("fields", []), "relationships": case.get("relationships", [])}
            graph = build_semantic_graph(catalog)
            started = time.monotonic()
            with trace_run("evaluation", {"case_id": case["id"], "repeat": repeat}) as trace:
                context = {"surface": "chat", **case.get("context", {})}
                plan = (await compile_analysis_plan(prompt=case["prompt"], user_id="", semantic_catalog=catalog,
                            metric_catalog=metrics, context=context) if args.compile
                        else await _llm_plan(case["prompt"], graph, context)) or {}
            usage = [event["payload"].get("usage") or {} for event in trace["events"] if event["event"] == "completion"]
            totals = {key: sum(item.get(key, 0) or 0 for item in usage) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
            usage_available = bool(usage) and all(all(key in item for key in totals) for item in usage)
            result = {"id": case["id"], "repeat": repeat, "passed": evaluate_outcome(plan, case["expected"]),
                      "seconds": round(time.monotonic()-started, 2), "expected": case["expected"], "plan": plan,
                      "usage": totals if usage_available else None, "usage_available": usage_available, "trace_id": trace["trace_id"]}
            if usage_available and args.input_per_million is not None and args.output_per_million is not None:
                result["estimated_cost"] = (totals["prompt_tokens"]*args.input_per_million + totals["completion_tokens"]*args.output_per_million)/1_000_000
            report["cases"].append(result)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"id": case["id"], "passed": result["passed"], "seconds": result["seconds"]}), flush=True)
    report["passed"] = sum(case["passed"] for case in report["cases"])
    report["total"] = len(report["cases"])
    report["median_seconds"] = statistics.median(case["seconds"] for case in report["cases"])
    report["unnecessary_clarifications"] = sum(bool(case["plan"].get("clarification")) and case["expected"]["outcome"] == "query" for case in report["cases"])
    report["incorrect_missing_metrics"] = sum(bool(case["plan"].get("missing_metric_request")) and case["expected"]["outcome"] != "missing" for case in report["cases"])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report["passed"] == report["total"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["codex", "ollama", "gemini"])
    parser.add_argument("--model")
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("bi_cases.json"))
    parser.add_argument("--output", type=Path, default=ROOT / "scratch/bi-evaluation.json")
    parser.add_argument("--trace-dir", type=Path, default=ROOT / "scratch/bi-traces")
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--compile", action="store_true", help="Include production compilation and conversation scope resolution")
    parser.add_argument("--input-per-million", type=float)
    parser.add_argument("--output-per-million", type=float)
    args = parser.parse_args()
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model
        os.environ["GEMINI_MODEL"] = args.model
    os.environ["BI_TRACE_DIR"] = str(args.trace_dir)
    try:
        success = asyncio.run(evaluate(args))
    finally:
        from services.codex_llm import server
        server.close()
    sys.exit(0 if success else 1)
