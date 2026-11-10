"""Adversarial presentation checks against executed evidence (no network)."""

import unittest

from api.chat import format_grouped_metric_answer


METADATA = {
    "Sales.amount": {"name": "Ventas", "format": "currency"},
    "Sales.ticket": {"name": "Ticket promedio", "format": "currency"},
}


def render(rows, *, measures=None, dimensions=None, order=None, **query_fields):
    query = {
        "measures": measures or ["Sales.amount"],
        "dimensions": dimensions or ["Customers.name"],
        **query_fields,
    }
    if order is not None:
        query["order"] = order
    return format_grouped_metric_answer(
        "Mostrame el detalle de los resultados", query, {"data": rows}, METADATA
    )


class AnswerEdgeCasesTests(unittest.TestCase):
    def test_customer_with_unknown_ticket_keeps_known_sales_and_rank(self):
        answer = render(
            [
                {"Customers.name": "Mayorista Norte", "Sales.amount": 1200, "Sales.ticket": None},
                {"Customers.name": "Minorista Sur", "Sales.amount": 900, "Sales.ticket": 30},
            ],
            measures=["Sales.ticket", "Sales.amount"],
            order={"Sales.amount": "desc"},
        )
        self.assertIsNotNone(answer)
        self.assertIn("Mayorista Norte", answer)
        self.assertIn("1.200,00", answer)
        self.assertIn("sin datos suficientes", answer)
        self.assertLess(answer.index("Mayorista Norte"), answer.index("Minorista Sur"))

    def test_two_business_dimensions_do_not_collapse_different_groups(self):
        answer = render(
            [
                {"Customers.name": "Acme", "Products.category": "Tecnología", "Sales.amount": 1200},
                {"Customers.name": "Acme", "Products.category": "Hogar", "Sales.amount": 300},
            ],
            dimensions=["Customers.name", "Products.category"],
            order={"Sales.amount": "desc"},
        )
        self.assertIn("Tecnología", answer)
        self.assertIn("Hogar", answer)

    def test_secondary_sort_breaks_ties_before_display_limit(self):
        answer = render(
            [
                {"Customers.name": "Zulu", "Sales.amount": 100},
                {"Customers.name": "Alfa", "Sales.amount": 100},
                {"Customers.name": "Beta", "Sales.amount": 90},
            ],
            order={"Sales.amount": "desc", "Customers.name": "asc"},
            limit=2,
        )
        self.assertLess(answer.index("Alfa"), answer.index("Zulu"))
        self.assertNotIn("Beta", answer)

    def test_cube_array_order_uses_selection_measure_and_direction(self):
        answer = render(
            [
                {"Customers.name": "Menor venta", "Sales.amount": 100, "Sales.ticket": 5},
                {"Customers.name": "Mayor venta", "Sales.amount": 200, "Sales.ticket": 1},
            ],
            measures=["Sales.ticket", "Sales.amount"],
            order=[["Sales.amount", "desc"]],
        )
        self.assertLess(answer.index("Mayor venta"), answer.index("Menor venta"))

    def test_unknown_ranking_value_is_never_treated_as_zero_above_negative_values(self):
        answer = render(
            [
                {"Customers.name": "Sin monto", "Sales.amount": None, "Sales.ticket": 5},
                {"Customers.name": "Con devolución", "Sales.amount": -20, "Sales.ticket": 10},
            ],
            measures=["Sales.ticket", "Sales.amount"],
            order={"Sales.amount": "desc"},
        )
        self.assertIn("Sin monto", answer)
        self.assertIn("sin datos suficientes", answer)
        self.assertLess(answer.index("Con devolución"), answer.index("Sin monto"))

    def test_one_row_ordered_by_name_does_not_claim_best_sales(self):
        answer = render(
            [{"Customers.name": "Acme", "Sales.amount": 150}],
            order={"Customers.name": "asc"},
        )
        self.assertIn("Acme", answer)
        self.assertIn("150,00", answer)
        self.assertNotIn("menor **name**", answer)
        self.assertNotIn("mayor **name**", answer)

    def test_null_exact_filter_does_not_become_literal_none_entity(self):
        answer = render(
            [{"Customers.name": "Acme", "Sales.amount": 150}],
            filters=[{"member": "Products.category", "operator": "equals", "values": [None]}],
        )
        self.assertNotIn("**None**", answer)

    def test_uncategorized_group_is_not_silently_removed(self):
        answer = render(
            [
                {"Products.category": None, "Sales.amount": 1234.56},
                {"Products.category": "Hogar", "Sales.amount": 200},
            ],
            dimensions=["Products.category"],
            order={"Sales.amount": "desc"},
        )
        self.assertIn("1.234,56", answer)
        self.assertIn("Hogar", answer)
        self.assertNotIn("**None**", answer)

    def test_zero_sales_and_summary_sentinel_are_handled_without_invented_totals(self):
        answer = render(
            [
                {"Customers.name": "Sin ventas", "Sales.amount": 0},
                {"_TOTALES_": True, "Sales.amount": 999},
            ],
        )
        self.assertIn("Sin ventas", answer)
        self.assertIn("0,00", answer)
        self.assertNotIn("999", answer)
        self.assertNotIn("_TOTALES_", answer)

    def test_top_limit_must_not_compute_unrequested_aggregate_from_visible_rows(self):
        answer = render(
            [
                {"Customers.name": "Acme", "Sales.amount": 1000, "Sales.ticket": 100},
                {"Customers.name": "Beta", "Sales.amount": 900, "Sales.ticket": 10},
            ],
            measures=["Sales.ticket", "Sales.amount"],
            order={"Sales.amount": "desc"},
            limit=2,
        )
        self.assertNotIn("55,00", answer)  # Average of averages is not global ticket.
        self.assertNotIn("1.900,00", answer)  # Top rows are not company-wide sales.
        self.assertIn("Acme", answer)
        self.assertIn("Beta", answer)

    def test_markdown_names_and_filter_values_are_rendered_as_literal_text(self):
        answer = render(
            [{"Customers.name": "**ACME** [ver](https://example.com)\n# Total falso", "Sales.amount": 100}],
            filters=[{"member": "Products.category", "operator": "equals", "values": ["[Hogar](https://example.com)"]}],
        )
        self.assertIn(r"\*\*ACME\*\*", answer)
        self.assertIn(r"\[ver\]", answer)
        self.assertIn(r"\[Hogar\]", answer)
        self.assertNotIn("[ver](https://example.com)", answer)
        self.assertNotIn("[Hogar](https://example.com)", answer)
        self.assertNotIn("\n# Total falso", answer)

    def test_explicit_twelve_results_are_not_silently_cut_to_five(self):
        answer = render(
            [{"Customers.name": f"Cliente {index:02d}", "Sales.amount": 100 - index} for index in range(12)],
            order={"Sales.amount": "desc"},
            limit=12,
        )
        for index in range(12):
            self.assertIn(f"Cliente {index:02d}", answer)
        self.assertIn("limitada a 12", answer)
        self.assertNotIn("5 de los 12", answer)

    def test_nonfinite_numbers_are_unknown_and_never_outrank_finite_sales(self):
        answer = render(
            [
                {"Customers.name": "No calculado", "Sales.amount": float("nan")},
                {"Customers.name": "Infinito positivo", "Sales.amount": float("inf")},
                {"Customers.name": "Infinito negativo", "Sales.amount": float("-inf")},
                {"Customers.name": "Monto real", "Sales.amount": -20},
            ],
            order={"Sales.amount": "desc"},
        )
        self.assertEqual(answer.count("sin datos suficientes"), 3)
        self.assertIn("-20,00", answer)
        for label in ["No calculado", "Infinito positivo", "Infinito negativo"]:
            self.assertIn(label, answer)
            self.assertLess(answer.index("Monto real"), answer.index(label))
        self.assertNotIn("**nan**", answer)
        self.assertNotIn("**inf**", answer)

    def test_duplicate_business_names_keep_identifiers_to_distinguish_entities(self):
        answer = render(
            [
                {"Customers.id": "customer-001", "Customers.name": "Acme", "Sales.amount": 500},
                {"Customers.id": "customer-002", "Customers.name": "Acme", "Sales.amount": 300},
            ],
            dimensions=["Customers.id", "Customers.name"],
        )
        self.assertIn("customer-001", answer)
        self.assertIn("customer-002", answer)
        self.assertEqual(answer.count("Acme"), 2)

    def test_unique_business_names_do_not_expose_redundant_technical_identifiers(self):
        answer = render(
            [
                {"Customers.id": "customer-001", "Customers.name": "Acme", "Sales.amount": 500},
                {"Customers.id": "customer-002", "Customers.name": "Beta", "Sales.amount": 300},
            ],
            dimensions=["Customers.id", "Customers.name"],
        )
        self.assertIn("Acme", answer)
        self.assertIn("Beta", answer)
        self.assertNotIn("customer-001", answer)
        self.assertNotIn("customer-002", answer)

    def test_business_dimension_ending_in_id_is_not_mistaken_for_identifier(self):
        answer = render(
            [
                {"Customers.name": "Acme", "Orders.paid": "Pagado", "Sales.amount": 500},
                {"Customers.name": "Beta", "Orders.paid": "Pendiente", "Sales.amount": 300},
            ],
            dimensions=["Customers.name", "Orders.paid"],
        )
        self.assertIn("Pagado", answer)
        self.assertIn("Pendiente", answer)

    def test_single_selected_winner_keeps_customer_filter_context(self):
        answer = render(
            [{"Products.name": "Producto líder", "Sales.ticket": 50, "Sales.amount": 500}],
            measures=["Sales.ticket", "Sales.amount"],
            dimensions=["Products.name"],
            order={"Sales.amount": "desc"},
            limit=1,
            filters=[{"member": "Customers.name", "operator": "equals", "values": ["Acme"]}],
        )
        self.assertIn("Producto líder", answer)
        self.assertIn("Acme", answer)

    def test_numeric_looking_text_dimensions_keep_lexical_order(self):
        answer = render(
            [
                {"Customers.name": "10", "Sales.amount": 500},
                {"Customers.name": "2", "Sales.amount": 300},
            ],
            order={"Customers.name": "asc"},
        )
        self.assertLess(answer.index("**10**"), answer.index("**2**"))


if __name__ == "__main__":
    unittest.main()
