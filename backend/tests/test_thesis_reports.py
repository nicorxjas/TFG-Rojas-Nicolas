import unittest

from api.reports import build_report_json_structure, enforce_report_scope


class ThesisReportTests(unittest.TestCase):
    def test_legacy_chart_flag_does_not_request_charts(self):
        for clients_allowed in (True, False):
            schema = build_report_json_structure(True, clients_allowed)
            self.assertNotIn('chart_data', schema)
            self.assertIn('executive_summary', schema)
            self.assertIn('actionables', schema)

    def test_unexpected_model_chart_is_removed_for_every_scope(self):
        for clients_allowed in (True, False):
            report = {
                'executive_summary': 'Ingresos: $100.',
                'actionables': [],
                'chart_data': {'type': 'bar', 'series': [100]},
            }
            result = enforce_report_scope(report, {'allow_client_detail': clients_allowed})
            self.assertNotIn('chart_data', result)
            self.assertEqual('Ingresos: $100.', result['executive_summary'])


if __name__ == '__main__':
    unittest.main()
