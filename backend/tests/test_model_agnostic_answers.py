"""Regressions across opaque keys and unrelated business domains."""
import asyncio
from copy import deepcopy
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from services.semantic_graph import build_semantic_graph
from services.semantic_planner import (_sanitize_query, _compile_raw_plan,
    compile_analysis_plan, execute_analysis_plan, extract_date_range_from_text)
from services.bi_conversation import resolve_conversation_state
from services.semantic_query_engine import compile_powerbi_dax, execute_powerbi_semantic_query


def fixture():
    metrics = [{"key": "Q.a", "name": "Duración media", "source": "provider", "format": "number"},
               {"key": "Q.b", "name": "Intervenciones registradas", "source": "provider", "format": "number"}]
    catalog = {"tables": [{"id": "q", "name": "Q", "business_name": "Intervenciones"},
                          {"id": "r", "name": "R", "business_name": "Pacientes"}],
               "fields": [{"table_id": "q", "semantic_key": "Q.t", "name": "t", "business_name": "Fecha de registro", "field_kind": "time", "data_type": "date"},
                          {"table_id": "r", "semantic_key": "R.v", "name": "v", "business_name": "Paciente", "field_kind": "dimension", "data_type": "string"}],
               "relationships": [{"from_table": "Q", "from_field": "r", "to_table": "R", "to_field": "id", "is_active": True}]}
    return catalog, metrics, build_semantic_graph(catalog, metrics)


class ModelAgnosticPlanTests(unittest.TestCase):
    def test_valid_temporal_comparison_is_not_rewritten(self):
        _, _, graph = fixture()
        query = {"measures": ["Q.a"], "timeDimensions": [{"dimension": "Q.t", "granularity": "month", "dateRange": ["2026-05-01", "2026-06-30"]}], "limit": 100}
        plan = _compile_raw_plan({"queries": [{"query": query}]}, graph, "Compará duración de junio contra mayo de 2026", None)
        self.assertEqual(plan['queries'][0]['query'], query)

    def test_first_and_last_point_keep_native_grain(self):
        _, _, graph = fixture()
        for direction in ['asc', 'desc']:
            query = {"measures": ["Q.b"], "timeDimensions": [{"dimension": "Q.t", "granularity": "day"}], "order": {"Q.t": direction}, "limit": 1}
            clean, errors = _sanitize_query(query, graph, 'Primera y última fecha registrada', None)
            self.assertFalse(errors)
            self.assertEqual(clean, query)

    def test_unrequested_monthly_grain_and_conflicting_literal_dates_are_rejected(self):
        _, _, graph = fixture()
        for temporal in [
            {'dimension': 'Q.t', 'granularity': 'month', 'dateRange': ['2026-05-01', '2026-05-31']},
            {'dimension': 'Q.t', 'dateRange': ['2025-01-01', '2025-01-31']},
        ]:
            clean, errors = _sanitize_query({'measures': ['Q.a'], 'timeDimensions': [temporal]}, graph,
                                             'Duración media de mayo de 2026', ['2026-05-01', '2026-05-31'])
            self.assertIsNone(clean)
            self.assertTrue(errors)

    def test_ordering_an_unbroken_scalar_does_not_select_latest_point(self):
        _, _, graph = fixture()
        query = {"measures": ['Q.a'], "timeDimensions": [{"dimension": 'Q.t'}], "order": {'Q.t': 'desc'}, "limit": 1}
        clean, errors = _sanitize_query(query, graph, 'Valor actualmente disponible', None)
        self.assertIsNone(clean)
        self.assertTrue(errors)

    def test_reference_clock_is_not_the_requested_period(self):
        self.assertIsNone(extract_date_range_from_text('Tomando hoy como 14 de octubre de 2026, consultá el mes calendario anterior'))
        self.assertIsNone(extract_date_range_from_text('Hoy 2026-10-14, ¿y el mes anterior?'))

    def test_negated_reference_keeps_explicit_replacement(self):
        catalog, metrics, _ = fixture()
        requested = {'measures': ['Q.a'], 'filters': [{'member': 'R.v', 'operator': 'equals', 'values': ['Persona B']}]}
        state = {'connection_id': 'c', 'primary_measure': 'Q.a', 'query': {'measures': ['Q.a'], 'filters': [{'member': 'R.v', 'operator': 'equals', 'values': ['Persona A']}]},
                 'selected_entities': [{'member': 'R.v', 'value': 'Persona A'}]}
        with patch('services.semantic_planner._llm_plan', new=AsyncMock(return_value={'queries': [{'query': requested}]})):
            plan = asyncio.run(compile_analysis_plan(prompt='Ese paciente no: duración media de Persona B', user_id='', connection_id='c',
                semantic_catalog=catalog, metric_catalog=metrics, context={'conversation_history': [{'role': 'assistant', 'content': 'Persona A', 'semantic_context': state}]}))
        self.assertEqual(plan['queries'][0]['query']['filters'], requested['filters'])
        self.assertFalse(plan['queries'][0]['query'].get('dimensions'))

    def test_global_request_rejects_unasked_group_instead_of_changing_it(self):
        _, _, graph = fixture()
        raw = {'measures': ['Q.a'], 'dimensions': ['R.v']}
        clean, errors = _sanitize_query(raw, graph, 'Un único valor global de Duración media sin desglose', None)
        self.assertIsNone(clean)
        self.assertTrue(errors)

    def test_metric_name_frequency_does_not_introduce_time_grain(self):
        catalog, metrics, _ = fixture()
        metrics[1]['name'] = 'Cantidad de controles mensuales'
        graph = build_semantic_graph(catalog, metrics)
        raw = {'measures': ['Q.b'], 'limit': 100}
        clean, errors = _sanitize_query(raw, graph,
            'Valor global de Cantidad de controles mensuales. Un único valor sin desglose.', None)
        self.assertFalse(errors)
        self.assertEqual(clean, raw)

    def test_reset_marker_stops_recovery_before_boundary(self):
        _, _, graph = fixture()
        history = [{'role': 'assistant', 'semantic_context': {'query': {'measures': ['Q.a']}, 'connection_id': 'c'}},
                   {'role': 'assistant', 'semantic_context': {'scope_reset': True, 'query': {}, 'connection_id': 'c'}}]
        state, reason = resolve_conversation_state(history, 'c', graph, 'version')
        self.assertEqual(state, {})
        self.assertEqual(reason, 'explicit_scope_reset')

    def test_partial_reset_keeps_only_surviving_scope(self):
        _, _, graph = fixture()
        state = {'scope_reset': True, 'connection_id': 'c', 'primary_measure': 'Q.a', 'query': {'measures': ['Q.a'], 'timeDimensions': [{'dimension': 'Q.t', 'dateRange': ['2026-01-01', '2026-01-31']}]}}
        actual, reason = resolve_conversation_state([{'role': 'assistant', 'semantic_context': state}], 'c', graph, 'version')
        self.assertIsNone(reason)
        self.assertFalse(actual['query'].get('filters'))
        self.assertEqual(actual['query']['timeDimensions'], state['query']['timeDimensions'])

    def test_coverage_comes_from_factual_source_and_is_reused(self):
        queries = [{'id': str(i), 'query': {'measures': ['Q.a'], 'timeDimensions': [{'dimension': 'Q.t', 'dateRange': period}], 'limit': 100}}
                   for i, period in enumerate([['2026-05-01', '2026-05-31'], ['2026-06-01', '2026-06-30']])]
        plan = {'queries': queries, 'temporal_metadata': {'Q': {'dimension': 'Q.t'}}, 'field_metadata': {'Q.t': {'field_kind': 'time'}}}
        with patch('services.semantic_planner.execute_semantic_query', new=AsyncMock(return_value={'data': [{'Q.a': 25}]})), \
             patch('services.semantic_planner.get_semantic_time_bounds', new=AsyncMock(return_value=['2023-01-01', '2026-06-11'])) as bounds:
            result = asyncio.run(execute_analysis_plan(plan=plan, user_id='u', connection_id='c'))
        self.assertFalse(result['validation_errors'])
        self.assertTrue(result['evidence'][0]['coverage']['period_complete'])
        self.assertFalse(result['evidence'][1]['coverage']['period_complete'])
        self.assertEqual(bounds.await_count, 1)

    def test_coverage_uses_the_explicit_fact_date_instead_of_another_preferred_date(self):
        plan = {'queries': [{'id': 'one', 'query': {'measures': ['Q.a'], 'timeDimensions': [
            {'dimension': 'Q.discharge', 'dateRange': ['2026-06-01', '2026-06-30']} ]}}],
            'temporal_metadata': {'Q': {'dimension': 'Q.admission'}}}
        with patch('services.semantic_planner.execute_semantic_query', new=AsyncMock(return_value={'data': [{'Q.a': 25}]})), \
             patch('services.semantic_planner.get_semantic_time_bounds', new=AsyncMock(return_value=['2024-01-01', '2026-06-11'])) as bounds:
            result = asyncio.run(execute_analysis_plan(plan=plan, user_id='u', connection_id='c'))
        self.assertEqual(bounds.call_args.kwargs['dimension'], 'Q.discharge')
        self.assertFalse(result['evidence'][0]['coverage']['period_complete'])

    def test_calendar_is_not_used_as_factual_coverage_without_a_declared_binding(self):
        plan = {'queries': [{'id': 'one', 'query': {'measures': ['Q.a'], 'timeDimensions': [
            {'dimension': 'Calendar.t', 'dateRange': ['2026-06-01', '2026-06-30']} ]}}],
            'temporal_metadata': {'Q': {'dimension': 'Q.t'}}}
        with patch('services.semantic_planner.execute_semantic_query', new=AsyncMock(return_value={'data': [{'Q.a': 25}]})), \
             patch('services.semantic_planner.get_semantic_time_bounds', new=AsyncMock()) as bounds:
            result = asyncio.run(execute_analysis_plan(plan=plan, user_id='u', connection_id='c'))
        bounds.assert_not_awaited()
        self.assertIsNone(result['evidence'][0]['coverage']['period_complete'])


class PowerBIContractTests(unittest.TestCase):
    def fields(self):
        return [{'semantic_key': 'A.m', 'name': 'M', 'field_kind': 'measure'},
                {'semantic_key': 'B.x', 'name': 'X', 'field_kind': 'dimension'},
                {'semantic_key': 'C.y', 'name': 'Y', 'field_kind': 'dimension'},
                {'semantic_key': 'A.t', 'name': 'T', 'field_kind': 'time'},
                {'semantic_key': 'A.u', 'name': 'U', 'field_kind': 'time'}]

    def test_scalar_total_retains_entity_and_all_temporal_filters(self):
        query = {'measures': ['A.m'], 'filters': [{'member': 'B.x', 'operator': 'equals', 'values': ['Norte']}],
                 'timeDimensions': [{'dimension': key, 'dateRange': ['2026-05-01', '2026-05-31']} for key in ['A.t', 'A.u']]}
        dax, _ = compile_powerbi_dax(query, self.fields())
        self.assertIn('CALCULATETABLE(ROW(', dax)
        self.assertIn('TREATAS({"Norte"}', dax)
        self.assertIn("'A'[T]", dax)
        self.assertIn("'A'[U]", dax)
        self.assertIn('+ 1', dax)

    def test_boolean_or_cannot_be_dropped_from_total(self):
        dax, _ = compile_powerbi_dax({'measures': ['A.m'], 'filters': [{'or': [
            {'member': 'B.x', 'operator': 'equals', 'values': ['Norte']},
            {'member': 'C.y', 'operator': 'equals', 'values': ['Crítico']}]}]}, self.fields())
        self.assertIn(' || ', dax)
        self.assertIn("'B'[X]", dax)
        self.assertIn("'C'[Y]", dax)
        self.assertIn('CALCULATETABLE', dax)

    def test_numeric_filter_in_boolean_group_uses_declared_type(self):
        fields = self.fields()
        next(f for f in fields if f['semantic_key'] == 'B.x')['data_type'] = 'number'
        dax, _ = compile_powerbi_dax({'measures': ['A.m'], 'filters': [{'or': [
            {'member': 'B.x', 'operator': 'gt', 'values': ['12.5']},
            {'member': 'C.y', 'operator': 'equals', 'values': ['Crítico']}]}]}, fields)
        self.assertIn('[__filter0] > 12.5', dax)
        self.assertNotIn('> "12.5"', dax)

    def test_unsupported_time_grain_is_not_silently_scalar(self):
        with self.assertRaises(HTTPException):
            compile_powerbi_dax({'measures': ['A.m'], 'timeDimensions': [{'dimension': 'A.t', 'granularity': 'month'}]}, self.fields())

    def test_timestamp_does_not_masquerade_as_a_daily_bucket(self):
        fields = self.fields()
        next(f for f in fields if f['semantic_key'] == 'A.t')['data_type'] = 'datetime'
        with self.assertRaises(HTTPException):
            compile_powerbi_dax({'measures': ['A.m'], 'timeDimensions': [{'dimension': 'A.t', 'granularity': 'day'}]}, fields)

    def test_invalid_date_is_not_rolled_over_or_truncated_by_dax(self):
        for invalid in ['2026-02-30', '2026-01-01T23:30:00']:
            with self.subTest(invalid=invalid), self.assertRaises(HTTPException):
                compile_powerbi_dax({'measures': ['A.m'], 'timeDimensions': [
                    {'dimension': 'A.t', 'dateRange': [invalid, invalid]}]}, self.fields())

    def test_provider_aliases_are_normalized_and_ranking_is_stable(self):
        client = AsyncMock()
        client.execute_dax.return_value = {'results': [{'tables': [{'rows': [
            {'[M]': 2, 'B[X]': 'Equipo B'}, {'[M]': 7, 'B[X]': 'Equipo A'}]}]}]}
        connection = {'id': 'c', 'provider': 'powerbi', 'config': {'dataset_id': 'd'}}
        with patch('services.semantic_query_engine.powerbi_client_for_connection', new=AsyncMock(return_value=client)):
            result = asyncio.run(execute_powerbi_semantic_query(
                query={'measures': ['A.m'], 'dimensions': ['B.x'], 'order': {'A.m': 'desc'}, 'limit': 2},
                connection_id='c', user_id='u', semantic_catalog={'fields': self.fields()}, connection=connection))
        self.assertEqual(result['data'], [{'A.m': 7, 'B.x': 'Equipo A'}, {'A.m': 2, 'B.x': 'Equipo B'}])


if __name__ == '__main__':
    unittest.main()
