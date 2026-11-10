import unittest

from api.chat import format_grouped_metric_answer


class ConversationalAnswersTests(unittest.TestCase):
    def test_top_customers_explains_sales_order_and_each_ticket(self):
        answer = format_grouped_metric_answer(
            "¿Cuáles son los 3 clientes a los que más le vendimos y cuál es el ticket promedio de cada uno?",
            {"measures": ["F.ticket", "F.amount"], "dimensions": ["C.name"],
             "order": {"F.amount": "desc"}, "limit": 3},
            {"data": [
                {"C.name": "María Gomez - 36", "F.ticket": 789.47, "F.amount": 272366.82},
                {"C.name": "Gastronómica del Plata 17", "F.ticket": 827.62, "F.amount": 297944.64},
                {"C.name": "Hotel Las Sierras 49", "F.ticket": 795.69, "F.amount": 265762.10},
            ]},
            {"F.ticket": {"name": "Ticket promedio de ventas", "format": "currency"},
             "F.amount": {"name": "Monto Total de Venta", "format": "number"}},
        )
        introduction, detail, scope = answer.split("\n\n")
        self.assertIn("de mayor a menor según **ventas acumuladas**", introduction)
        self.assertIn("También te muestro el **ticket promedio**", introduction)
        self.assertLess(detail.index("Gastronómica"), detail.index("María"))
        self.assertLess(detail.index("María"), detail.index("Hotel"))
        self.assertIn("**297.944,64** en ventas acumuladas; ticket promedio de **$827,62**", detail)
        self.assertIn("histórico disponible", scope)
        self.assertNotIn("lidera el ranking", answer)

    def test_followup_includes_executed_customer_filter(self):
        answer = format_grouped_metric_answer(
            "¿Qué rubro de productos compra gastronomía del plata?",
            {"measures": ["F.amount"], "dimensions": ["P.category"], "order": {"F.amount": "desc"},
             "filters": [{"and": [{"member": "C.name", "operator": "equals",
                                     "values": ["Gastronómica del Plata 17"]}]}]},
            {"data": [{"P.category": "Tecnología", "F.amount": 166564.51},
                      {"P.category": "Hogar", "F.amount": 100027.07},
                      {"P.category": "Ferretería", "F.amount": 31353.06}]},
            {"F.amount": {"name": "Monto Total de Venta", "format": "number"}},
        )
        self.assertTrue(answer.startswith("Para **Gastronómica del Plata 17**"))
        self.assertIn("**Tecnología**: **166.564,51**", answer)
        self.assertNotIn("$", answer)  # No invented unit from the business wording.
        self.assertNotIn("lidera", answer)

    def test_other_domain_uses_metadata_and_reports_display_limit(self):
        answer = format_grouped_metric_answer(
            "Compará las unidades",
            {"measures": ["M.a", "M.b", "M.c", "M.d"], "dimensions": ["D.label"],
             "timeDimensions": [{"dimension": "M.date", "dateRange": ["2025-01-01", "2025-01-31"]}]},
            {"data": [{"D.label": f"Unidad {i}", "M.a": i, "M.b": 2, "M.c": 3, "M.d": None}
                      for i in range(7)]},
            {"M.a": {"name": "Consultas atendidas", "format": "number"},
             "M.b": {"name": "Espera", "format": "duration_days"},
             "M.c": {"name": "Capacidad", "format": "number"},
             "M.d": {"name": "Ocupación", "format": "percent"}},
        )
        self.assertIn("Consultas atendidas", answer)
        self.assertIn("Ocupación: **sin datos suficientes**", answer)
        self.assertIn("2025-01-01 a 2025-01-31", answer)
        self.assertIn("5 de los 7 resultados devueltos", answer)
        self.assertNotIn("mayor", answer)
        self.assertNotIn("cliente", answer)
        self.assertNotIn("Unidad 5", answer)

    def test_or_and_partial_match_filters_do_not_become_exact_context(self):
        answer = format_grouped_metric_answer(
            "Desglosá para otra persona inventada",
            {"measures": ["M.a"], "dimensions": ["D.label"],
             "filters": [{"or": [{"member": "C.name", "operator": "equals", "values": ["A"]},
                                  {"member": "C.name", "operator": "equals", "values": ["B"]}]},
                         {"member": "C.name", "operator": "contains", "values": ["C"]}]},
            {"data": [{"D.label": "Unidad", "M.a": 10}]},
            {"M.a": {"name": "Atenciones", "format": "number"}},
        )
        self.assertTrue(answer.startswith("Este es el desglose"))
        self.assertNotIn("Para **", answer)
        self.assertNotIn("persona inventada", answer)


if __name__ == "__main__":
    unittest.main()
