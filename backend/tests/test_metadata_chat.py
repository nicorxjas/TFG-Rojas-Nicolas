"""Domain-independent regressions for definitions, routing and Codex effort."""
import asyncio
import json
import os
import threading
import unittest
import httpx
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from api.chat import build_runtime_system_prompt, classify_chat_intent, _fallback_chat_intent, prepare_chat_analysis
from services.codex_llm import CodexAppServer
from api.semantic_metrics import create_missing_metric_draft_from_prompt, _infer_metric_resolution_with_llm
from services.semantic_planner import _catalog_payload


class MetadataChatTests(unittest.TestCase):
    def test_explicit_creation_opens_definition_before_analytical_clarification(self):
        suggestion = {"resolution_status": "missing", "requires_definition": True, "name": "Continuidad"}
        with patch("api.chat.create_missing_metric_draft_from_prompt", new=AsyncMock(return_value=suggestion)), patch(
            "api.chat.compile_analysis_plan", new=AsyncMock()
        ) as planner:
            plan, result = asyncio.run(prepare_chat_analysis("Creá una métrica de continuidad", "u", "c", [], "data"))
        self.assertEqual(result, suggestion)
        self.assertEqual(plan["queries"], [])
        planner.assert_not_awaited()

    def test_formula_with_unverified_business_assumptions_requires_definition(self):
        for gap_key in ("assumptions", "missing_components"):
            response = {"status": "missing", "name": "Indice ajustado", "expression": "@Model.a / @Model.b",
                        gap_key: ["Alcance de los ajustes no documentado"]}
            transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps(response)}}]
            }))
            with patch("api.semantic_metrics.llm_client", side_effect=lambda **kwargs: httpx.AsyncClient(transport=transport)), patch(
                "api.semantic_metrics.llm_is_configured", return_value=True
            ):
                result = asyncio.run(_infer_metric_resolution_with_llm(
                    prompt="Indice ajustado", metric_catalog=[], company_context={}, connection_id="c"
                ))
            self.assertEqual(result["status"], "insufficient")
            self.assertTrue(result["suggestion"]["requires_definition"])
            self.assertEqual(result["suggestion"]["expression"], "")

    def test_planner_does_not_silently_hide_late_catalog_members(self):
        graph = {"metrics": [{"key": f"Model.m{i}"} for i in range(170)],
                 "dimensions": [{"key": f"Model.d{i}"} for i in range(190)],
                 "time_dimensions": [{"key": f"Model.t{i}"} for i in range(70)],
                 "relationships": [{"from_cube": f"Model{i}", "to_cube": "Dimension"} for i in range(170)]}
        payload = _catalog_payload(graph)
        self.assertEqual(payload["metrics"][-1]["key"], "Model.m169")
        self.assertEqual(payload["dimensions"][-1]["key"], "Model.d189")
        self.assertEqual(payload["timeDimensions"][-1]["key"], "Model.t69")
        self.assertEqual(len(payload["relationships"]), 170)

    def test_uncompilable_new_formula_still_offers_definition_menu(self):
        proposal = {"name": "Continuidad", "expression": "unknown(Missing.value)"}
        for retry in [{"status": "unavailable"}, {"status": "missing", "proposal": proposal}]:
            with patch("api.semantic_metrics.fetch_semantic_catalog", new=AsyncMock(return_value={})), patch(
                "api.semantic_metrics.build_metric_catalog", new=AsyncMock(return_value=[])
            ), patch("api.semantic_metrics.fetch_custom_metrics", new=AsyncMock(return_value=[])), patch(
                "api.semantic_metrics.fetch_company_context", new=AsyncMock(return_value={})
            ), patch("api.semantic_metrics._infer_metric_resolution_with_llm", new=AsyncMock(side_effect=[
                {"status": "missing", "proposal": proposal}, retry
            ])), patch("api.semantic_metrics.sb.rest_post", new=AsyncMock()) as write:
                result = asyncio.run(create_missing_metric_draft_from_prompt(prompt="Continuidad", user_id="u"))
            self.assertEqual(result["resolution_status"], "missing")
            self.assertTrue(result["requires_definition"])
            self.assertEqual(result["expression"], "")
            write.assert_not_awaited()

    def test_guidance_receives_company_definition_not_only_metric_name(self):
        for name, definition in [
            ("Continuidad asistencial", "Episodios con seguimiento / episodios elegibles; excluye derivaciones."),
            ("Disponibilidad tecnica", "Minutos disponibles / minutos programados; excluye mantenimiento acordado."),
            ("Permanencia estudiantil", "Alumnos reinscritos / cohorte inicial; excluye egresados."),
        ]:
            with self.subTest(name=name), patch("api.chat.fetch_company_context", new=AsyncMock(return_value={})), patch(
                "api.semantic_metrics.build_metric_catalog", new=AsyncMock(return_value=[{
                    "key": "Metricas.validated", "name": name, "description": definition,
                    "business_formula": "numerador / denominador", "format": "percent",
                    "aliases": ["indicador acordado"], "source": "custom",
                }])
            ):
                prompt = asyncio.run(build_runtime_system_prompt("u", "c", surface="guidance"))
                self.assertIn(definition, prompt)
                self.assertIn("numerador / denominador", prompt)
                self.assertIn("indicador acordado", prompt)

    def test_definition_question_is_not_forced_into_data_by_cual_es(self):
        with patch("api.chat.post_llm_json", new=AsyncMock(return_value={"choices": [{"message": {
            "content": json.dumps({"mode": "guidance"})
        }}]})):
            intent = asyncio.run(classify_chat_intent(
                "¿Cuál es la definición de disponibilidad tecnica?", [], {}
            ))
        self.assertEqual(intent["mode"], "guidance")

    def test_explicit_metric_creation_reaches_semantic_resolution_on_outage(self):
        for prompt in ["Creá una métrica de permanencia", "Definí un KPI de continuidad", "Agregar una medida de disponibilidad"]:
            self.assertEqual(_fallback_chat_intent(prompt)["mode"], "data")

    def test_codex_passes_requested_effort_to_turn_and_uses_default_when_absent(self):
        for requested, expected in [("medium", "medium"), (None, "low")]:
            worker = CodexAppServer()
            worker._workspace = SimpleNamespace(name="unused-test-workspace")
            worker._models = {"test-model": {"supportedReasoningEfforts": [
                {"reasoningEffort": "low"}, {"reasoningEffort": "medium"}
            ]}}
            worker._disabled_mcp = {}
            calls = []

            def rpc(method, params, *args):
                calls.append((method, params))
                return {"thread": {"id": "t"}, "turn": {"id": "r"}}

            events = [
                {"method": "item/completed", "params": {"threadId": "t", "item": {
                    "type": "agentMessage", "phase": "final_answer", "text": "ok"
                }}},
                {"method": "turn/completed", "params": {"threadId": "t", "turn": {
                    "id": "r", "status": "completed"
                }}},
            ]
            with patch.object(worker, "_start"), patch.object(worker, "_rpc", side_effect=rpc), patch.object(
                worker, "_next", side_effect=events
            ), patch.dict(os.environ, {"CODEX_REASONING_EFFORT": "low"}):
                worker._complete_sync({"model": "test-model", "reasoning_effort": requested}, 10, threading.Event())
            self.assertEqual(next(params for method, params in calls if method == "turn/start")["effort"], expected)
