"""Adversarial follow-ups must keep scope and never guess an ambiguous entity."""
import asyncio
import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, patch

from services.semantic_planner import compile_analysis_plan
from test_contextual_business_chat import contextual_fixture, TICKET
from test_semantic_metric_routing import AMOUNT_KEY, CLIENT_KEY, COUNT_KEY


class EnterpriseConversationTests(unittest.TestCase):
    def setUp(self):
        self.catalog, self.metrics = contextual_fixture()
        self.query = {
            "measures": [TICKET, AMOUNT_KEY], "dimensions": [CLIENT_KEY],
            "order": {AMOUNT_KEY: "desc"}, "limit": 3,
            "filters": [{"member": CLIENT_KEY, "operator": "equals", "values": ["Cliente A"]}],
            "timeDimensions": [{"dimension": "FactVentas.fecha", "dateRange": ["2026-01-01", "2026-01-31"]}],
        }
        self.state = {"connection_id": "c", "query": self.query, "primary_measure": TICKET,
                      "selected_entities": [{"member": CLIENT_KEY, "value": "Cliente A"}]}

    def plan(self, prompt, *, state=None, connection="c", raw_plan=None):
        with patch("services.semantic_planner._llm_plan", new=AsyncMock(return_value=raw_plan)):
            return asyncio.run(compile_analysis_plan(
                prompt=prompt, user_id="", connection_id=connection,
                semantic_catalog=self.catalog, metric_catalog=self.metrics,
                context={"conversation_history": [{"role": "assistant", "semantic_context": state or self.state}]},
            ))

    def test_period_only_followup_keeps_filters_measures_ranking_and_limit(self):
        for prompt in ["¿Y en mayo de 2026?", "Ahora en mayo de 2026"]:
            with self.subTest(prompt=prompt):
                query = self.plan(prompt)["queries"][0]["query"]
                for key in ["filters", "measures", "dimensions", "order", "limit"]:
                    self.assertEqual(query.get(key), self.query[key])
                self.assertEqual(query["timeDimensions"][0]["dateRange"], ["2026-05-01", "2026-05-31"])

    def test_period_reset_keeps_customer_and_removes_only_period(self):
        query = self.plan("¿Y en todo el histórico?")["queries"][0]["query"]
        self.assertEqual(query["filters"], self.query["filters"])
        self.assertEqual(query["measures"], self.query["measures"])
        self.assertFalse(any(item.get("dateRange") for item in query.get("timeDimensions", [])))

    def test_period_followup_repairs_llm_that_loses_customer(self):
        raw = {"queries": [{"query": {"measures": [TICKET]}}]}
        query = self.plan("¿Y en mayo de 2026?", raw_plan=raw)["queries"][0]["query"]
        self.assertEqual(query["filters"], self.query["filters"])

    def test_period_followup_preserves_existing_time_breakdown(self):
        state = deepcopy(self.state)
        state["query"]["timeDimensions"][0]["granularity"] = "month"
        query = self.plan("¿Y en 2025?", state=state)["queries"][0]["query"]
        self.assertEqual(query["timeDimensions"][0]["granularity"], "month")
        self.assertEqual(query["timeDimensions"][0]["dateRange"], ["2025-01-01", "2025-12-31"])

    def test_period_followup_does_not_cross_connection(self):
        plan = self.plan("¿Y en mayo de 2026?", connection="other")
        self.assertEqual(plan["queries"], [])
        self.assertTrue(plan.get("clarification"))

    def test_period_followup_does_not_reuse_stale_catalog(self):
        state = deepcopy(self.state)
        state["catalog_fingerprint"] = "stale-catalog"
        plan = self.plan("¿Y en mayo de 2026?", state=state)
        self.assertEqual(plan["queries"], [])
        self.assertTrue(plan.get("clarification"))

    def test_period_edit_preserves_nested_boolean_filters_without_mutating_history(self):
        state = deepcopy(self.state)
        state["query"]["filters"] = [{"or": [
            {"member": CLIENT_KEY, "operator": "equals", "values": ["Cliente A"]},
            {"member": CLIENT_KEY, "operator": "equals", "values": ["Cliente B"]},
        ]}]
        original = deepcopy(state)
        query = self.plan("¿Y en mayo de 2026?", state=state)["queries"][0]["query"]
        self.assertEqual(query["filters"], original["query"]["filters"])
        self.assertEqual(state, original)

    def test_new_metric_and_customer_with_period_are_not_mistaken_for_period_only_edit(self):
        replacement = {"member": CLIENT_KEY, "operator": "equals", "values": ["Cliente B"]}
        query = self.plan("Ahora Monto Total de Venta de Cliente B en mayo de 2026", raw_plan={
            "queries": [{"query": {"measures": [AMOUNT_KEY], "filters": [replacement]}}],
        })["queries"][0]["query"]
        self.assertEqual(query["measures"], [AMOUNT_KEY])
        self.assertEqual(query["filters"], [replacement])
        self.assertEqual(query["timeDimensions"][0]["dateRange"], ["2026-05-01", "2026-05-31"])

    def test_plural_ranking_respects_requested_count(self):
        for prompt, count in [("Los 3 mejores clientes según Monto Total de Venta", 3),
                              ("Los 12 clientes con mayor Monto Total de Venta", 12)]:
            with self.subTest(prompt=prompt):
                query = self.plan(prompt)["queries"][0]["query"]
                self.assertEqual(query["limit"], count)

    def test_ambiguous_singular_customer_requests_clarification(self):
        state = deepcopy(self.state)
        state["selected_entities"].append({"member": CLIENT_KEY, "value": "Cliente B"})
        plan = self.plan("Ticket promedio de ese cliente", state=state)
        self.assertEqual(plan["queries"], [])
        self.assertTrue(plan.get("clarification"))

    def test_explicit_customer_change_is_not_overridden_by_previous_customer(self):
        replacement = {"member": CLIENT_KEY, "operator": "equals", "values": ["Cliente B"]}
        query = self.plan("Ticket promedio de Cliente B", raw_plan={"queries": [{"query": {
            "measures": [TICKET], "filters": [replacement]}}]})["queries"][0]["query"]
        self.assertEqual(query["filters"], [replacement])

    def test_metric_only_followup_preserves_unambiguous_customer_and_period(self):
        raw = {"queries": [{"query": {"measures": [COUNT_KEY]}}]}
        for prompt in ["¿Y la cantidad de ventas?", "¿Y el ticket promedio de ventas?"]:
            with self.subTest(prompt=prompt):
                query = self.plan(prompt, raw_plan=raw)["queries"][0]["query"]
                expected = COUNT_KEY if "cantidad" in prompt else TICKET
                self.assertEqual(query["measures"], [expected])
                self.assertEqual(query["filters"], self.query["filters"])
                self.assertEqual(query["timeDimensions"], self.query["timeDimensions"])
                self.assertFalse(query.get("dimensions"))

    def test_metric_only_followup_does_not_guess_between_selected_customers(self):
        state = deepcopy(self.state)
        state["selected_entities"].append({"member": CLIENT_KEY, "value": "Cliente B"})
        plan = self.plan("¿Y la cantidad de ventas?", state=state)
        self.assertEqual(plan["queries"], [])
        self.assertTrue(plan.get("clarification"))

    def test_metric_only_followup_does_not_reuse_other_connection_or_missing_state(self):
        for state, connection in [(self.state, "other"), ({"connection_id": "c"}, "c")]:
            with self.subTest(connection=connection, state=state):
                plan = self.plan("¿Y la cantidad de ventas?", state=state, connection=connection)
                self.assertEqual(plan["queries"], [])
                self.assertTrue(plan.get("clarification"))

    def test_metric_followup_with_explicit_different_customer_uses_new_customer(self):
        replacement = {"member": CLIENT_KEY, "operator": "equals", "values": ["Cliente B"]}
        query = self.plan("¿Y la cantidad de ventas de Cliente B?", raw_plan={"queries": [{"query": {
            "measures": [COUNT_KEY], "filters": [replacement]}}]})["queries"][0]["query"]
        self.assertEqual(query["filters"], [replacement])
        self.assertEqual(query["measures"], [COUNT_KEY])


if __name__ == "__main__":
    unittest.main()
