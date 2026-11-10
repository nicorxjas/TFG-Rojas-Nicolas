"""User-reported Ollama failures, tested with deliberately unreliable LLM output."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from api.chat import ChatRequest, chat_with_data, catalog_criteria_answer, classify_chat_intent
from api.semantic_metrics import create_missing_metric_draft_from_prompt
from services.semantic_planner import compile_analysis_plan
from services.metric_request import subject_matches
from test_contextual_business_chat import contextual_fixture, TICKET
from test_semantic_metric_routing import AMOUNT_KEY, COUNT_KEY, CLIENT_KEY

STOCK = "Inventario.stock_cierre"
QUANTITY = "FactVentas.cantidad_vendida"


def fixture():
    catalog, metrics = contextual_fixture()
    metrics.extend([
        {"key": STOCK, "name": "Stock al Cierre", "cube_dependencies": [STOCK]},
        {"key": QUANTITY, "name": "Cantidad vendida", "cube_dependencies": [QUANTITY]},
    ])
    return catalog, metrics


class UserChatRegressions(unittest.TestCase):
    def test_catalog_changes_drive_options_and_average_resolution_across_domains(self):
        for entity, subject, average_name in [
            ("Profesional", "duración", "Duración típica"),
            ("Curso", "asistencia", "Asistencia media"),
            ("Máquina", "consumo", "Consumo habitual"),
        ]:
            with self.subTest(entity=entity):
                # Keys deliberately contain no clues about the business domain.
                catalog = {
                    "tables": [{"id": "a", "name": "Records"}, {"id": "b", "name": "Entities"}],
                    "fields": [{"table_id": "b", "semantic_key": "Entities.x7", "business_name": entity, "field_kind": "dimension"}],
                    "relationships": [{"from_table": "Records", "from_field": "b_id", "to_table": "Entities", "to_field": "id"}],
                    "metrics": [{"key": "Records.x9", "name": subject, "cube_dependencies": ["Records.x9"]}],
                }
                metrics = list(catalog["metrics"])
                average = {"key": "Derived.z2", "name": average_name, "aliases": [f"Promedio de {subject}"],
                           "source": "custom", "cube_dependencies": ["Records.x9"]}
                prompt = f"¿Cuál es el promedio de {subject}?"
                missing = asyncio.run(compile_analysis_plan(prompt=prompt, user_id="", semantic_catalog=catalog,
                                                            metric_catalog=metrics, use_llm=False))
                self.assertEqual(missing["queries"], [])
                self.assertTrue(missing.get("missing_metric_request"))
                metrics.append(average)
                existing = asyncio.run(compile_analysis_plan(prompt=prompt, user_id="", semantic_catalog=catalog,
                                                             metric_catalog=metrics, use_llm=False))
                self.assertEqual(existing["queries"][0]["query"]["measures"], ["Derived.z2"])
                answer = catalog_criteria_answer("¿Qué opciones tengo?", [
                    {"role": "user", "content": f"¿Cuál es el mejor {entity}?"}], catalog, [average])
                self.assertIn(f"**{subject}**", answer)
                self.assertIn(average_name, answer)
                for forbidden in ["Records.", "Derived.", "venta", "cliente", "ticket"]:
                    self.assertNotIn(forbidden, answer.lower())

    def test_business_equivalence_must_come_from_catalog_aliases(self):
        metric = {"name": "Volumen", "key": "Records.x9"}
        self.assertFalse(subject_matches("cantidad vendida", metric))
        self.assertTrue(subject_matches("cantidad vendida", {**metric, "aliases": ["Cantidad vendida"]}))

    def test_options_include_base_and_custom_metrics_and_exclude_unrelated_stock(self):
        catalog, metrics = fixture()
        answer = catalog_criteria_answer("¿Qué opciones tengo?", [
            {"role": "user", "content": "¿Cuál es nuestro mejor cliente?"},
            {"role": "assistant", "content": "¿Con qué criterio?"},
        ], catalog, metrics)
        for name in ["Monto Total de Venta", "Cantidad de Ventas", "Ticket promedio de ventas", "Tiempo promedio entre ventas"]:
            self.assertIn(name, answer)
        for technical in ["Metricas.", "FactVentas.", "Stock al Cierre", "_promedio", "query_semantic_model"]:
            self.assertNotIn(technical, answer)

    def test_general_options_without_ranking_context_do_not_assume_customers(self):
        catalog, metrics = fixture()
        self.assertIsNone(catalog_criteria_answer("¿Qué opciones tengo?", [], catalog, metrics))

    def test_data_request_cannot_be_routed_to_free_form_general_answer(self):
        with patch("api.chat.post_llm_json", new=AsyncMock(return_value={"choices": [{"message": {
            "content": json.dumps({"mode": "general", "needs_data": False})}}]})):
            result = asyncio.run(classify_chat_intent("Mostrame los 3 mejores clientes según el ticket promedio", [], {}))
        self.assertEqual(result["mode"], "data")
        self.assertTrue(result["needs_data"])

    def test_missing_average_cannot_be_replaced_with_stock_or_quantity_sum(self):
        catalog, metrics = fixture()
        with patch("services.semantic_planner._llm_plan", new=AsyncMock(return_value={
            "queries": [{"query": {"measures": [STOCK]}}]})) as llm:
            plan = asyncio.run(compile_analysis_plan(
                prompt="¿Cuál es el promedio de cantidad vendida?", user_id="",
                semantic_catalog=catalog, metric_catalog=metrics,
            ))
        self.assertEqual(plan["queries"], [])
        self.assertEqual(plan["missing_metric_request"], "Promedio de cantidad vendida")
        llm.assert_not_awaited()

    def test_existing_average_is_reused(self):
        catalog, metrics = fixture()
        key = "Metricas.promedio_cantidad_vendida"
        metrics.append({"key": key, "name": "Promedio de cantidad vendida", "source": "custom", "cube_dependencies": [QUANTITY]})
        plan = asyncio.run(compile_analysis_plan(
            prompt="¿Cuál es el promedio de cantidad vendida?", user_id="", use_llm=False,
            semantic_catalog=catalog, metric_catalog=metrics,
        ))
        self.assertEqual(plan["queries"][0]["query"]["measures"], [key])
        self.assertNotIn("missing_metric_request", plan)

    def test_missing_average_asks_for_definition_without_inventing_formula_or_creating_metric(self):
        catalog, metrics = fixture()
        with (
            patch("api.semantic_metrics.fetch_semantic_catalog", new=AsyncMock(return_value=catalog)),
            patch("api.semantic_metrics.build_metric_catalog", new=AsyncMock(return_value=metrics)),
            patch("api.semantic_metrics.fetch_custom_metrics", new=AsyncMock(return_value=[])),
            patch("api.semantic_metrics.fetch_company_context", new=AsyncMock(return_value={})),
            patch("api.semantic_metrics._infer_metric_resolution_with_llm", new=AsyncMock(return_value={"status": "existing", "existing_metric_key": STOCK})) as llm,
            patch("api.semantic_metrics.sb.rest_post", new=AsyncMock()) as write,
        ):
            suggestion = asyncio.run(create_missing_metric_draft_from_prompt(
                prompt="¿Cuál es el promedio de cantidad vendida?", user_id="u", connection_id="c"))
        self.assertEqual(suggestion["resolution_status"], "missing")
        self.assertTrue(suggestion["requires_definition"])
        self.assertEqual(suggestion["expression"], "")
        llm.assert_not_awaited()
        write.assert_not_awaited()

    def test_ranked_answer_uses_only_queried_names_and_values_without_llm_rewriting(self):
        async def run():
            query = {"measures": [TICKET], "dimensions": ["DimCliente.id", CLIENT_KEY], "order": {TICKET: "desc"}, "limit": 3}
            evidence = {"query": query, "metric_metadata": {TICKET: {"name": "Ticket promedio de ventas", "format": "currency"}},
                        "data": [{"DimCliente.id": "id-a", CLIENT_KEY: "Cliente A", TICKET: 100},
                                 {"DimCliente.id": "id-b", CLIENT_KEY: "Cliente B", TICKET: 300},
                                 {"DimCliente.id": "id-c", CLIENT_KEY: "Cliente C", TICKET: 200}]}
            async def untrusted_stream(*args, **kwargs):
                raise AssertionError("The LLM must not rewrite verified values")
                yield "Invented customer: $1234.56"
            with (
                patch("api.chat.user_id_from_authorization", return_value="u"),
                patch("api.chat.build_runtime_system_prompt", new=AsyncMock(return_value="system")),
                patch("api.chat.classify_chat_intent", new=AsyncMock(return_value={"mode": "data", "needs_data": True})),
                patch("api.chat.prepare_chat_analysis", new=AsyncMock(return_value=({"queries": [{"query": query}]}, None))),
                patch("api.chat.execute_analysis_plan", new=AsyncMock(return_value={"evidence": [evidence]})),
                patch("api.chat.stream_llm_answer", new=untrusted_stream),
            ):
                response = await chat_with_data(ChatRequest(prompt="Los 3 mejores clientes según el ticket promedio", connection_id="c"), authorization="test")
                return [json.loads(event.removeprefix("data: ")) async for event in response.body_iterator]
        events = asyncio.run(run())
        answer = "".join(event["content"] for event in events if event["type"] == "chunk")
        self.assertIn("1. **Cliente B**: **$300,00**", answer)
        self.assertIn("2. **Cliente C**: **$200,00**", answer)
        self.assertIn("3. **Cliente A**: **$100,00**", answer)
        for forbidden in ["id-a", "Metricas.", "query_semantic_model", "_TOTALES_", "1234"]:
            self.assertNotIn(forbidden, answer)
        self.assertEqual(events[-1]["type"], "done")

    def test_numeric_field_offers_a_valid_creation_proposal(self):
        catalog, metrics = fixture()
        catalog["fields"].append({"table_id": "fact", "semantic_key": "FactVentas.cantidad",
                                  "business_name": "Cantidad vendida", "field_kind": "dimension",
                                  "data_type": "number", "metadata": {"source": "excel", "provider": "cube"}})
        metrics.append({"key": "FactVentas.cantidad_avg", "name": "Promedio Cantidad vendida",
                        "source": "aggregate_helper", "aggregate_operation": "avg", "aggregate_field": "FactVentas.cantidad"})
        with (
            patch("api.semantic_metrics.fetch_semantic_catalog", new=AsyncMock(return_value=catalog)),
            patch("api.semantic_metrics.build_metric_catalog", new=AsyncMock(return_value=metrics)),
            patch("api.semantic_metrics.fetch_custom_metrics", new=AsyncMock(return_value=[])),
            patch("api.semantic_metrics.fetch_company_context", new=AsyncMock(return_value={})),
            patch("api.semantic_metrics._infer_metric_resolution_with_llm", new=AsyncMock()) as llm,
            patch("api.semantic_metrics.sb.rest_post", new=AsyncMock(return_value=[{"id": "draft-test"}])) as write,
        ):
            result = asyncio.run(create_missing_metric_draft_from_prompt(
                prompt="¿Cuál es el promedio de cantidad vendida?", user_id="u", connection_id="c"))
        self.assertEqual(result["resolution_status"], "missing")
        self.assertFalse(result.get("requires_definition", False))
        self.assertEqual(result["expression"], "avg(FactVentas.cantidad)")
        self.assertEqual(result["draft_id"], "draft-test")
        self.assertEqual(write.call_args.args[0], "semantic_metric_drafts")
        llm.assert_not_awaited()

    def test_missing_metric_is_a_menu_event_and_never_a_stock_answer(self):
        async def run():
            suggestion = {"resolution_status": "missing", "name": "Promedio de cantidad vendida",
                          "proposed_calculation": "Definir sobre qué registros se calcula.", "requires_definition": True}
            with (
                patch("api.chat.user_id_from_authorization", return_value="u"),
                patch("api.chat.build_runtime_system_prompt", new=AsyncMock(return_value="system")),
                patch("api.chat.classify_chat_intent", new=AsyncMock(return_value={"mode": "data", "needs_data": True})),
                patch("api.chat.prepare_chat_analysis", new=AsyncMock(return_value=({"queries": []}, suggestion))),
                patch("api.chat.execute_analysis_plan", new=AsyncMock()) as execute,
            ):
                response = await chat_with_data(ChatRequest(prompt="¿Cuál es el promedio de cantidad vendida?", connection_id="c"), authorization="test")
                events = [json.loads(event.removeprefix("data: ")) async for event in response.body_iterator]
                execute.assert_not_awaited()
            return events
        events = asyncio.run(run())
        self.assertEqual([event["type"] for event in events], ["metric_suggestion", "done"])
        self.assertIn("no existe", events[0]["content"]["message"])
