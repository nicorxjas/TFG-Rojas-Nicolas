"""The evaluator must catch unsupported definitions in suggestion events too."""
import unittest
from evaluation.qa_answers import checks_for


class QAAnswerContractTests(unittest.TestCase):
    def test_missing_concept_cannot_pass_with_an_executable_partial_formula(self):
        events = [{'type': 'metric_suggestion', 'content': {'suggestion': {
            'name': 'Costo integral del episodio', 'expression': '@Q.a - @Q.b', 'requires_definition': False}}},
            {'type': 'done'}]
        checks, status = checks_for({'kind': 'missing'}, '', events, [])
        self.assertFalse(checks['no_unsupported_formula_proposal'])
        self.assertEqual(status, 'fail')

    def test_missing_concept_with_specific_definition_gap_is_safe(self):
        events = [{'type': 'metric_suggestion', 'content': {'suggestion': {
            'name': 'Costo integral del episodio', 'expression': '', 'requires_definition': True,
            'proposed_calculation': 'Faltan costos de rehabilitación y seguimiento.'}}}, {'type': 'done'}]
        checks, status = checks_for({'kind': 'missing'}, '', events, [])
        self.assertTrue(checks['no_unsupported_formula_proposal'])
        self.assertEqual(status, 'pass')


if __name__ == '__main__':
    unittest.main()
