import unittest

from services.recommendation_evidence import recommendation_facts, render_recommendations


MEASURE = "Q8.x17"
DIMENSION = "D4.v3"
PERIOD = "Z2.p9"


def evidence(query, rows, **extra):
    return {
        "query": {"measures": [MEASURE], **query},
        "sample_rows": rows,
        "metric_metadata": {MEASURE: {"name": "Energía registrada", "unit": "kWh"}},
        **extra,
    }


def render(facts, references=None):
    return render_recommendations({"actions": [{
        "title": "Verificar el alcance",
        "proposal": "Revisar los registros asociados a la observación.",
        "hypothesis": "La revisión podría mejorar la calidad de la evidencia.",
        "fact_ids": references or [facts[0]["id"]],
        "monitoring_measures": [MEASURE],
    }]}, facts, lambda measure, value, metadata: str(value))


class RecommendationScopeTests(unittest.TestCase):
    def test_null_clinical_group_is_retained_and_never_rendered_as_global(self):
        facts = recommendation_facts([evidence(
            {"dimensions": [DIMENSION]}, [{DIMENSION: None, MEASURE: 12}],
            field_metadata={DIMENSION: {"business_name": "Centro clínico", "field_kind": "dimension", "data_type": "string"}},
        )])
        scope = facts[0]["scope"]
        self.assertTrue(scope["grouped"])
        self.assertEqual(scope["dimensions"][0]["member"], DIMENSION)
        self.assertIsNone(scope["dimensions"][0]["value"])
        self.assertTrue(scope["dimensions"][0]["missing"])
        self.assertIn("no es un total global", " ".join(scope["qualification"]))
        answer = render(facts)
        self.assertIn("Grupo sin dato (Centro clínico)", answer)
        self.assertNotIn("Negocio:", answer)
        self.assertNotIn("Total consultado:", answer)

    def test_mixed_energy_groups_preserve_null_binding_and_returned_amount(self):
        second = "R7.z1"
        facts = recommendation_facts([evidence(
            {"dimensions": [DIMENSION, second]},
            [{DIMENSION: "Planta Norte", second: None, MEASURE: "17.25"}],
            field_metadata={second: {"name": "Circuito", "data_type": "string"}},
        )])
        self.assertEqual(facts[0]["scope"]["entities"], ["Planta Norte"])
        self.assertEqual(facts[0]["value"], "17.25")
        answer = render(facts)
        self.assertIn("Planta Norte / Grupo sin dato (Circuito)", answer)
        self.assertIn("**17.25**", answer)

    def test_null_bucket_does_not_inherit_requested_period_or_raw_date(self):
        facts = recommendation_facts([evidence(
            {"timeDimensions": [{"dimension": PERIOD, "granularity": "month", "dateRange": ["2026-01-01", "2026-03-31"]}]},
            [{PERIOD + ".month": None, PERIOD: "2026-02-01", MEASURE: 8}],
            field_metadata={PERIOD: {"name": "Mes observado", "field_kind": "time"}},
        )])
        scope = facts[0]["scope"]
        self.assertTrue(scope["grouped"])
        self.assertEqual(scope["periods"], [])
        binding = scope["time_dimensions"][0]
        self.assertIsNone(binding["value"])
        self.assertEqual(binding["granularity"], "month")
        self.assertEqual(binding["returned_member"], PERIOD + ".month")
        self.assertEqual(binding["date_range"], ["2026-01-01", "2026-03-31"])
        answer = render(facts)
        self.assertIn("Grupo temporal", answer)
        self.assertIn("fecha sin dato", answer)
        self.assertNotIn("histórico disponible", answer)
        self.assertNotIn("2026-02-01", answer)
        self.assertNotIn("Total consultado", answer)

    def test_opaque_temporal_string_dimension_is_a_period_using_metadata(self):
        facts = recommendation_facts([evidence(
            {"dimensions": [PERIOD]}, [{PERIOD: "Semana epidemiológica Alfa", MEASURE: 3}],
            field_metadata={PERIOD: {"name": "Semana registrada", "field_kind": "time", "data_type": "string"}},
        )])
        scope = facts[0]["scope"]
        self.assertEqual(scope["entities"], [])
        self.assertEqual(scope["periods"], ["Semana epidemiológica Alfa"])
        self.assertTrue(scope["dimensions"][0]["temporal"])
        answer = render(facts)
        self.assertIn("Grupo temporal", answer)
        self.assertIn("Semana epidemiológica Alfa", answer)

    def test_year_month_detected_by_format_with_opaque_key(self):
        for field_metadata in ({}, {PERIOD: {"field_kind": "dimension", "data_type": "string", "format_string": "yyyy-MM"}}):
            with self.subTest(metadata=field_metadata):
                facts = recommendation_facts([evidence(
                    {"dimensions": [PERIOD]}, [{PERIOD: "2026-06", MEASURE: 4}],
                    field_metadata=field_metadata,
                )])
                self.assertEqual(facts[0]["scope"]["periods"], ["2026-06"])
                self.assertEqual(facts[0]["scope"]["entities"], [])
                self.assertIn("2026-06", render(facts))

    def test_non_temporal_strings_and_declared_identifiers_remain_entities(self):
        samples = [
            ("Servicio 2026-06", {"field_kind": "dimension", "data_type": "string"}),
            ("2026-06", {"field_kind": "id", "data_type": "string"}),
            ("2026-06", {"semantic_type": "code", "data_type": "string"}),
            ("2026-99", {}),
        ]
        for value, metadata in samples:
            with self.subTest(value=value, metadata=metadata):
                facts = recommendation_facts([evidence(
                    {"dimensions": [DIMENSION]}, [{DIMENSION: value, MEASURE: 6}],
                    field_metadata={DIMENSION: metadata},
                )])
                self.assertEqual(facts[0]["scope"]["entities"], [value])
                self.assertEqual(facts[0]["scope"]["periods"], [])
                self.assertFalse(facts[0]["scope"]["dimensions"][0]["temporal"])

    def test_null_temporal_dimension_uses_metadata_to_preserve_missing_date(self):
        facts = recommendation_facts([evidence(
            {"dimensions": [PERIOD, DIMENSION]}, [{PERIOD: None, DIMENSION: "Sala Sur", MEASURE: 2}],
            field_metadata={PERIOD: {"field_kind": "time", "name": "Fecha de atención", "data_type": "date"}},
        )])
        scope = facts[0]["scope"]
        self.assertTrue(scope["dimensions"][0]["temporal"])
        self.assertIsNone(scope["dimensions"][0]["value"])
        self.assertEqual(scope["entities"], ["Sala Sur"])
        answer = render(facts)
        self.assertIn("Sala Sur", answer)
        self.assertIn("fecha sin dato", answer)
        self.assertNotIn("histórico disponible", answer)

    def test_total_without_grouping_is_legitimate_even_with_period_filter(self):
        facts = recommendation_facts([evidence(
            {"timeDimensions": [{"dimension": PERIOD, "dateRange": ["2026-05-01", "2026-05-31"]}]},
            [{MEASURE: 14}], coverage={"period_complete": True},
        )])
        scope = facts[0]["scope"]
        self.assertFalse(scope["grouped"])
        self.assertEqual(scope["dimensions"], [])
        answer = render(facts)
        self.assertIn("Total consultado: Energía registrada **14**", answer)
        self.assertIn("2026-05-01 a 2026-05-31", answer)
        self.assertNotIn("Grupo sin dato", answer)
        self.assertNotIn("no está verificada", answer)

    def test_incomplete_coverage_and_warnings_are_available_to_model_and_renderer(self):
        coverage = {
            "requested_period": ["2026-06-01", "2026-06-30"],
            "available_period": ["2026-01-01", "2026-06-11"],
            "period_complete": False, "temporal_dimension": PERIOD, "granularity": "month",
            "incompleteness_reason": "La fuente termina antes del cierre solicitado.",
        }
        warning = "La consulta devuelve una muestra acotada."
        facts = recommendation_facts([evidence(
            {"dimensions": [PERIOD]}, [{PERIOD: "2026-06", MEASURE: 9}],
            coverage=coverage, warnings=[warning],
        )])
        scope = facts[0]["scope"]
        self.assertEqual(scope["coverage"], coverage)
        self.assertEqual(scope["warnings"], [warning])
        self.assertIn("incompleta", " ".join(scope["qualification"]))
        answer = render(facts)
        self.assertIn("cobertura del período solicitado es incompleta", answer)
        self.assertIn("2026-06-11", answer)
        self.assertIn(coverage["incompleteness_reason"], answer)
        self.assertIn(warning, answer)
        self.assertNotIn("no está verificada", answer)

    def test_monthly_bucket_is_not_presented_as_a_single_recorded_day(self):
        facts = recommendation_facts([evidence(
            {"timeDimensions": [{"dimension": PERIOD, "granularity": "month"}]},
            [{PERIOD + ".month": "2026-06-01T00:00:00.000", MEASURE: 8}],
        )])
        self.assertEqual(facts[0]["scope"]["periods"], ["2026-06"])
        self.assertIn("(2026-06)", render(facts))
        self.assertNotIn("2026-06-01", render(facts))

    def test_fact_ids_and_returned_values_do_not_change_with_scope_classification(self):
        second_measure = "W9.f2"
        digest = [evidence(
            {"measures": [MEASURE, second_measure], "dimensions": [PERIOD, DIMENSION]},
            [{PERIOD: None, DIMENSION: None, MEASURE: "0", second_measure: None},
             {PERIOD: "2026-06", DIMENSION: "Equipo 3000", MEASURE: "7", second_measure: "2"}],
        )]
        facts = recommendation_facts(digest)
        self.assertEqual([fact["id"] for fact in facts], ["e0r0m0", "e0r1m1", "e0r1m2"])
        self.assertEqual([fact["value"] for fact in facts], ["0", "7", "2"])
        self.assertIsNone(facts[0]["scope"]["dimensions"][0]["value"])
        self.assertIn("**0**", render(facts))


if __name__ == "__main__":
    unittest.main()
