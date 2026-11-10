import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from api.chat import (
    ChatRequest, _fallback_chat_intent, chat_with_data, classify_chat_intent,
    prepare_chat_analysis, generate_verified_recommendations,
)
from api.semantic_metrics import create_missing_metric_draft_from_prompt
from services.semantic_planner import compile_analysis_plan
from services.recommendation_evidence import recommendation_facts, render_recommendations
from services.conversation_context import select_conversation_history
from test_semantic_metric_routing import semantic_fixture, AMOUNT_KEY, COUNT_KEY, CLIENT_KEY


TICKET = "Metricas.mean_invoice"


def contextual_fixture():
    catalog, metrics, _ = semantic_fixture()
    metrics.append({"key": TICKET, "name": "Ticket promedio de ventas", "source": "custom",
                    "format": "currency", "cube_dependencies": [AMOUNT_KEY, COUNT_KEY]})
    catalog["tables"].append({"id": "p", "name": "DimItem"})
    catalog["fields"].append({"table_id": "p", "semantic_key": "DimItem.caption",
                              "business_name": "Nombre producto", "field_kind": "dimension", "data_type": "string"})
    catalog["relationships"].append({"from_table": "FactVentas", "from_field": "item", "to_table": "DimItem", "to_field": "id"})
    return catalog, metrics


class ContextualBusinessChatTests(unittest.TestCase):
    def test_scoped_ticket_uses_existing_catalog_before_llm_metric_resolution(self):
        catalog, metrics = contextual_fixture()
        with (
            patch("api.semantic_metrics.fetch_semantic_catalog", new=AsyncMock(return_value=catalog)),
            patch("api.semantic_metrics.build_metric_catalog", new=AsyncMock(return_value=metrics)),
            patch("api.semantic_metrics.fetch_custom_metrics", new=AsyncMock(return_value=[])),
            patch("api.semantic_metrics.fetch_company_context", new=AsyncMock(return_value={})),
            patch("api.semantic_metrics._infer_metric_resolution_with_llm", new=AsyncMock()) as resolver,
            patch("api.semantic_metrics.sb.rest_post", new=AsyncMock()) as write,
        ):
            result = asyncio.run(create_missing_metric_draft_from_prompt(
                prompt="Cuál es el ticket promedio de nuestro mejor cliente?", user_id="u", connection_id="c",
            ))
        self.assertEqual(result["existing_metric_key"], TICKET)
        resolver.assert_not_awaited()
        write.assert_not_awaited()

    def test_metric_resolver_outage_is_not_evidence_of_a_missing_metric(self):
        catalog, metrics = contextual_fixture()
        with (
            patch("api.semantic_metrics.fetch_semantic_catalog", new=AsyncMock(return_value=catalog)),
            patch("api.semantic_metrics.build_metric_catalog", new=AsyncMock(return_value=metrics)),
            patch("api.semantic_metrics.fetch_custom_metrics", new=AsyncMock(return_value=[])),
            patch("api.semantic_metrics.fetch_company_context", new=AsyncMock(return_value={})),
            patch("api.semantic_metrics._infer_metric_resolution_with_llm", new=AsyncMock(return_value={"status": "unavailable"})),
            patch("api.semantic_metrics.sb.rest_post", new=AsyncMock()) as write,
        ):
            result = asyncio.run(create_missing_metric_draft_from_prompt(prompt="Promedio de continuidad operativa", user_id="u"))
        self.assertEqual(result["resolution_status"], "unavailable")
        self.assertNotIn("requires_definition", result)
        write.assert_not_awaited()

    def test_unknown_followup_is_not_replaced_by_previous_metric(self):
        catalog, metrics = contextual_fixture()
        with (
            patch("api.semantic_metrics.fetch_semantic_catalog", new=AsyncMock(return_value=catalog)),
            patch("api.semantic_metrics.build_metric_catalog", new=AsyncMock(return_value=metrics)),
            patch("api.semantic_metrics.fetch_custom_metrics", new=AsyncMock(return_value=[])),
            patch("api.semantic_metrics.fetch_company_context", new=AsyncMock(return_value={})),
            patch("api.semantic_metrics._infer_metric_resolution_with_llm", new=AsyncMock(return_value={"status": "unavailable"})) as resolver,
        ):
            result = asyncio.run(create_missing_metric_draft_from_prompt(
                prompt="¿Y la continuidad operativa?", user_id="u", connection_id="c",
                conversation_history=[{"role": "assistant", "semantic_context": {
                    "connection_id": "c", "primary_measure": TICKET,
                }}],
            ))
        resolver.assert_awaited_once()
        self.assertEqual(result["resolution_status"], "unavailable")

    def test_planning_and_scope_clarification_precede_metric_creation(self):
        for plan in [{"queries": [], "clarification": "¿Qué criterio define al mejor?"},
                     {"queries": [{"query": {"measures": [TICKET], "dimensions": [CLIENT_KEY]}}]}]:
            with (
                self.subTest(plan=plan),
                patch("api.chat.compile_analysis_plan", new=AsyncMock(return_value=plan)),
                patch("api.chat.create_missing_metric_draft_from_prompt", new=AsyncMock()) as create,
            ):
                result, suggestion = asyncio.run(prepare_chat_analysis("Ticket del mejor cliente", "u", "c", [], "data"))
                self.assertEqual(result, plan)
                self.assertIsNone(suggestion)
                create.assert_not_awaited()

    def test_genuinely_missing_base_metric_can_still_be_proposed(self):
        plan = {"queries": [], "missing_metric_request": "Tiempo de espera en caja"}
        with (
            patch("api.chat.compile_analysis_plan", new=AsyncMock(return_value=plan)),
            patch("api.chat.create_missing_metric_draft_from_prompt", new=AsyncMock(return_value={"resolution_status": "missing"})) as create,
        ):
            _, suggestion = asyncio.run(prepare_chat_analysis("Tiempo de espera en caja del mejor local", "u", "c", [], "data"))
        self.assertEqual(create.call_args.kwargs["prompt"], "Tiempo de espera en caja")
        self.assertEqual(create.call_args.kwargs["original_request"], "Tiempo de espera en caja del mejor local")
        self.assertEqual(suggestion["resolution_status"], "missing")

    def test_ticket_criterion_followup_keeps_ticket_as_target(self):
        catalog, metrics = contextual_fixture()
        catalog["fields"].append({"table_id": "p", "semantic_key": "DimItem.price",
            "business_name": "Monto Total de Venta", "field_kind": "dimension", "data_type": "number"})
        initial = "Cuál es el ticket promedio de nuestro mejor cliente?"
        first = asyncio.run(compile_analysis_plan(prompt=initial, user_id="", semantic_catalog=catalog, metric_catalog=metrics, use_llm=False))
        self.assertEqual(first["clarification_kind"], "selection_criterion")
        context = {"conversation_history": [{"role": "assistant", "semantic_context": {
            "pending_request": initial, "clarification_kind": "selection_criterion",
        }}]}
        second = asyncio.run(compile_analysis_plan(prompt="Por Monto Total de Venta", user_id="", semantic_catalog=catalog,
                                                    metric_catalog=metrics, context=context, use_llm=False))
        query = second["queries"][0]["query"]
        self.assertEqual(query["measures"][0], TICKET)
        self.assertEqual(query["order"], {AMOUNT_KEY: "desc"})
        self.assertEqual(query["dimensions"], [CLIENT_KEY])

    def test_applied_strategy_requests_require_data(self):
        prompt = "Qué estrategias de ventas puedo implementar para aumentarlas?"
        self.assertEqual(_fallback_chat_intent(prompt)["mode"], "recommendation")
        with patch("api.chat.post_llm_json", new=AsyncMock(return_value={"choices": [{"message": {"content": json.dumps({"mode": "recommendation", "needs_data": False})}}]})):
            result = asyncio.run(classify_chat_intent(prompt, [], {}))
        self.assertTrue(result["needs_data"])
        self.assertEqual(_fallback_chat_intent("Cuáles son otras formas de determinar mi mejor cliente?")["mode"], "guidance")

    def test_recommendation_exploration_keeps_totals_and_trend_separate(self):
        catalog, metrics = contextual_fixture()
        plan = asyncio.run(compile_analysis_plan(prompt="Qué estrategias de ventas puedo implementar?", user_id="",
            semantic_catalog=catalog, metric_catalog=metrics, context={"surface": "recommendation"}, use_llm=False))
        self.assertFalse(plan["validation_errors"])
        queries = [spec["query"] for spec in plan["queries"]]
        self.assertFalse(queries[0].get("timeDimensions"))
        grouped = [query for query in queries if query.get("dimensions")]
        self.assertEqual({query["dimensions"][0] for query in grouped}, {CLIENT_KEY, "DimItem.caption"})
        self.assertTrue(all(not query.get("timeDimensions") for query in grouped))
        self.assertEqual(queries[-1]["timeDimensions"][0]["granularity"], "month")

    def test_recommendations_never_open_metric_creation_flow(self):
        with (
            patch("api.chat.compile_analysis_plan", new=AsyncMock(return_value={"queries": []})) as planner,
            patch("api.chat.create_missing_metric_draft_from_prompt", new=AsyncMock()) as create,
        ):
            _, suggestion = asyncio.run(prepare_chat_analysis("Estrategias para crecer", "u", "c", [], "recommendation"))
        create.assert_not_awaited()
        self.assertIsNone(suggestion)
        self.assertEqual(planner.call_args.kwargs["context"]["surface"], "recommendation")

    def test_optional_period_does_not_block_business_recommendations(self):
        catalog, metrics = contextual_fixture()
        with patch("services.semantic_planner._llm_plan", new=AsyncMock(return_value={
            "queries": [], "clarification": "¿Para qué período te gustaría analizar las ventas?",
        })):
            plan = asyncio.run(compile_analysis_plan(
                prompt="Qué estrategias de ventas puedo implementar para aumentarlas?", user_id="",
                semantic_catalog=catalog, metric_catalog=metrics, context={"surface": "recommendation"},
            ))
        self.assertTrue(plan["queries"])
        self.assertFalse(plan.get("clarification"))
        self.assertTrue(all(not item.get("dateRange") for spec in plan["queries"]
                            for item in spec["query"].get("timeDimensions") or []))

    def test_entity_selection_uses_business_labels_with_opaque_keys(self):
        catalog = {
            "tables": [{"id": "f", "name": "F7"}, {"id": "d", "name": "D9", "business_name": "Pacientes"}],
            "fields": [{"table_id": "d", "semantic_key": "D9.caption", "business_name": "Nombre completo",
                        "field_kind": "dimension", "data_type": "string"}],
            "relationships": [{"from_table": "F7", "from_field": "ref", "to_table": "D9", "to_field": "id"}],
        }
        metrics = [{"key": "F7.a", "name": "Tiempo medio de recuperación"},
                   {"key": "F7.b", "name": "Intervenciones registradas"}]
        plan = asyncio.run(compile_analysis_plan(
            prompt="Tiempo medio de recuperación del mejor paciente por Intervenciones registradas", user_id="",
            semantic_catalog=catalog, metric_catalog=metrics, use_llm=False,
        ))
        query = plan["queries"][0]["query"]
        self.assertEqual(query["dimensions"], ["D9.caption"])
        self.assertEqual(query["measures"][0], "F7.a")
        self.assertEqual(query["order"], {"F7.b": "desc"})

    def test_invalid_recommendation_is_repaired_before_publication(self):
        digest = [{"query": {"measures": [AMOUNT_KEY]}, "sample_rows": [{AMOUNT_KEY: 10}],
                   "metric_metadata": {AMOUNT_KEY: {"name": "Ingresos registrados", "format": "currency"}}}]
        action = {"title": "Validar la propuesta", "proposal": "Probar la propuesta con compradores actuales.",
                  "hypothesis": "Podría ayudar a evaluar sus necesidades.", "fact_ids": ["e0r0m0"],
                  "monitoring_measures": [AMOUNT_KEY]}
        def response(payload):
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}
        with patch("api.chat.post_llm_json", new=AsyncMock(side_effect=[
            response({"actions": [{**action, "proposal": "Aumentar ingresos un 50%."}]}),
            response({"actions": [action]}),
        ])) as llm:
            result = asyncio.run(generate_verified_recommendations([], {"evidence_digest": digest}, {}))
        self.assertEqual(llm.await_count, 2)
        self.assertNotIn("50%", result)
        self.assertIn("Ingresos registrados **$10,00**", result)

    def test_recommendation_generation_receives_company_and_real_entities(self):
        async def run():
            captured = []
            async def generate(payload, *args, **kwargs):
                captured.extend(payload["messages"])
                return {"choices": [{"message": {"content": json.dumps({"actions": [{
                    "title": "Probar una demostración", "proposal": "Ofrecer una demostración de Amoladora.",
                    "hypothesis": "Podría facilitar la evaluación del producto.", "fact_ids": ["e0r0m0"],
                    "monitoring_measures": [AMOUNT_KEY],
                }]})}}]}
            query = {"measures": [AMOUNT_KEY], "dimensions": ["DimItem.caption"]}
            evidence = {"query": query, "data": [{"DimItem.caption": "Amoladora", AMOUNT_KEY: 100}]}
            with (
                patch("api.chat.llm_is_configured", return_value=True),
                patch("api.chat.get_llm_headers", return_value={}),
                patch("api.chat.user_id_from_authorization", return_value="u"),
                patch("api.chat.build_runtime_system_prompt", new=AsyncMock(return_value="Empresa industrial. Vende herramientas.")),
                patch("api.chat.classify_chat_intent", new=AsyncMock(return_value={"mode": "recommendation", "needs_data": True})),
                patch("api.chat.compile_analysis_plan", new=AsyncMock(return_value={"queries": [{"query": query}]})),
                patch("api.chat.execute_analysis_plan", new=AsyncMock(return_value={"evidence": [evidence], "evidence_digest": [{"query": query, "sample_rows": evidence["data"]}]})) as execute,
                patch("api.chat.create_missing_metric_draft_from_prompt", new=AsyncMock()) as create,
                patch("api.chat.post_llm_json", new=generate),
            ):
                history = [{"role": "user", "content": "Fabricamos herramientas de precisión para talleres."}]
                history.extend({"role": "assistant", "content": "Consulta anterior resuelta."} for _ in range(8))
                response = await chat_with_data(ChatRequest(prompt="Qué estrategias de ventas puedo implementar?", history=history), authorization="Bearer test")
                events = [json.loads(item.removeprefix("data: ").strip()) async for item in response.body_iterator]
                execute.assert_awaited_once()
                create.assert_not_awaited()
            return captured, events
        messages, events = asyncio.run(run())
        text = json.dumps(messages, ensure_ascii=False)
        self.assertIn("Empresa industrial", text)
        self.assertIn("Fabricamos herramientas de precisión", text)
        self.assertIn("Amoladora", text)
        self.assertIn("acciones concretas", text)
        self.assertEqual(events[-1]["type"], "done")

    def test_long_history_retains_opening_context_and_recent_referents_within_budget(self):
        history = [{"role": "user", "content": "Nuestro negocio es una clínica."}]
        history.extend({"role": "assistant", "content": "x" * 10_000} for _ in range(30))
        history.append({"role": "assistant", "content": "La entidad seleccionada.", "semantic_context": {"primary_measure": TICKET}})
        selected = select_conversation_history(history)
        self.assertEqual(selected[0], history[0])
        self.assertEqual(selected[-1], history[-1])
        self.assertLessEqual(sum(len(message["content"]) for message in selected), 48_000)
        self.assertTrue(all(len(message["content"]) <= 6_000 for message in selected))
        self.assertEqual(select_conversation_history(selected), selected)

    def test_recommendation_facts_keep_period_scope_and_drop_unknown_values(self):
        facts = recommendation_facts([{
            "query": {"measures": [AMOUNT_KEY, COUNT_KEY], "dimensions": ["DimItem.caption"],
                      "timeDimensions": [{"dimension": "Events.date", "granularity": "month"}]},
            "sample_rows": [{"DimItem.caption": "Equipo 3000", "Events.date.month": "2026-06-01T00:00:00.000", AMOUNT_KEY: 123.45, COUNT_KEY: None}],
            "metric_metadata": {AMOUNT_KEY: {"name": "Ingresos registrados"}},
        }])
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["scope"]["periods"], ["2026-06"])
        self.assertEqual(facts[0]["scope"]["time_dimensions"][0]["granularity"], "month")
        self.assertEqual(facts[0]["name"], "Ingresos registrados")

    def test_recommendation_rejects_invented_facts_metrics_and_numbers(self):
        facts = recommendation_facts([{
            "query": {"measures": [AMOUNT_KEY], "dimensions": ["DimItem.caption"]},
            "sample_rows": [{"DimItem.caption": "Equipo 3000", AMOUNT_KEY: 123.45}],
            "metric_metadata": {AMOUNT_KEY: {"name": "Ingresos registrados"}},
        }])
        action = {"title": "Demostrar el producto", "proposal": "Probar demostraciones de Equipo 3000.",
                  "hypothesis": "Podría facilitar la evaluación del equipo.",
                  "fact_ids": [facts[0]["id"]], "monitoring_measures": [AMOUNT_KEY]}
        for change in [{"fact_ids": ["invented"]}, {"monitoring_measures": ["Fake.units"]},
                       {"proposal": "Aumentar ventas un 25%."}, {"fact_ids": []}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                render_recommendations({"actions": [{**action, **change}]}, facts, lambda *args: "123,45")
        result = render_recommendations({"actions": [action]}, facts, lambda *args: "123,45", partial=True)
        self.assertIn("Equipo 3000: Ingresos registrados **123,45**", result)
        self.assertIn("Hipótesis a validar", result)
        self.assertIn("Parte de las consultas", result)

    def test_recommendation_temporal_evidence_does_not_claim_a_decline(self):
        facts = recommendation_facts([{
            "query": {"measures": [COUNT_KEY], "timeDimensions": [{"dimension": "Events.date", "granularity": "month"}]},
            "sample_rows": [{"Events.date.month": "2026-06-01", COUNT_KEY: 10}],
            "metric_metadata": {COUNT_KEY: {"name": "Eventos registrados"}},
        }])
        result = render_recommendations({"actions": [{
            "title": "Verificar cobertura", "proposal": "Revisar que se hayan cargado todos los eventos del período.",
            "hypothesis": "La cobertura podría afectar la comparación.", "fact_ids": [facts[0]["id"]],
            "monitoring_measures": [COUNT_KEY],
        }]}, facts, lambda *args: "10")
        self.assertIn("cobertura completa de los períodos no está verificada", result)
        self.assertIn("Eventos registrados **10**", result)
        self.assertNotIn("unidades", result)


if __name__ == "__main__":
    unittest.main()
