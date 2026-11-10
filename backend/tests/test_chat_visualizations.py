import unittest
from services.chat_visualizations import build_chat_visualization


class ChatVisualizationTests(unittest.TestCase):
    def setUp(self):
        self.query = {"measures": ["M.sales"], "dimensions": ["C.name"], "order": {"M.sales": "desc"}}
        self.result = {"data": [{"C.name": "A", "M.sales": "20.5"}, {"C.name": "B", "M.sales": 40}]}
        self.meta = {"M.sales": {"name": "Ventas", "format": "currency", "expression": "SUM(@amount)"}}

    def test_ranking_uses_exact_values_and_requested_order(self):
        chart = build_chat_visualization(self.query, self.result, self.meta)
        self.assertEqual(chart["preferred"], "horizontal-bar")
        self.assertEqual(chart["data"], [{"label": "B", "values": {"m0": 40}}, {"label": "A", "values": {"m0": 20.5}}])
        self.assertTrue(chart["series"][0]["additive"])

    def test_never_fills_missing_or_invalid_values_with_zero(self):
        for value in [None, "NaN", "Infinity", "oops", True]:
            self.result["data"][0]["M.sales"] = value
            self.assertIsNone(build_chat_visualization(self.query, self.result, self.meta))

    def test_ambiguous_grouping_and_totals_stay_text(self):
        for dimensions in [[], ["C.name", "C.city"]]:
            self.assertIsNone(build_chat_visualization({**self.query, "dimensions": dimensions}, self.result, self.meta))

    def test_percentages_and_averages_are_not_additive(self):
        self.meta["M.sales"]["expression"] = "AVG(@amount)"
        chart = build_chat_visualization(self.query, self.result, self.meta, "ver torta")
        self.assertFalse(chart["series"][0]["additive"])

    def test_explicit_text_request(self):
        self.assertIsNone(build_chat_visualization(self.query, self.result, self.meta, "solo texto"))

    def test_time_series_use_granular_key_and_chronological_order(self):
        query = {"measures": ["M.sales"], "timeDimensions": [{"dimension": "T.date", "granularity": "month"}]}
        result = {"data": [{"T.date.month": "2026-02", "M.sales": 3}, {"T.date.month": "2026-01", "M.sales": 2}]}
        chart = build_chat_visualization(query, result, self.meta)
        self.assertEqual(chart["kind"], "temporal")
        self.assertEqual(chart["data"][0]["label"], "2026-01")


if __name__ == "__main__":
    unittest.main()
