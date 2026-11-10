import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError

from services.bi_catalog_tools import CatalogTools
from services.bi_contracts import Plan, ChatIntent
from services.bi_conversation import resolve_conversation_state
from services.bi_runtime import run_planner, provider_capabilities
from services.bi_semantic_validation import validate_plan_semantics
from services.bi_trace import trace_run, record
from services.semantic_graph import build_semantic_graph
from services.semantic_planner import _compile_raw_plan


def fixture():
    return build_semantic_graph({"metrics": [
        {"key": "Operations.a", "name": "Disponibilidad", "description": "Horas disponibles", "unit": "hours", "grain": "day"},
        {"key": "Operations.b", "name": "Duracion objetivo", "unit": "hours", "grain": "day"},
        {"key": "Operations.money", "name": "Importe", "unit": "EUR", "grain": "day"},
    ], "fields": [{"semantic_key": "Operations.region", "field_kind": "dimension", "business_name": "Region"},
                   {"semantic_key": "Operations.day", "field_kind": "time", "business_name": "Dia"}]})


def plan_for(key="Operations.a"):
    return {"queries": [{"query": {"measures": [key]}}]}


class ContractTests(unittest.TestCase):
    def test_filter_dialects_normalize_without_changing_boolean_meaning(self):
        raw = plan_for()
        raw["queries"][0]["query"]["filters"] = [{"or": [
            {"dimension": "Operations.region", "operator": "equals", "values": ["Sur"]},
            {"member": "Operations.region", "operator": "equals", "values": ["Norte"]}]}]
        query = Plan.model_validate(raw).queries[0].query
        self.assertEqual(query.filters[0]["or"][0]["member"], "Operations.region")
        self.assertNotIn("dimension", query.filters[0]["or"][0])

    def test_rejects_contradictory_and_unbounded_plans(self):
        for raw in [
            {**plan_for(), "missing_metric_request": "something"},
            {"queries": [{"query": {"measures": ["Operations.a"], "limit": 10001}}]},
            {"queries": [{"query": {"measures": ["Operations.a"], "limit": "100"}}]},
            {"queries": [{"query": {"measures": ["Operations.a"], "sql": "select 1"}}]},
            {"queries": [{"query": {"measures": ["Operations.a"], "timeDimensions": [
                {"dimension": "Operations.day", "dateRange": ["2026-02-30", "2026-03-01"]}]}}]},
        ]:
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                Plan.model_validate(raw)

    def test_intent_derives_data_requirement(self):
        self.assertTrue(ChatIntent(mode="recommendation", needs_data=False).needs_data)

    def test_catalog_search_reaches_members_beyond_initial_window(self):
        graph = build_semantic_graph({"metrics": [
            {"key": f"Model.m{i}", "name": f"Indice {i}", "description": "Horas disponibles"} for i in range(200)
        ] + [{"key": "Model.tail", "name": "Continuidad", "aliases": ["permanencia"], "description": "Cohorte reinscrita"}]})
        tools = CatalogTools(graph)
        self.assertLess(len(tools.seed("horas")["metrics"]), 201)
        found = tools.execute({"tool": "search_catalog", "text": "permanencia", "kind": "metrics"})
        self.assertEqual(found["items"][0]["key"], "Model.tail")
        self.assertEqual(tools.execute({"tool": "search_catalog", "kind": "metrics", "offset": 200})["total_matches"], 201)
        with self.assertRaises(ValueError):
            tools.execute({"tool": "get_members", "keys": ["Other.secret"]})

    def test_dimension_alias_is_available_to_discovery(self):
        graph = build_semantic_graph({"fields": [{"semantic_key": "Model.location", "field_kind": "dimension",
                                                  "business_name": "Ubicacion", "aliases": ["sucursal"]}]})
        self.assertEqual(CatalogTools(graph).search("sucursal")["items"][0]["key"], "Model.location")

    def test_units_and_nonadditive_scope_are_validated_from_metadata(self):
        graph = fixture()
        comparison = {"virtual_metrics": [{"left": "Operations.a", "right": "Operations.money"}]}
        self.assertTrue(validate_plan_semantics(comparison, graph))
        graph["metrics_by_key"]["Operations.a"]["non_additive_dimensions"] = ["Operations.day"]
        self.assertTrue(validate_plan_semantics(plan_for(), graph))
        raw = plan_for()
        raw["queries"][0]["query"]["timeDimensions"] = [{"dimension": "Operations.day", "dateRange": ["2026-01-01", "2026-01-01"]}]
        self.assertEqual(validate_plan_semantics(raw, graph), [])
        raw["queries"][0]["query"]["timeDimensions"] = [{"dimension": "Operations.day", "granularity": "year"}]
        self.assertTrue(validate_plan_semantics(raw, graph))
        raw["queries"][0]["query"]["timeDimensions"][0]["granularity"] = "day"
        self.assertEqual(validate_plan_semantics(raw, graph), [])

    def test_state_is_scoped_and_preserved_beyond_last_six_messages(self):
        graph = fixture()
        fingerprint = CatalogTools(graph).fingerprint
        history = [{"role": "assistant", "semantic_context": {"connection_id": "c", "query": {"measures": ["Operations.a"]},
                    "selected_entities": [{"member": "Operations.region", "value": "Sur"}]}}]
        history += [{"role": "user", "content": "explicacion"}] * 8
        state, reason = resolve_conversation_state(history, "c", graph, fingerprint)
        self.assertIsNone(reason)
        self.assertEqual(state["selected_entities"][0]["value"], "Sur")
        self.assertEqual(resolve_conversation_state(history, "other", graph, fingerprint)[1], "connection_changed")
        history[0]["semantic_context"]["catalog_fingerprint"] = "old"
        self.assertEqual(resolve_conversation_state(history, "c", graph, fingerprint)[1], "catalog_changed")

    def test_trace_is_replayable_and_excludes_credentials(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"BI_TRACE_DIR": folder}):
            with trace_run("test", {"prompt": "hello", "authorization": "secret", "user_id": "owner"}):
                record("plan", plan_for())
            snapshot = json.loads(next(Path(folder).glob("*.json")).read_text(encoding="utf-8"))
        self.assertNotIn("authorization", snapshot["request"])
        self.assertNotIn("user_id", snapshot["request"])
        self.assertEqual(snapshot["events"][0]["payload"], plan_for())
        self.assertIn("snapshot_sha256", snapshot)


class HarnessExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_replay_selects_last_planner_span_in_a_chat_trace(self):
        from evaluation.replay_bi import replay
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"BI_TRACE_DIR": folder}):
            with trace_run("chat", {"prompt": "two plans"}):
                await run_planner("Disponibilidad", fixture(), {}, "plan", lambda p: [], complete=AsyncMock(return_value=plan_for()))
                await run_planner("Duracion objetivo", fixture(), {}, "plan", lambda p: [], complete=AsyncMock(return_value=plan_for("Operations.b")))
            path = next(Path(folder).glob("*.json"))
            result = await replay(path)
        self.assertTrue(result["matches"])
        self.assertEqual(result["plan"]["queries"][0]["query"]["measures"], ["Operations.b"])

    async def test_discovery_and_repair_before_plan_can_exit(self):
        graph = fixture()
        complete = AsyncMock(side_effect=[
            {"action": {"tool": "get_members", "keys": ["Operations.a"]}},
            plan_for("Unknown.fake"), plan_for(),
        ])
        validate = lambda raw: _compile_raw_plan(raw, graph, "Disponibilidad", None)["validation_errors"]
        result = await run_planner("Disponibilidad", graph, {}, "plan", validate, complete=complete)
        self.assertEqual(result["queries"][0]["query"]["measures"], ["Operations.a"])
        self.assertEqual(result["harness"]["tool_calls"], 1)
        self.assertEqual(result["harness"]["repairs"], 1)
        last_messages = complete.call_args.args[0]
        self.assertTrue(any("validation_errors" in item["content"] for item in last_messages))

    async def test_malformed_output_stops_without_creating_metric(self):
        complete = AsyncMock(return_value={"queries": "garbage"})
        result = await run_planner("x", fixture(), {}, "plan", lambda p: [], complete=complete, max_repairs=1)
        self.assertEqual(complete.await_count, 2)
        self.assertEqual(result["queries"], [])
        self.assertTrue(result["clarification"])
        self.assertNotIn("missing_metric_request", result)

    async def test_outage_and_timeout_do_not_become_missing_metric(self):
        async def slow(*args, **kwargs):
            await asyncio.sleep(1)
        for complete in [AsyncMock(side_effect=RuntimeError("offline")), slow]:
            result = await run_planner("x", fixture(), {}, "plan", lambda p: [], complete=complete, timeout=0.02)
            self.assertEqual(result["queries"], [])
            self.assertNotIn("missing_metric_request", result)

    async def test_existing_metric_cannot_be_reported_missing(self):
        complete = AsyncMock(side_effect=[{"missing_metric_request": "Disponibilidad"}, plan_for()])
        result = await run_planner("Disponibilidad", fixture(), {}, "plan", lambda p: [], complete=complete)
        self.assertTrue(result["queries"])
        self.assertEqual(result["harness"]["repairs"], 1)

    async def test_discovery_cannot_invoke_execution_or_write_tools(self):
        complete = AsyncMock(return_value={"action": {"tool": "execute_sql", "text": "DROP TABLE x"}})
        result = await run_planner("x", fixture(), {}, "plan", lambda p: [], complete=complete, max_repairs=0)
        self.assertFalse(result["queries"])
        self.assertEqual(result["harness"]["tool_calls"], 0)

    async def test_provider_selection_does_not_change_harness_contract(self):
        for provider in ["codex", "ollama", "gemini"]:
            with patch.dict(os.environ, {"LLM_PROVIDER": provider, "LLM_MODEL": "configured-test-model", "GEMINI_MODEL": "configured-test-model"}):
                result = await run_planner("x", fixture(), {}, "plan", lambda p: [], complete=AsyncMock(return_value=plan_for()))
                self.assertEqual(result["harness"]["capabilities"]["model"], "configured-test-model")
                self.assertFalse(provider_capabilities()["native_tool_calls_required"])
