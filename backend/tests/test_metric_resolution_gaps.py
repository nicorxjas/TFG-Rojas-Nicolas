"""An incomplete definition must never publish an executable formula."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from api.semantic_metrics import _infer_metric_resolution_with_llm


class MetricResolutionGapTests(unittest.TestCase):
    def test_missing_and_insufficient_statuses_use_declared_gaps_instead_of_guessed_formula(self):
        for status in ("missing", "insufficient"):
            with self.subTest(status=status):
                raw = {"status": status, "name": "Energía equivalente", "description": "Conversión de unidades",
                       "expression": "@Z.a * @Z.b", "format": "number",
                       "proposed_calculation": "Multiplicar la lectura por la tasa",
                       "missing_components": ["Unidad de origen y destino"],
                       "assumptions": ["Orientación y escala de la tasa"]}
                response = Mock()
                response.json.return_value = {"choices": [{"message": {"content": json.dumps(raw)}}]}
                client = SimpleNamespace(post=AsyncMock(return_value=response))
                manager = AsyncMock()
                manager.__aenter__.return_value = client
                with patch("api.semantic_metrics.llm_is_configured", return_value=True), \
                     patch("api.semantic_metrics.llm_client", return_value=manager):
                    result = asyncio.run(_infer_metric_resolution_with_llm(
                        prompt="Convertir las lecturas", metric_catalog=[], company_context={}, connection_id="test",
                        original_request="Energía equivalente incluyendo pérdidas y ajustes del equipo, en la escala final.",
                        available_fields=[{'semantic_key': 'Z.threshold', 'business_name': 'Umbral configurado', 'data_type': 'string'},
                                          {'semantic_key': 'Z.hidden', 'business_name': 'Reservado', 'is_hidden': True}]))
                self.assertEqual(result["status"], "insufficient")
                suggestion = result["suggestion"]
                self.assertEqual(suggestion["expression"], "")
                self.assertTrue(suggestion["requires_definition"])
                self.assertIn("Unidad de origen y destino", suggestion["proposed_calculation"])
                self.assertIn("Orientación y escala", suggestion["proposed_calculation"])
                self.assertNotIn("Multiplicar", suggestion["proposed_calculation"])
                sent = client.post.call_args.kwargs['json']['messages'][1]['content']
                self.assertIn('Umbral configurado', sent)
                self.assertIn('string', sent)
                self.assertNotIn('Z.hidden', sent)
                self.assertIn('incluyendo pérdidas y ajustes del equipo', sent)


if __name__ == "__main__":
    unittest.main()
