import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from api.chat import (
    _fallback_chat_intent,
    ChatRequest,
    build_semantic_conversation_context,
    chat_with_data,
    classify_chat_intent,
    format_grouped_metric_answer,
    format_quick_metric_answer,
    repair_semantic_query_from_catalog,
)
from api.semantic_metrics import _metric_proposal_already_exists
from services.semantic_graph import build_semantic_graph
from services.semantic_planner import (
    _catalog_payload,
    _enforce_deterministic_intent,
    _explicit_catalog_metric,
    compile_analysis_plan,
    infer_sales_activity_query,
)
from services.semantic_query_engine import apply_post_compute_order


CUSTOM_KEY = "Metricas.tiempo_promedio_entre_ventas"
COUNT_KEY = "FactVentas.cantidad_ventas"
AMOUNT_KEY = "FactVentas.monto_total"
CLIENT_KEY = "DimCliente.nombre"


def semantic_fixture():
    catalog = {
        "tables": [
            {"id": "fact", "name": "FactVentas"},
            {"id": "client", "name": "DimCliente"},
        ],
        "metrics": [
            {
                "key": COUNT_KEY,
                "name": "Cantidad de Ventas",
                "description": "Cantidad de transacciones realizadas.",
                "cube_dependencies": [COUNT_KEY],
            },
            {
                "key": AMOUNT_KEY,
                "name": "Monto Total de Venta",
                "description": "Importe total vendido.",
                "format": "currency",
                "cube_dependencies": [AMOUNT_KEY],
            },
            {
                "key": "FactVentas.fecha_min",
                "name": "Primera fecha de venta",
                "cube_dependencies": ["FactVentas.fecha_min"],
            },
            {
                "key": "FactVentas.fecha_max",
                "name": "Ultima fecha de venta",
                "cube_dependencies": ["FactVentas.fecha_max"],
            },
        ],
        "fields": [
            {
                "table_id": "client",
                "semantic_key": CLIENT_KEY,
                "business_name": "Cliente",
                "field_kind": "dimension",
                "is_ai_enabled": True,
            },
            {
                "table_id": "fact",
                "semantic_key": "FactVentas.fecha",
                "business_name": "Fecha",
                "field_kind": "time",
                "is_ai_enabled": True,
            },
        ],
        "relationships": [
            {
                "from_table": "FactVentas",
                "from_field": "clienteid",
                "to_table": "DimCliente",
                "to_field": "clienteid",
                "is_active": True,
            }
        ],
    }
    metrics = catalog["metrics"] + [
        {
            "key": CUSTOM_KEY,
            "name": "Tiempo promedio entre ventas",
            "description": "Promedio de dias entre ventas consecutivas.",
            "format": "duration_days",
            "source": "custom",
            "business_area": "Ventas",
            "business_formula": "Lapso entre la primera y la ultima venta dividido por transacciones menos uno.",
            "aliases": ["cadencia de compra"],
            "cube_dependencies": [
                "FactVentas.fecha_min",
                "FactVentas.fecha_max",
                COUNT_KEY,
            ],
        }
    ]
    return catalog, metrics, build_semantic_graph(catalog, metrics)


class SemanticMetricRoutingTests(unittest.TestCase):
    def test_guidance_request_is_not_treated_as_data_query(self):
        prompt = "Cuales son otras formas de determinar cual es mi mejor cliente?"
        self.assertEqual(_fallback_chat_intent(prompt)["mode"], "guidance")
        llm_response = {
            "choices": [{
                "message": {
                    "content": '{"mode":"guidance","needs_data":false,"reason":"Pide criterios alternativos"}',
                }
            }]
        }
        with patch("api.chat.post_llm_json", new=AsyncMock(return_value=llm_response)):
            intent = asyncio.run(classify_chat_intent(prompt, [], {}))
        self.assertEqual(intent["mode"], "guidance")
        self.assertFalse(intent["needs_data"])

    def test_actual_value_request_is_routed_to_data(self):
        prompt = "Mostrame los datos y calcula cual cliente tiene el valor mas alto"
        self.assertEqual(_fallback_chat_intent(prompt)["mode"], "data")
        self.assertEqual(
            _fallback_chat_intent("Cual es el tiempo entre eventos para la entidad seleccionada?")["mode"],
            "data",
        )

    def test_guidance_mode_returns_without_entering_semantic_query_pipeline(self):
        async def fake_stream(*args, **kwargs):
            yield "Hay varias formas de definirlo; primero conviene elegir el criterio de negocio."

        async def run_request():
            with (
                patch("api.chat.llm_is_configured", return_value=True),
                patch("api.chat.get_llm_headers", return_value={}),
                patch("api.chat.build_runtime_system_prompt", new=AsyncMock(return_value="system")),
                patch(
                    "api.chat.classify_chat_intent",
                    new=AsyncMock(return_value={"mode": "guidance", "needs_data": False, "source": "llm"}),
                ),
                patch("api.chat.stream_llm_answer", new=fake_stream),
                patch("api.chat.compile_analysis_plan", new=AsyncMock(side_effect=AssertionError("planner called"))),
                patch(
                    "api.chat.infer_semantic_query_from_catalog",
                    new=AsyncMock(side_effect=AssertionError("query fallback called")),
                ),
            ):
                response = await chat_with_data(
                    ChatRequest(prompt="Cuales son otras formas de determinar cual es mi mejor cliente?"),
                    authorization=None,
                )
                chunks = []
                async for chunk in response.body_iterator:
                    chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
                return "".join(chunks)

        streamed = asyncio.run(run_request())
        self.assertIn("Hay varias formas de definirlo", streamed)
        self.assertIn('"type": "done"', streamed)

    def test_target_prompt_selects_custom_metric_client_and_minimum(self):
        catalog, metrics, _ = semantic_fixture()
        prompt = "Okay, ahora quiero que me digas cual es el cliente con menor tiempo entre ventas"
        plan = asyncio.run(
            compile_analysis_plan(
                prompt=prompt,
                user_id="",
                semantic_catalog=catalog,
                metric_catalog=metrics,
                context={"surface": "chat"},
                use_llm=False,
            )
        )
        query = plan["queries"][0]["query"]
        self.assertEqual(query["measures"], [CUSTOM_KEY])
        self.assertEqual(query["dimensions"], [CLIENT_KEY])
        self.assertEqual(query["order"], {CUSTOM_KEY: "asc"})
        self.assertEqual(query["limit"], 1)

    def test_hardcoded_validation_does_not_replace_correct_llm_plan(self):
        _, _, graph = semantic_fixture()
        original_filter = {"member": CLIENT_KEY, "operator": "contains", "values": ["Lopez"]}
        compiled = {
            "queries": [
                {
                    "id": "llm",
                    "label": "correcta",
                    "purpose": "minimo por cliente",
                    "query": {
                        "measures": [CUSTOM_KEY],
                        "dimensions": [CLIENT_KEY],
                        "order": {CUSTOM_KEY: "asc"},
                        "limit": 1,
                        "filters": [original_filter],
                    },
                    "virtual_metrics": [],
                }
            ],
            "warnings": [],
            "validation_errors": [],
            "virtual_metrics": [],
        }
        result = _enforce_deterministic_intent(
            compiled,
            graph,
            "cliente con menor tiempo entre ventas",
            None,
            {},
        )
        result_query = result["queries"][0]["query"]
        self.assertEqual(result_query["measures"], [CUSTOM_KEY])
        self.assertEqual(result_query["filters"], [original_filter])

    def test_follow_up_uses_recent_metric_context(self):
        catalog, metrics, _ = semantic_fixture()
        history = [
            {"role": "user", "content": "Cual es el tiempo promedio entre ventas?"},
            {"role": "assistant", "content": "El valor de Tiempo promedio entre ventas es 0,05 dias."},
        ]
        plan = asyncio.run(
            compile_analysis_plan(
                prompt="Y por cliente?",
                user_id="",
                semantic_catalog=catalog,
                metric_catalog=metrics,
                context={"surface": "chat", "conversation_history": history},
                use_llm=False,
            )
        )
        query = plan["queries"][0]["query"]
        self.assertEqual(query["measures"], [CUSTOM_KEY])
        self.assertEqual(query["dimensions"], [CLIENT_KEY])

    def test_best_customer_keeps_requested_metric_as_primary_answer(self):
        catalog, metrics, _ = semantic_fixture()
        plan = asyncio.run(
            compile_analysis_plan(
                prompt="Cual es el tiempo entre venta y venta para mi mejor cliente?",
                user_id="",
                semantic_catalog=catalog,
                metric_catalog=metrics,
                context={"surface": "chat", "conversation_history": [{
                    "role": "assistant", "semantic_context": {"selection_measure": AMOUNT_KEY},
                }]},
                use_llm=False,
            )
        )
        query = plan["queries"][0]["query"]
        self.assertEqual(query["measures"], [CUSTOM_KEY, AMOUNT_KEY])
        self.assertEqual(query["dimensions"], [CLIENT_KEY])
        self.assertEqual(query["order"], {AMOUNT_KEY: "desc"})
        self.assertEqual(query["limit"], 1)

    def test_best_customer_preserves_llm_selection_criterion(self):
        _, _, graph = semantic_fixture()
        compiled = {
            "queries": [{
                "id": "llm",
                "label": "best_customer",
                "purpose": "Select customer by an LLM-resolved business criterion.",
                "query": {
                    "measures": [COUNT_KEY, CUSTOM_KEY],
                    "dimensions": [CLIENT_KEY],
                    "order": {COUNT_KEY: "desc"},
                    "limit": 1,
                },
                "virtual_metrics": [],
            }],
            "warnings": [],
            "validation_errors": [],
            "virtual_metrics": [],
        }
        result = _enforce_deterministic_intent(
            compiled,
            graph,
            "tiempo entre venta y venta para mi mejor cliente",
            None,
            {},
        )
        query = result["queries"][0]["query"]
        self.assertEqual(query["measures"], [CUSTOM_KEY, COUNT_KEY])
        self.assertEqual(query["order"], {COUNT_KEY: "desc"})

    def test_follow_up_resolves_selected_customer_as_filter(self):
        catalog, metrics, _ = semantic_fixture()
        history = [
            {
                "role": "assistant",
                "content": "El tiempo promedio entre ventas de Gastronomica del Plata 17 es 3,05 dias.",
                "semantic_context": {
                    "primary_measure": CUSTOM_KEY,
                    "selection_measure": AMOUNT_KEY,
                    "selected_entities": [
                        {"member": CLIENT_KEY, "value": "Gastronomica del Plata 17"},
                    ],
                },
            }
        ]
        plan = asyncio.run(
            compile_analysis_plan(
                prompt="Bueno, pero decime cual es el tiempo entre venta y venta para ese cliente",
                user_id="",
                semantic_catalog=catalog,
                metric_catalog=metrics,
                context={"surface": "chat", "conversation_history": history},
                use_llm=False,
            )
        )
        query = plan["queries"][0]["query"]
        self.assertEqual(query["measures"], [CUSTOM_KEY])
        self.assertNotIn("dimensions", query)
        self.assertNotIn("timeDimensions", query)
        self.assertEqual(
            query["filters"],
            [{"member": CLIENT_KEY, "operator": "equals", "values": ["Gastronomica del Plata 17"]}],
        )
        result = {"data": [{CUSTOM_KEY: 3.05}]}
        answer = format_quick_metric_answer(
            "tiempo para ese cliente",
            query,
            result,
            {CUSTOM_KEY: {"name": "Tiempo promedio entre ventas", "format": "duration_days"}},
        )
        self.assertIn("Gastronomica del Plata 17", answer)
        self.assertIn("3,05 días", answer)
        state = build_semantic_conversation_context(query, result)
        self.assertEqual(
            state["selected_entities"],
            [{"member": CLIENT_KEY, "value": "Gastronomica del Plata 17"}],
        )
        continued_history = [
            {
                "role": "assistant",
                "content": answer,
                "semantic_context": state,
            }
        ]
        monthly_plan = asyncio.run(
            compile_analysis_plan(
                prompt="Y por mes para ese cliente?",
                user_id="",
                semantic_catalog=catalog,
                metric_catalog=metrics,
                context={"surface": "chat", "conversation_history": continued_history},
                use_llm=False,
            )
        )
        monthly_query = monthly_plan["queries"][0]["query"]
        self.assertNotIn("dimensions", monthly_query)
        self.assertEqual(monthly_query["filters"], query["filters"])
        self.assertEqual(
            monthly_query["timeDimensions"],
            [{"dimension": "FactVentas.fecha", "granularity": "month"}],
        )

    def test_legacy_text_history_requires_entity_confirmation(self):
        catalog, metrics, _ = semantic_fixture()
        legacy_history = [{
            "role": "assistant",
            "content": (
                "Comparacion por nombre razonsocial:\n\n"
                "1. Gastronomica del Plata 17: 297.944,64 (Tiempo promedio entre ventas: 3,05 dias)\n\n"
                "Lectura: Gastronomica del Plata 17 lidera el ranking por Monto Total de Venta."
            ),
        }]
        plan = asyncio.run(
            compile_analysis_plan(
                prompt="decime el tiempo entre venta y venta para ese cliente",
                user_id="",
                semantic_catalog=catalog,
                metric_catalog=metrics,
                context={"surface": "chat", "conversation_history": legacy_history},
                use_llm=False,
            )
        )
        self.assertEqual(plan["queries"], [])
        self.assertIn("referís", plan["clarification"])

    def test_generic_sales_word_does_not_select_transaction_count(self):
        _, _, graph = semantic_fixture()
        self.assertIsNone(_explicit_catalog_metric("ventas", graph))
        self.assertIsNone(infer_sales_activity_query("ventas", graph))

    def test_business_metadata_is_sent_to_llm_planner(self):
        _, _, graph = semantic_fixture()
        payload = _catalog_payload(graph)
        custom = next(metric for metric in payload["metrics"] if metric["key"] == CUSTOM_KEY)
        self.assertEqual(custom["business_area"], "Ventas")
        self.assertIn("primera", custom["business_formula"].lower())
        self.assertEqual(custom["aliases"], ["cadencia de compra"])

    def test_custom_metric_order_is_applied_after_computation(self):
        rows = [
            {CLIENT_KEY: "Cliente B", CUSTOM_KEY: 4.1},
            {CLIENT_KEY: "Cliente A", CUSTOM_KEY: 2.9},
            {CLIENT_KEY: "Sin datos", CUSTOM_KEY: None},
        ]
        result = apply_post_compute_order(rows, {CUSTOM_KEY: "asc"}, limit=1)
        self.assertEqual(result, [{CLIENT_KEY: "Cliente A", CUSTOM_KEY: 2.9}])

    def test_grouped_answer_honors_ascending_order(self):
        query = {
            "measures": [CUSTOM_KEY],
            "dimensions": [CLIENT_KEY],
            "order": {CUSTOM_KEY: "asc"},
            "limit": 1,
        }
        result = {
            "data": [
                {CLIENT_KEY: "Cliente B", CUSTOM_KEY: 4.1},
                {CLIENT_KEY: "Cliente A", CUSTOM_KEY: 2.9},
            ]
        }
        answer = format_grouped_metric_answer(
            "cliente con menor tiempo entre ventas",
            query,
            result,
            {CUSTOM_KEY: {"name": "Tiempo promedio entre ventas", "format": "duration_days"}},
        )
        self.assertIn("1. **Cliente A**: **2,90 días**", answer)
        self.assertIn("de menor a mayor", answer)

    def test_best_customer_answer_leads_with_requested_metric(self):
        query = {
            "measures": [CUSTOM_KEY, AMOUNT_KEY],
            "dimensions": [CLIENT_KEY],
            "order": {AMOUNT_KEY: "desc"},
            "limit": 1,
        }
        result = {
            "data": [{CLIENT_KEY: "Gastronomica del Plata 17", CUSTOM_KEY: 3.05, AMOUNT_KEY: 297944.64}],
        }
        metadata = {
            CUSTOM_KEY: {"name": "Tiempo promedio entre ventas", "format": "duration_days"},
            AMOUNT_KEY: {"name": "Monto Total de Venta", "format": "currency"},
        }
        answer = format_grouped_metric_answer(
            "tiempo entre venta y venta para mi mejor cliente",
            query,
            result,
            metadata,
        )
        self.assertIn("Tiempo promedio entre ventas", answer)
        self.assertIn("3,05 días", answer)
        self.assertIn("mejor cliente", answer)
        self.assertIn("$297.944,64", answer)
        self.assertNotIn("Comparacion por", answer)

        semantic_context = build_semantic_conversation_context(query, result, metadata)
        self.assertEqual(
            semantic_context["selected_entities"],
            [{"member": CLIENT_KEY, "value": "Gastronomica del Plata 17"}],
        )
        self.assertEqual(semantic_context["primary_measure"], CUSTOM_KEY)
        self.assertEqual(semantic_context["selection_measure"], AMOUNT_KEY)

    def test_duplicate_metric_proposal_returns_existing_key(self):
        _, metrics, _ = semantic_fixture()
        compiled = {
            "compiled_expression": "m0",
            "variables": {"m0": CUSTOM_KEY},
        }
        proposal = {"name": "Tiempo promedio entre ventas"}
        self.assertEqual(_metric_proposal_already_exists(metrics, proposal, compiled), CUSTOM_KEY)

    def test_legacy_repair_replaces_semantically_wrong_hardcoded_measure(self):
        catalog, metrics, _ = semantic_fixture()
        safe_query = {
            "measures": [CUSTOM_KEY],
            "dimensions": [CLIENT_KEY],
            "order": {CUSTOM_KEY: "asc"},
            "limit": 1,
        }
        wrong_query = {
            "measures": [COUNT_KEY],
            "dimensions": [CLIENT_KEY],
            "limit": 1,
        }
        with (
            patch("services.semantic_catalog.fetch_semantic_catalog", new=AsyncMock(return_value=catalog)),
            patch("api.chat.build_metric_catalog", new=AsyncMock(return_value=metrics)),
            patch("api.chat.infer_semantic_query_from_catalog", new=AsyncMock(return_value=safe_query)),
        ):
            repaired = asyncio.run(
                repair_semantic_query_from_catalog(
                    wrong_query,
                    "cliente con menor tiempo entre ventas",
                    "user",
                )
            )
        self.assertEqual(repaired, safe_query)


if __name__ == "__main__":
    unittest.main()
