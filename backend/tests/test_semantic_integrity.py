import asyncio
import json
import unittest
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import duckdb
import httpx
from fastapi import HTTPException

from api.chat import (
    ChatRequest, _format_metric_value, build_semantic_conversation_context,
    chat_with_data, classify_chat_intent, format_planner_quick_answer,
    format_grouped_metric_answer,
)
from api.cube import post_process_cube_response, process_computed_metrics
from api.semantic_metrics import evaluate_compiled_expression
from services.semantic_filters import validate_filters
from services.semantic_planner import (
    _apply_virtual_metrics, _sanitize_query, compile_analysis_plan, execute_analysis_plan,
    extract_date_range_from_text, _enforce_deterministic_intent,
)
from services.semantic_query_engine import execute_cube_semantic_query, validate_query_against_catalog
from test_semantic_metric_routing import semantic_fixture, CUSTOM_KEY, CLIENT_KEY, AMOUNT_KEY, COUNT_KEY


class SemanticIntegrityTests(unittest.TestCase):
    def plan(self, prompt, *, history=None, raw_plan=None, connection_id=None):
        catalog, metrics, _ = semantic_fixture()
        with patch("services.semantic_planner._llm_plan", new=AsyncMock(return_value=raw_plan)):
            return asyncio.run(compile_analysis_plan(
                prompt=prompt, user_id="", connection_id=connection_id,
                semantic_catalog=catalog, metric_catalog=metrics,
                context={"conversation_history": history or []}, use_llm=raw_plan is not None,
            ))

    def history(self, connection_id=None):
        query = {"measures": [CUSTOM_KEY, AMOUNT_KEY], "dimensions": [CLIENT_KEY],
                 "order": {AMOUNT_KEY: "desc"}, "limit": 1,
                 "timeDimensions": [{"dimension": "FactVentas.fecha", "dateRange": ["2025-01-01", "2025-12-31"]}]}
        return [{"role": "assistant", "content": "Para esa entidad, son 3 días.",
                 "semantic_context": build_semantic_conversation_context(
                     query, {"data": [{CLIENT_KEY: "Entidad A", CUSTOM_KEY: 3, AMOUNT_KEY: 100}]},
                     connection_id=connection_id)}]

    def test_best_requires_a_business_criterion(self):
        plan = self.plan("Cuál es el tiempo entre venta y venta para mi mejor cliente?")
        self.assertEqual(plan["queries"], [])
        self.assertIn("criterio", plan["clarification"])

    def test_criterion_clarification_continues_the_original_question(self):
        initial = "Cuál es el tiempo entre venta y venta para mi mejor cliente?"
        pending = self.plan(initial)
        history = [{"role": "assistant", "content": pending["clarification"], "semantic_context": {
            "pending_request": initial, "clarification_kind": pending["clarification_kind"],
        }}]
        query = self.plan("Por Monto Total de Venta", history=history)["queries"][0]["query"]
        self.assertEqual(query["measures"], [CUSTOM_KEY, AMOUNT_KEY])
        self.assertEqual(query["dimensions"], [CLIENT_KEY])
        self.assertEqual(query["order"], {AMOUNT_KEY: "desc"})
        self.assertEqual(query["limit"], 1)

    def test_pending_criterion_does_not_capture_an_unrelated_request(self):
        history = [{"role": "assistant", "semantic_context": {
            "pending_request": "Tiempo promedio entre ventas de mi mejor cliente?",
            "clarification_kind": "selection_criterion",
        }}]
        query = self.plan("Mostrame la Cantidad de Ventas", history=history)["queries"][0]["query"]
        self.assertEqual(query["measures"], [COUNT_KEY])
        self.assertNotIn("dimensions", query)

    def test_unknown_referent_never_becomes_global_total(self):
        plan = self.plan("Decime el tiempo promedio entre ventas para ese cliente")
        self.assertEqual(plan["queries"], [])
        self.assertTrue(plan["clarification"])

    def test_structured_primary_metric_and_period_survive_paraphrase(self):
        query = self.plan("Y para ese cliente?", history=self.history())["queries"][0]["query"]
        self.assertEqual(query["measures"], [CUSTOM_KEY])
        self.assertEqual(query["filters"][0]["values"], ["Entidad A"])
        self.assertEqual(query["timeDimensions"][0]["dateRange"], ["2025-01-01", "2025-12-31"])
        self.assertNotIn("granularity", query["timeDimensions"][0])

    def test_explicit_metric_change_beats_previous_primary(self):
        query = self.plan("Y el Monto Total de Venta para ese cliente?", history=self.history())["queries"][0]["query"]
        self.assertEqual(query["measures"], [AMOUNT_KEY])

    def test_context_cannot_cross_connections(self):
        plan = self.plan("Y para ese cliente?", history=self.history("old"), connection_id="new")
        self.assertEqual(plan["queries"], [])

    def test_user_role_cannot_set_semantic_context(self):
        history = self.history()
        history[0]["role"] = "user"
        self.assertEqual(self.plan("Y para ese cliente?", history=history)["queries"], [])

    def test_ambiguous_entity_values_require_clarification(self):
        history = self.history()
        history[0]["semantic_context"]["selected_entities"].append({"member": CLIENT_KEY, "value": "Entidad B"})
        self.assertEqual(self.plan("Y para ese cliente?", history=history)["queries"], [])

    def test_weekly_follow_up_preserves_scope_and_granularity(self):
        query = self.plan("Y por semana para ese cliente?", history=self.history())["queries"][0]["query"]
        self.assertEqual(query["timeDimensions"][0]["granularity"], "week")
        self.assertIn("dateRange", query["timeDimensions"][0])
        self.assertNotIn("dimensions", query)

    def test_year_is_a_period_not_an_implicit_monthly_breakdown(self):
        query = self.plan("Tiempo promedio entre ventas en el año 2025")["queries"][0]["query"]
        self.assertFalse(any(item.get("granularity") for item in query.get("timeDimensions", [])))

    def test_context_works_with_unrelated_models_and_opaque_keys(self):
        for noun in ["sucursal", "máquina", "paciente"]:
            with self.subTest(noun=noun):
                catalog = {"tables": [{"id": "t", "name": "Opaque"}], "fields": [{
                    "table_id": "t", "semantic_key": "Opaque.x7", "business_name": noun,
                    "field_kind": "dimension",
                }], "metrics": [{"key": "Opaque.m9", "name": "Demora media", "format": "duration_hours"}]}
                history = [{"role": "assistant", "content": "El resultado está disponible.", "semantic_context": {
                    "primary_measure": "Opaque.m9", "selected_entities": [{"member": "Opaque.x7", "value": "A-17"}],
                }}]
                plan = asyncio.run(compile_analysis_plan(
                    prompt=f"Y para ese {noun}?", user_id="", semantic_catalog=catalog,
                    metric_catalog=catalog["metrics"], context={"conversation_history": history}, use_llm=False,
                ))
                query = plan["queries"][0]["query"]
                self.assertEqual(query["measures"], ["Opaque.m9"])
                self.assertEqual(query["filters"], [{"member": "Opaque.x7", "operator": "equals", "values": ["A-17"]}])
                self.assertNotIn("dimensions", query)

    def test_invalid_filter_does_not_get_dropped_or_replaced_by_fallback(self):
        raw = {"queries": [{"query": {"measures": [CUSTOM_KEY], "filters": [
            {"member": "Unknown.customer", "operator": "equals", "values": ["A"]},
        ]}}]}
        plan = self.plan("Tiempo promedio entre ventas", raw_plan=raw)
        self.assertEqual(plan["queries"], [])
        self.assertTrue(plan["validation_errors"])

    def test_recursive_filters_preserve_boolean_meaning(self):
        _, _, graph = semantic_fixture()
        filters = [{"or": [{"member": CLIENT_KEY, "operator": "equals", "values": ["A"]},
                            {"member": CLIENT_KEY, "operator": "equals", "values": ["B"]}]}]
        query, errors = _sanitize_query({"measures": [AMOUNT_KEY], "filters": filters}, graph, "Monto Total de Venta", None)
        self.assertEqual(errors, [])
        self.assertEqual(query["filters"], filters)
        filters[0]["or"][1]["member"] = "Unknown.field"
        query, errors = _sanitize_query({"measures": [AMOUNT_KEY], "filters": filters}, graph, "Monto Total de Venta", None)
        self.assertIsNone(query)
        self.assertTrue(errors)

    def test_filter_shapes_fail_closed(self):
        for filters in [[{}], [{"and": []}], [{"or": [], "member": CLIENT_KEY}],
                        [{"member": CLIENT_KEY, "operator": "equals", "values": "A"}],
                        [{"member": CLIENT_KEY, "operator": "madeUp", "values": ["A"]}]]:
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                validate_filters(filters, lambda member: None)

    def test_execution_validates_nested_members_before_cube(self):
        catalog, metrics, _ = semantic_fixture()
        with self.assertRaises(HTTPException):
            asyncio.run(validate_query_against_catalog(
                {"measures": [AMOUNT_KEY], "filters": [{"or": [{"member": "Other.secret", "operator": "equals", "values": ["x"]}]}]},
                user_id="u", connection_id="c", metric_catalog=metrics, semantic_catalog=catalog,
            ))

    def test_no_execution_when_plan_has_validation_errors(self):
        with patch("services.semantic_planner.execute_semantic_query", new=AsyncMock()) as execute:
            result = asyncio.run(execute_analysis_plan(
                plan={"queries": [{"query": {"measures": [AMOUNT_KEY]}}], "validation_errors": ["invalid filter"]}, user_id="u",
            ))
        execute.assert_not_awaited()
        self.assertEqual(result["evidence"], [])

    def test_time_series_keeps_every_period(self):
        rows = [{"F.date.month": "2025-01-01", "F.value": 10}, {"F.date.month": "2025-02-01", "F.value": 20}]
        actual, summary = _apply_virtual_metrics(rows, [], {"timeDimensions": [{"dimension": "F.date", "granularity": "month"}]})
        self.assertEqual(actual, rows)
        self.assertEqual(summary, {})
        self.assertIsNone(format_planner_quick_answer("por mes", {"evidence": [{
            "query": {"measures": ["F.value"], "timeDimensions": [{"dimension": "F.date", "granularity": "month"}]}, "data": rows,
        }]}))

    def test_undefined_calculations_are_not_zero(self):
        variables = {"a": "F.a", "b": "F.b"}
        for row in [{"F.a": 5, "F.b": 0}, {"F.a": None, "F.b": 1}, {"F.b": 1}, {"F.a": "NaN", "F.b": 1}]:
            with self.subTest(row=row):
                self.assertIsNone(evaluate_compiled_expression("a / b", variables, row))
        self.assertEqual(evaluate_compiled_expression("a / b", variables, {"F.a": 0, "F.b": 2}), 0)
        self.assertEqual(_format_metric_value("anything", None), "sin datos suficientes")

    def test_duckdb_interval_matches_published_formula_including_single_event(self):
        # The engine evaluates only the published formula, using aggregate evidence.
        with duckdb.connect(":memory:") as db:
            rows = db.execute("""SELECT entity, min(day)::VARCHAR, max(day)::VARCHAR, count(*)
                FROM (VALUES ('A', DATE '2025-01-01'), ('A', DATE '2025-01-04'),
                             ('A', DATE '2025-01-07'), ('B', DATE '2025-01-01')) AS events(entity, day)
                GROUP BY entity ORDER BY entity""").fetchall()
        values = {}
        for entity, first, last, count in rows:
            values[entity] = evaluate_compiled_expression("date_diff('day', last, first) / (n - 1)",
                {"last": "E.last", "first": "E.first", "n": "E.count"},
                {"E.last": last, "E.first": first, "E.count": count})
        self.assertEqual(values, {"A": 3.0, "B": None})

    def test_custom_metrics_can_depend_on_other_published_custom_metrics(self):
        catalog = [
            {"key": "Metricas.base", "source": "custom", "cube_dependencies": ["F.a", "F.b"],
             "compiled_expression": "a / b", "variables": {"a": "F.a", "b": "F.b"}},
            {"key": "Metricas.derived", "source": "custom", "cube_dependencies": ["F.a", "F.b"],
             "compiled_expression": "x * 2", "variables": {"x": "Metricas.base"}},
        ]
        query, measures, info = process_computed_metrics({"measures": ["Metricas.derived"]}, catalog)
        self.assertEqual(set(query["measures"]), {"F.a", "F.b"})
        result = post_process_cube_response({"data": [{"F.a": 8, "F.b": 2}]}, measures, info)
        self.assertEqual(result["data"], [{"Metricas.derived": 8}])

    def test_truncated_custom_ranking_is_not_reported_as_global_winner(self):
        response = httpx.Response(200, json={"data": [{"F.value": i} for i in range(3)]}, request=httpx.Request("GET", "http://cube/load"))
        async def run():
            with patch("services.semantic_query_engine.MAX_POWERBI_LIMIT", 3), patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
                return await execute_cube_semantic_query(
                    {"measures": ["Metricas.x"], "order": {"Metricas.x": "asc"}, "limit": 1},
                    metric_catalog=[{"key": "Metricas.x", "source": "custom", "cube_dependencies": ["F.value"],
                                     "compiled_expression": "x", "variables": {"x": "F.value"}}],
                )
        with self.assertRaises(HTTPException) as error:
            asyncio.run(run())
        self.assertIn("ranking completo", error.exception.detail)

    def test_order_only_custom_metric_is_computed_before_limit(self):
        response = httpx.Response(200, json={"data": [
            {"F.value": 100, "F.cost": 2}, {"F.value": 10, "F.cost": 8},
        ]}, request=httpx.Request("GET", "http://cube/load"))
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)) as get:
            result = asyncio.run(execute_cube_semantic_query(
                {"measures": ["F.value"], "order": {"Metricas.x": "desc"}, "limit": 1},
                metric_catalog=[{"key": "Metricas.x", "source": "custom", "cube_dependencies": ["F.cost"],
                                 "compiled_expression": "x * 2", "variables": {"x": "F.cost"}}],
            ))
        sent = json.loads(get.call_args.kwargs["params"]["query"])
        self.assertIn("F.cost", sent["measures"])
        self.assertNotIn("Metricas.x", sent["measures"])
        self.assertEqual(result["data"], [{"F.value": 10}])

    def test_router_outage_preserves_short_data_followup(self):
        with patch("api.chat.post_llm_json", new=AsyncMock(side_effect=RuntimeError("offline"))):
            intent = asyncio.run(classify_chat_intent("Y por semana?", self.history(), {}))
        self.assertTrue(intent["needs_data"])

    def test_explicit_all_history_removes_previous_period(self):
        query = self.plan("Y para ese cliente en todo el histórico?", history=self.history())["queries"][0]["query"]
        self.assertNotIn("timeDimensions", query)

    def test_invalid_order_and_period_are_not_silently_removed(self):
        _, _, graph = semantic_fixture()
        for extra in [{"order": {"Unknown.value": "desc"}},
                      {"timeDimensions": [{"dimension": "FactVentas.fecha", "dateRange": "nonsense"}]}]:
            with self.subTest(extra=extra):
                query, errors = _sanitize_query({"measures": [AMOUNT_KEY], **extra}, graph, "Monto Total de Venta", None)
                self.assertIsNone(query)
                self.assertTrue(errors)

    def test_exact_date_ranges_are_not_expanded_to_a_year(self):
        self.assertEqual(extract_date_range_from_text("Del 2025-02-03 al 2025-04-07"), ["2025-02-03", "2025-04-07"])
        self.assertEqual(extract_date_range_from_text("el 15 de enero de 2025"), ["2025-01-15", "2025-01-15"])
        self.assertEqual(extract_date_range_from_text("enero de 2025"), ["2025-01-01", "2025-01-31"])
        self.assertIsNone(extract_date_range_from_text("entre enero y marzo de 2025"))
        self.assertIsNone(extract_date_range_from_text("primer trimestre de 2025"))

    def test_metric_repair_preserves_valid_filters(self):
        _, _, graph = semantic_fixture()
        scope = [{"member": CLIENT_KEY, "operator": "equals", "values": ["A"]}]
        compiled = {"queries": [{"query": {"measures": [COUNT_KEY], "filters": scope}}]}
        result = _enforce_deterministic_intent(compiled, graph, "Tiempo promedio entre ventas", None)
        self.assertEqual(result["queries"][0]["query"]["filters"], scope)
        self.assertEqual(result["queries"][0]["query"]["measures"], [CUSTOM_KEY])

    def test_virtual_comparison_preserves_periods_and_unknown_values(self):
        virtuals = [{"key": "virtual.test", "type": "comparison", "left": "F.a", "right": "F.b", "operator": "lt"}]
        rows = [{"F.date.month": "2025-01-01", "F.a": 1, "F.b": 2},
                {"F.date.month": "2025-02-01", "F.a": None, "F.b": 2}]
        result, summaries = _apply_virtual_metrics(rows, virtuals, {})
        self.assertEqual(len(result), 2)
        self.assertEqual(summaries["virtual.test"]["count"], 1)
        self.assertEqual(summaries["virtual.test"]["unknown_count"], 1)

    def test_cube_error_is_not_an_empty_success(self):
        response = httpx.Response(200, json={"error": "query failed"}, request=httpx.Request("GET", "http://cube/load"))
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)), self.assertRaises(HTTPException):
            asyncio.run(execute_cube_semantic_query({"measures": ["F.x"]}, metric_catalog=[]))

    def test_grouped_sample_without_order_does_not_claim_a_winner(self):
        answer = format_grouped_metric_answer("Comparar", {"measures": [AMOUNT_KEY], "dimensions": [CLIENT_KEY]},
                                             {"data": [{CLIENT_KEY: "A", AMOUNT_KEY: 10}]})
        self.assertNotIn("lidera", answer)
        self.assertNotIn("Comparacion por", answer)


class ChatIntegrityTests(unittest.TestCase):
    def request(self, *, plan=None, evidence=None, planner_error=None, stream=None, intent="data"):
        async def default_stream(*args, **kwargs):
            yield "Texto final."
        async def run():
            with ExitStack() as stack:
                for name, value in [("llm_is_configured", True), ("get_llm_headers", {}),
                                    ("user_id_from_authorization", "user")]:
                    stack.enter_context(patch(f"api.chat.{name}", return_value=value))
                stack.enter_context(patch("api.chat.build_runtime_system_prompt", new=AsyncMock(return_value="system")))
                stack.enter_context(patch("api.chat.classify_chat_intent", new=AsyncMock(return_value={
                    "mode": intent, "needs_data": intent == "data", "source": "llm",
                })))
                stack.enter_context(patch("api.chat.create_missing_metric_draft_from_prompt", new=AsyncMock(return_value=None)))
                stack.enter_context(patch("api.chat.compile_analysis_plan", new=AsyncMock(return_value=plan, side_effect=planner_error)))
                execute = stack.enter_context(patch("api.chat.execute_analysis_plan", new=AsyncMock(return_value=evidence)))
                fallback = stack.enter_context(patch("api.chat.infer_semantic_query_from_catalog", new=AsyncMock()))
                stack.enter_context(patch("api.chat.stream_llm_answer", new=stream or default_stream))
                response = await chat_with_data(ChatRequest(prompt="Explicame los criterios para un dashboard", connection_id="c"), authorization="Bearer test")
                events = []
                async for chunk in response.body_iterator:
                    events.append(json.loads(chunk.removeprefix("data: ").strip()))
                return events, execute.await_count, fallback.await_count
        return asyncio.run(run())

    def test_artifact_request_returns_text_without_executing_queries(self):
        events, calls, fallback = self.request(intent="artifact")
        self.assertEqual(calls, 0)
        self.assertEqual(fallback, 0)
        self.assertEqual([event["type"] for event in events], ["chunk", "done"])
        self.assertIn("no crea tableros", events[0]["content"])
        self.assertIn("Informes", events[0]["content"])

    def test_clarification_never_executes_or_falls_back(self):
        events, calls, fallback = self.request(plan={"queries": [], "clarification": "¿Qué criterio querés usar?"})
        self.assertEqual(calls, 0)
        self.assertEqual(fallback, 0)
        self.assertIn("criterio", events[0]["content"])
        self.assertEqual(events[-1]["type"], "done")

    def test_planner_error_never_substitutes_another_query(self):
        events, calls, fallback = self.request(planner_error=RuntimeError("failed"))
        self.assertEqual(calls, 0)
        self.assertEqual(fallback, 0)
        self.assertEqual(events[0]["type"], "error")

    def test_partial_evidence_is_not_a_complete_answer(self):
        events, calls, fallback = self.request(
            plan={"queries": [{"query": {"measures": [AMOUNT_KEY]}}]},
            evidence={"evidence": [{"data": [{AMOUNT_KEY: 999}]}], "validation_errors": ["second query failed"]},
        )
        self.assertEqual(calls, 1)
        self.assertEqual(fallback, 0)
        self.assertNotIn("999", json.dumps(events))
        self.assertNotIn("semantic_context", [event["type"] for event in events])

    def test_guidance_about_dashboard_does_not_create_artifact(self):
        events, calls, fallback = self.request(intent="guidance")
        self.assertEqual((calls, fallback), (0, 0))
        self.assertEqual(events[0]["content"], "Texto final.")

    def test_failed_narration_discards_partial_text_and_keeps_factual_scope(self):
        async def broken_stream(*args, **kwargs):
            yield "Respuesta incompleta que no se debe mostrar"
            raise RuntimeError("disconnected")
        query = {"measures": [CUSTOM_KEY], "filters": [{"member": CLIENT_KEY, "operator": "equals", "values": ["A"]}]}
        evidence = {"evidence": [{"query": query, "data": [{CUSTOM_KEY: 3.05}],
                                  "metric_metadata": {CUSTOM_KEY: {"name": "Demora", "format": "duration_days"}}}]}
        events, _, fallback = self.request(plan={"queries": [{"query": query}], "connection_id": "c"}, evidence=evidence, stream=broken_stream)
        self.assertEqual(fallback, 0)
        text = "".join(event["content"] for event in events if event["type"] == "chunk")
        self.assertNotIn("incompleta", text)
        self.assertIn("3,05 días", text)
        self.assertIn("**A**", text)
        state = next(event["content"] for event in events if event["type"] == "semantic_context")
        self.assertEqual(state["connection_id"], "c")

    def test_multiple_queries_do_not_select_the_first_entity_or_hide_other_results(self):
        async def broken_stream(*args, **kwargs):
            yield "incompleto"
            raise RuntimeError("disconnected")
        query = {"measures": [AMOUNT_KEY], "dimensions": [CLIENT_KEY]}
        packs = [{"query": query, "data": [{CLIENT_KEY: name, AMOUNT_KEY: 10}], "label": name}
                 for name in ["Primera consulta", "Segunda consulta"]]
        digests = [{"query": query, "label": pack["label"], "sample_rows": pack["data"], "row_count": 1} for pack in packs]
        events, _, _ = self.request(
            plan={"queries": [{"query": query}, {"query": query}], "connection_id": "c"},
            evidence={"evidence": packs, "evidence_digest": digests}, stream=broken_stream,
        )
        state = next(event["content"] for event in events if event["type"] == "semantic_context")
        self.assertEqual(state["selected_entities"], [])
        self.assertIsNone(state["primary_measure"])
        text = "".join(event["content"] for event in events if event["type"] == "chunk")
        self.assertIn("Primera consulta", text)
        self.assertIn("Segunda consulta", text)


if __name__ == "__main__":
    unittest.main()
