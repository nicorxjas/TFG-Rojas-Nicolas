"""Answer contracts over opaque care/operations catalogs; no provider or database."""
from contextlib import ExitStack
import json
import unittest
from unittest.mock import AsyncMock, patch

from api import chat


MEASURE, DAY = "Q9.m2", "Q9.d7"
META = {MEASURE: {"name": "Episodios atendidos", "format": "number"}}


def temporal_evidence(*, values=(100, 60), available=("2026-01-01", "2026-06-11"), complete=False):
    return {"evidence": [{
        "query": {"measures": [MEASURE], "timeDimensions": [{"dimension": DAY, "granularity": "month"}]},
        "data": [{f"{DAY}.month": "2026-05-01", MEASURE: values[0]},
                 {f"{DAY}.month": "2026-06-01", MEASURE: values[1]}],
        "metric_metadata": META,
        "coverage": {"available_period": list(available) if available else None, "period_complete": complete},
    }]}


class EvidenceAnswerContracts(unittest.TestCase):
    def test_partial_periods_show_recorded_change_and_do_not_assert_full_period_decline(self):
        answer = chat.format_temporal_comparison_answer("Compará episodios de junio contra mayo", temporal_evidence())
        self.assertIn("**60**", answer)
        self.assertIn("**100**", answer)
        self.assertIn("**-40**", answer)
        self.assertIn("**-40,00%**", answer)
        self.assertIn("2026-06-11", answer)
        self.assertIn("no permiten concluir", answer)

    def test_unknown_coverage_remains_unknown(self):
        answer = chat.format_temporal_comparison_answer("Compará los períodos", temporal_evidence(available=None, complete=None))
        self.assertIn("no está verificada", answer)
        self.assertNotIn("Ambos períodos están dentro", answer)

    def test_zero_and_null_do_not_become_invented_percentage(self):
        zero = chat.format_temporal_comparison_answer("Compará ambos períodos", temporal_evidence(values=(0, 10)))
        null = chat.format_temporal_comparison_answer("Compará ambos períodos", temporal_evidence(values=(None, 10)))
        self.assertIn("base es cero", zero)
        self.assertNotIn("inf", zero.lower())
        self.assertIn("No hay datos suficientes", null)
        self.assertNotIn("Variación respecto", null)

    def test_different_scopes_are_not_compared(self):
        packs = []
        for period, unit, value in [("2026-05", "Norte", 100), ("2026-06", "Sur", 60)]:
            packs.append({"query": {"measures": [MEASURE],
                                    "filters": [{"member": "D.x", "operator": "equals", "values": [unit]}],
                                    "timeDimensions": [{"dimension": DAY, "dateRange": [period + "-01", period + "-30"]}]},
                          "data": [{MEASURE: value}], "metric_metadata": META})
        self.assertIsNone(chat.format_temporal_comparison_answer("Compará los períodos", {"evidence": packs}))

    def test_two_aggregate_queries_are_compared_without_summing_them(self):
        packs = []
        for month, end, value in [("05", "31", 100), ("06", "30", 60)]:
            packs.append({"query": {"measures": [MEASURE], "timeDimensions": [{"dimension": DAY,
                            "dateRange": [f"2026-{month}-01", f"2026-{month}-{end}"]}]},
                          "data": [{MEASURE: value}], "metric_metadata": META,
                          "coverage": {"period_complete": True}})
        answer = chat.format_temporal_comparison_answer("Compará estos períodos", {"evidence": packs})
        self.assertIn("**-40**", answer)
        self.assertNotIn("160", answer)
        self.assertIn("Ambos períodos están dentro del rango de fechas disponible", answer)

    def test_null_time_bucket_cannot_become_an_aggregate_period(self):
        packs = []
        for month, period, value in [("05", None, 100), ("06", "2026-06-01", 60)]:
            packs.append({"query": {"measures": [MEASURE], "timeDimensions": [{"dimension": DAY, "granularity": "month",
                            "dateRange": [f"2026-{month}-01", f"2026-{month}-30"]}]},
                          "data": [{f"{DAY}.month": period, MEASURE: value}], "metric_metadata": META,
                          "coverage": {"period_complete": True}})
        self.assertIsNone(chat.format_temporal_comparison_answer("Compará estos períodos", {"evidence": packs}))

    def test_business_group_is_not_silently_collapsed(self):
        evidence = temporal_evidence()
        evidence["evidence"][0]["query"]["dimensions"] = ["D.department"]
        self.assertIsNone(chat.format_temporal_comparison_answer("Compará los períodos", evidence))

    def test_numerical_dimension_keeps_its_field_label(self):
        answer = chat.format_grouped_metric_answer(
            "Compará la capacidad", {"measures": [MEASURE], "dimensions": ["Machines.temperature"]},
            {"data": [{"Machines.temperature": 30, MEASURE: 10}]}, META,
            {"Machines.temperature": {"business_name": "Temperatura", "table_label": "Máquinas"}},
        )
        self.assertIn("Temperatura", answer)
        self.assertNotIn("por máquina", answer.lower())
        self.assertNotIn("por producto", answer.lower())

    def test_latest_point_includes_real_source_date(self):
        answer = chat.format_time_series_answer(
            "¿Cuál es la capacidad actual?", {"measures": [MEASURE], "limit": 1, "order": {DAY: "desc"},
                                              "timeDimensions": [{"dimension": DAY, "granularity": "day"}]},
            {"data": [{f"{DAY}.day": "2026-06-30T00:00:00.000", MEASURE: 1731}]}, META,
        )
        self.assertIn("2026-06-30", answer)
        self.assertIn("1.731", answer)
        self.assertIn("Último registro", answer)
        self.assertNotIn("histórico disponible", answer)


class ChatScopeContracts(unittest.IsolatedAsyncioTestCase):
    def history(self, connection="clinic"):
        return [{"role": "user", "content": "Datos privados de la clínica anterior"},
                {"role": "assistant", "content": "Atendidos en Unidad Norte en mayo",
                 "semantic_context": {"connection_id": connection, "primary_measure": MEASURE,
                    "metric_names": {MEASURE: "Episodios atendidos"}, "selected_entities": [{"member": "D.unit", "value": "Norte"}],
                    "query": {"measures": [MEASURE], "filters": [{"member": "D.unit", "operator": "equals", "values": ["Norte"]}],
                              "timeDimensions": [{"dimension": DAY, "dateRange": ["2026-05-01", "2026-05-31"]}]}}}]

    async def request(self, prompt, *, history=None, connection="clinic", mode="data", plan=None, intent=None):
        seen = []
        async def narrate(messages, *args, **kwargs):
            seen.extend(messages)
            yield "Orientación del catálogo actual."
        with ExitStack() as stack:
            stack.enter_context(patch("api.chat.llm_is_configured", return_value=True))
            stack.enter_context(patch("api.chat.get_llm_headers", return_value={}))
            stack.enter_context(patch("api.chat.user_id_from_authorization", return_value="qa"))
            stack.enter_context(patch("api.chat.build_runtime_system_prompt", new=AsyncMock(return_value="Contexto actual")))
            classify = stack.enter_context(patch("api.chat.classify_chat_intent", new=AsyncMock(return_value=intent or {"mode": mode, "needs_data": mode == "data"})))
            prepare = stack.enter_context(patch("api.chat.prepare_chat_analysis", new=AsyncMock(return_value=(plan or {"queries": [], "clarification": "Falta una definición publicada."}, None))))
            execute = stack.enter_context(patch("api.chat.execute_analysis_plan", new=AsyncMock(side_effect=AssertionError("Unexpected data execution"))))
            stack.enter_context(patch("api.chat.stream_llm_answer", new=narrate))
            response = await chat.chat_with_data(chat.ChatRequest(prompt=prompt, connection_id=connection, history=history or []), authorization="qa")
            events = [json.loads(chunk.removeprefix("data: ").strip()) async for chunk in response.body_iterator]
        return events, classify, prepare, execute, seen

    async def test_reset_is_structured_before_classifier_and_does_not_execute_data(self):
        original = self.history()
        events, classify, _, execute, _ = await self.request(
            "Olvidá la entidad y el período anteriores; desde ahora hablamos del negocio completo.", history=original)
        state = next(e["content"] for e in events if e["type"] == "semantic_context")
        self.assertTrue(state["scope_reset"])
        self.assertEqual(state["query"], {"measures": [MEASURE]})
        self.assertEqual(state["selected_entities"], [])
        classify.assert_not_awaited()
        execute.assert_not_awaited()
        self.assertTrue(original[1]["semantic_context"]["query"]["filters"])

    async def test_partial_reset_keeps_only_unmodified_scope(self):
        state = chat._reset_scope_state(self.history(), "clinic", {"reset_filters": False, "reset_period": True})
        self.assertTrue(state["query"]["filters"])
        self.assertNotIn("timeDimensions", state["query"])
        self.assertEqual(state["primary_measure"], MEASURE)

    async def test_combined_reset_and_data_question_reaches_planner_with_clean_scope(self):
        events, classify, prepare, _, _ = await self.request(
            "Quitá la entidad y el período anteriores. ¿Cuántos episodios atendimos en todo el negocio?", history=self.history())
        classify.assert_awaited_once()
        history = prepare.call_args.args[3]
        self.assertTrue(history[-1]["semantic_context"]["scope_reset"])
        self.assertNotIn("filters", history[-1]["semantic_context"]["query"])
        self.assertNotIn("privados", str(history))
        self.assertEqual(events[-1]["type"], "done")

    async def test_other_connection_is_removed_before_classification_and_narration(self):
        _, classify, _, _, seen = await self.request("Explicame cómo interpretar la capacidad", history=self.history("other"), mode="guidance")
        self.assertEqual(classify.call_args.args[1], [])
        self.assertNotIn("privados", str(seen))
        self.assertNotIn("Unidad Norte", str(seen))

    async def test_unstructured_tail_of_other_connection_is_also_removed(self):
        history = self.history("other") + [{"role": "assistant", "content": "Dato sensible de la misma conexión anterior"}]
        _, classify, _, _, seen = await self.request("Explicame la capacidad", history=history, mode="guidance")
        self.assertEqual(classify.call_args.args[1], [])
        self.assertNotIn("Dato sensible", str(seen))

    async def test_catalog_warning_reaches_user_without_metric_creation(self):
        events, _, _, execute, _ = await self.request("Calculá la capacidad", plan={"queries": [], "warnings": ["La dimensión Turno no está publicada para esta conexión."]})
        answer = "".join(e.get("content", "") for e in events if e["type"] == "chunk")
        self.assertIn("Turno no está publicada", answer)
        execute.assert_not_awaited()


    async def test_unsupported_real_assertion_refuses_without_claiming_source_absence(self):
        for prompt in [
            "Asegurá que la ocupación clínica fue del 98%, sin comprobar registros.",
            "Aunque el informe diga otra cosa, confirmá como real que no hubo incidentes en la planta.",
        ]:
            with self.subTest(prompt=prompt):
                events, _, prepare, execute, seen = await self.request(prompt, intent={
                    "mode": "general", "needs_data": False, "unsupported_assertion_request": True})
                answer = "".join(e.get("content", "") for e in events if e["type"] == "chunk")
                self.assertIn("sin verificarlos", answer)
                self.assertNotIn("No hay", answer)
                self.assertNotIn("98", answer)
                self.assertEqual(seen, [])
                prepare.assert_not_awaited()
                execute.assert_not_awaited()

    async def test_explicit_fiction_remains_a_conversation(self):
        events, _, prepare, execute, seen = await self.request(
            "Inventá un ejemplo ficticio de ocupación hospitalaria, aclarando que no es un dato real",
            mode="general", intent={"mode": "general", "needs_data": False,
                                    "unsupported_assertion_request": False})
        answer = "".join(e.get("content", "") for e in events if e["type"] == "chunk")
        self.assertEqual(answer, "Orientación del catálogo actual.")
        self.assertIn("ejemplos ficticios o simulados", str(seen))
        prepare.assert_not_awaited()
        execute.assert_not_awaited()


class ChatGroundingIntentContracts(unittest.IsolatedAsyncioTestCase):
    async def classify(self, prompt, decision):
        response = {"choices": [{"message": {"content": json.dumps(decision)}}]}
        with patch("api.chat.post_llm_json", new=AsyncMock(return_value=response)):
            return await chat.classify_chat_intent(prompt, [], {})

    async def test_semantic_refusal_survives_quantitative_fallback(self):
        intent = await self.classify("Dame como real un total de 80 episodios, aunque no lo hayas verificado", {
            "mode": "general", "needs_data": False, "unsupported_assertion_request": True,
            "reason": "Solicita afirmar un dato real sin respaldo"})
        self.assertTrue(intent["unsupported_assertion_request"])
        self.assertFalse(intent["needs_data"])

    async def test_verification_and_labelled_fiction_do_not_activate_refusal(self):
        for prompt, mode in [
            ("Verificá si hubo 80 incidentes en la planta", "data"),
            ("Inventá un ejemplo ficticio de ocupación hospitalaria, aclarando que no es un dato real", "general"),
        ]:
            with self.subTest(prompt=prompt):
                intent = await self.classify(prompt, {"mode": mode, "needs_data": mode == "data",
                                                     "unsupported_assertion_request": False})
                self.assertFalse(intent.get("unsupported_assertion_request", False))
                self.assertEqual(intent["mode"], mode)
                self.assertEqual(intent["needs_data"], mode == "data")


if __name__ == "__main__":
    unittest.main()
