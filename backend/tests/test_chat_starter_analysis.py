import asyncio
import json
import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from api.chat import ChatRequest, chat_with_data, starter_analysis_prompt
from services.semantic_graph import build_semantic_graph
from services.semantic_planner import _recommendation_fallback_plan, _weekly_sales_plan, compile_analysis_plan
from test_semantic_metric_routing import semantic_fixture, CLIENT_KEY, AMOUNT_KEY, COUNT_KEY, CUSTOM_KEY


class StarterAnalysisTests(unittest.TestCase):
    def test_weekly_sales_has_explicit_previous_complete_week(self):
        for today in (date(2026, 11, 9), date(2026, 11, 15)):
            prompt = starter_analysis_prompt("weekly_sales", today)
            self.assertIn("2026-11-02 al 2026-11-08", prompt)

    def test_weekly_plan_scopes_sales_and_excludes_unrelated_interval_metric(self):
        _, _, graph = semantic_fixture()
        plan = _weekly_sales_plan(graph, ["2026-11-02", "2026-11-08"])
        self.assertEqual(len(plan["queries"]), 3)
        for spec in plan["queries"]:
            self.assertEqual(set(spec["query"]["measures"]), {AMOUNT_KEY, COUNT_KEY})
            self.assertNotIn(CUSTOM_KEY, spec["query"]["measures"])
        self.assertEqual(plan["queries"][1]["query"]["timeDimensions"][0]["granularity"], "day")
        self.assertEqual(plan["queries"][2]["query"]["timeDimensions"][0]["dateRange"], ["2026-10-26", "2026-11-01"])

    def test_weekly_starter_compiles_even_when_llm_planner_cannot_validate(self):
        catalog, metrics, _ = semantic_fixture()
        with patch("services.semantic_planner._llm_plan", new=AsyncMock(return_value={
            "queries": [], "clarification": "No pude validar una consulta completa. Indicame la métrica y el alcance que querés analizar.",
        })) as llm:
            plan = asyncio.run(compile_analysis_plan(
                prompt=starter_analysis_prompt("weekly_sales", date(2026, 11, 10)),
                user_id="u", connection_id="c", semantic_catalog=catalog, metric_catalog=metrics,
                context={"surface": "recommendation", "starter": "weekly_sales", "business_context": "Ventas"},
            ))
        llm.assert_not_awaited()
        self.assertFalse(plan.get("clarification"), plan)
        self.assertFalse(plan.get("validation_errors"), plan)
        self.assertEqual(len(plan["queries"]), 3)
        self.assertIn(AMOUNT_KEY, plan["metric_metadata"])
        self.assertEqual(plan["queries"][0]["query"]["timeDimensions"][0]["dateRange"], ["2026-11-02", "2026-11-08"])

    def test_churn_fallback_queries_customers_and_last_purchase(self):
        catalog, metrics, _ = semantic_fixture()
        graph = build_semantic_graph(catalog, metrics)
        plan = _recommendation_fallback_plan(starter_analysis_prompt("churn"), graph, None)
        self.assertEqual(len(plan["queries"]), 1)
        query = plan["queries"][0]["query"]
        self.assertEqual(query["dimensions"], [CLIENT_KEY])
        self.assertIn("FactVentas.fecha_max", query["measures"])

    def test_cards_execute_queries_and_narrate_analysis_without_actions_contract(self):
        async def run(starter):
            query = {"measures": [AMOUNT_KEY], "dimensions": [CLIENT_KEY]}
            evidence = {"query": query, "data": [{CLIENT_KEY: "Cliente real", AMOUNT_KEY: 1200}],
                        "metric_metadata": {AMOUNT_KEY: {"name": "Ventas"}}}

            async def narrate(messages, headers, **kwargs):
                self.assertIn("Cliente real", json.dumps(messages, ensure_ascii=False))
                yield "El cliente real registra ventas por 1.200 en el alcance consultado."

            with (
                patch("api.chat.llm_is_configured", return_value=True),
                patch("api.chat.get_llm_headers", return_value={}),
                patch("api.chat.user_id_from_authorization", return_value="u"),
                patch("api.chat.build_runtime_system_prompt", new=AsyncMock(return_value="Empresa")),
                patch("api.chat.classify_chat_intent", new=AsyncMock()) as classify,
                patch("api.chat.prepare_chat_analysis", new=AsyncMock(return_value=({"queries": [{"query": query}]}, None))) as prepare,
                patch("api.chat.execute_analysis_plan", new=AsyncMock(return_value={
                    "evidence": [evidence], "evidence_digest": [{**evidence, "sample_rows": evidence["data"]}],
                })) as execute,
                patch("api.chat.generate_verified_recommendations", new=AsyncMock()) as recommend,
                patch("api.chat.stream_llm_answer", new=narrate),
            ):
                response = await chat_with_data(ChatRequest(prompt="Texto de la tarjeta", starter=starter), authorization="Bearer test")
                events = [json.loads(event.removeprefix("data: ").strip()) async for event in response.body_iterator]
                execute.assert_awaited_once()
                classify.assert_not_awaited()
                recommend.assert_not_awaited()
                self.assertEqual(prepare.call_args.kwargs["starter"], starter)
                self.assertIn("consult", prepare.call_args.args[0])
                self.assertTrue(any(event.get("type") == "chunk" and "1.200" in event["content"] for event in events))
                self.assertEqual(events[-1]["type"], "done")

        for starter in ("weekly_sales", "churn"):
            with self.subTest(starter=starter):
                asyncio.run(run(starter))


if __name__ == "__main__":
    unittest.main()
