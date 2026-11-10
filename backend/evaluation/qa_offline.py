"""Read-only data profile and answer/context regressions; no model inference.

python backend/evaluation/qa_offline.py --output scratch/qa-respuestas-2026-10-14
"""
import argparse
import csv
from collections import Counter
from datetime import datetime
from decimal import Decimal
import hashlib
import inspect
import json
import os
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/tests')]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def profile(folder):
    tables = {}
    report = {'scope': 'CSV locales, sin consultar Cube ni Supabase. Cálculos monetarios con Decimal.', 'tables': {}}
    for source in sorted(folder.glob('*.csv')):
        rows = list(csv.DictReader(source.open(encoding='utf-8-sig', newline='')))
        tables[source.stem] = rows
        report['tables'][source.stem] = {
            'path': str(source.relative_to(ROOT)), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'rows': len(rows), 'columns': list(rows[0]) if rows else [],
            'empty_by_column': {c: sum(not r[c].strip() for r in rows) for c in rows[0]} if rows else {},
        }
    sales, inventory = tables['fact_ventas'], tables['fact_inventario_mensual']
    key_map = {'dim_cliente': ['clienteid'], 'dim_producto': ['productoid'], 'dim_proveedor': ['proveedorid'],
               'dim_fecha': ['fecha'], 'fact_ventas': ['idtransaccion'], 'fact_inventario_mensual': ['fecha_cierre', 'productoid']}
    for name, keys in key_map.items():
        counts = Counter(tuple(r[k] for k in keys) for r in tables[name])
        report['tables'][name]['duplicate_keys'] = sum(v - 1 for v in counts.values())
        report['tables'][name]['key'] = keys
    amount = sum((Decimal(r['monto_total']) for r in sales), Decimal(0))
    cost = sum((Decimal(r['costo_total']) for r in sales), Decimal(0))
    calendar = {r['fecha'] for r in tables['dim_fecha']}
    missing = [r for r in sales if r['fecha'] not in calendar]
    clients = {r['clienteid']: r['nombre_razonsocial'] for r in tables['dim_cliente']}
    products = {r['productoid'] for r in tables['dim_producto']}
    providers = {r['proveedorid'] for r in tables['dim_proveedor']}
    report['sales'] = {
        'date_min': min(r['fecha'] for r in sales), 'date_max': max(r['fecha'] for r in sales),
        'amount': str(amount), 'cost': str(cost), 'units': str(sum(Decimal(r['cantidad']) for r in sales)),
        'unique_transactions': len({r['idtransaccion'] for r in sales}),
        'amount_per_transaction_offline': str(amount / len({r['idtransaccion'] for r in sales})),
        'calendar_orphan_rows': len(missing), 'calendar_orphan_share': len(missing) / len(sales),
        'calendar_orphan_amount': str(sum((Decimal(r['monto_total']) for r in missing), Decimal(0))),
        'calendar_join_amount': str(sum((Decimal(r['monto_total']) for r in sales if r['fecha'] in calendar), Decimal(0))),
        'customer_orphans': sum(r['clienteid'] not in clients for r in sales),
        'product_orphans': sum(r['productoid'] not in products for r in sales),
    }
    report['product_provider_orphans'] = sum(r['proveedorid'] not in providers for r in tables['dim_producto'])
    report['inventory'] = {'date_min': min(r['fecha_cierre'] for r in inventory),
                           'date_max': max(r['fecha_cierre'] for r in inventory),
                           'closes': len({r['fecha_cierre'] for r in inventory}),
                           'products': len({r['productoid'] for r in inventory})}
    grouped = {}
    for row in sales:
        entry = grouped.setdefault(row['clienteid'], {'name': clients.get(row['clienteid']), 'amount': Decimal(0), 'transactions': set()})
        entry['amount'] += Decimal(row['monto_total'])
        entry['transactions'].add(row['idtransaccion'])
    report['top_customers'] = [{'customer_id': k, 'name': v['name'], 'amount': str(v['amount']),
                               'transactions': len(v['transactions']), 'ticket_reference': str(v['amount'] / len(v['transactions']))}
                              for k, v in sorted(grouped.items(), key=lambda kv: kv[1]['amount'], reverse=True)[:3]]
    report['oracle_definition'] = 'ticket_reference = sum(monto_total) / count(distinct idtransaccion). Se debe contrastar con definición publicada antes de juzgar el chat.'
    return report


def baseline(output):
    # Windows implements asyncio's socketpair with a loopback TCP connection.
    # Permit only that stdlib call, while blocking application network access.
    original_connect = socket.socket.connect

    def guard(sock, address):
        internal_pair = any(f.function in {'socketpair', '_fallback_socketpair'} and Path(f.filename).name == 'socket.py' for f in inspect.stack())
        if internal_pair:
            return original_connect(sock, address)
        raise AssertionError('QA offline: application network prohibited')

    names = ['test_answer_edge_cases', 'test_conversational_answers', 'test_bi_harness',
             'test_conversation_enterprise', 'test_semantic_integrity', 'test_contextual_business_chat',
             'test_user_chat_regressions', 'test_semantic_metric_routing', 'test_metadata_chat',
             'test_codex_llm', 'test_llm_provider']
    os.environ['BI_TRACE_DIR'] = ''
    with patch.object(socket.socket, 'connect', guard), (output / 'baseline.log').open('w', encoding='utf-8') as stream:
        suite = unittest.TestLoader().loadTestsFromNames(names)
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    report = {'scope': 'Regresiones locales; inferencia y datos remotos simulados. Red de aplicación bloqueada.',
              'tests_run': result.testsRun, 'failures': [{'test': str(t), 'traceback': e} for t, e in result.failures],
              'errors': [{'test': str(t), 'traceback': e} for t, e in result.errors], 'skipped': result.skipped,
              'passed': result.wasSuccessful(), 'test_modules': names}
    save(output / 'baseline.json', report)
    return report


def memory_probe(output):
    from services.conversation_context import select_conversation_history
    from services.semantic_planner import compile_analysis_plan
    from test_contextual_business_chat import contextual_fixture
    from test_semantic_metric_routing import AMOUNT_KEY, CLIENT_KEY
    import asyncio
    from unittest.mock import AsyncMock

    report = {'scope': 'Selector real y reparaciones deterministas con plan LLM simulado; no inferencia.', 'cases': []}
    old = {'role': 'user', 'content': 'El negocio se llama CONTEXTO_INICIAL_X.'}
    correction = {'role': 'user', 'content': 'Corrección: el negocio ahora se llama CONTEXTO_CORREGIDO_Y.'}
    history = [old] + [{'role': 'assistant', 'content': 'x' * 6000} for _ in range(7)] + [correction]
    history += [{'role': 'user', 'content': 'y' * 6000} for _ in range(12)]
    selected = select_conversation_history(history)
    kept_old = any('CONTEXTO_INICIAL_X' in m['content'] for m in selected)
    kept_new = any('CONTEXTO_CORREGIDO_Y' in m['content'] for m in selected)
    report['cases'].append({'id': 'MEM-budget-correction', 'input': history, 'selected': selected,
                            'checks': {'newest_correction_retained_or_original_removed': kept_new or not kept_old},
                            'passed': kept_new or not kept_old,
                            'observation': {'original_retained': kept_old, 'correction_retained': kept_new}})
    pressure_history = [dict(m) for m in history]
    pressure_history[0]['content'] = (old['content'] + ' ' + 'z' * 6000)[:6000]
    pressure_selected = select_conversation_history(pressure_history)
    old_kept = any('CONTEXTO_INICIAL_X' in m['content'] for m in pressure_selected)
    new_kept = any('CONTEXTO_CORREGIDO_Y' in m['content'] for m in pressure_selected)
    report['cases'].append({'id': 'MEM-budget-full-prefix', 'input': pressure_history, 'selected': pressure_selected,
                            'checks': {'newest_correction_retained_or_original_removed': new_kept or not old_kept},
                            'passed': new_kept or not old_kept,
                            'observation': {'original_retained': old_kept, 'correction_retained': new_kept}})
    long_message = {'role': 'user', 'content': 'x' * 6001 + ' CORRECCION_CRITICA_FINAL'}
    selected_long = select_conversation_history([long_message])
    report['cases'].append({'id': 'MEM-message-truncation', 'input_characters': len(long_message['content']),
                            'selected_characters': len(selected_long[0]['content']),
                            'critical_tail_retained': 'CORRECCION_CRITICA_FINAL' in selected_long[0]['content'],
                            'status': 'transport_limitation'})
    catalog, metrics = contextual_fixture()
    previous = {'connection_id': 'c', 'primary_measure': AMOUNT_KEY, 'selected_entities': [{'member': CLIENT_KEY, 'value': 'Cliente A'}],
                'query': {'measures': [AMOUNT_KEY], 'filters': [{'member': CLIENT_KEY, 'operator': 'equals', 'values': ['Cliente A']}],
                          'timeDimensions': [{'dimension': 'FactVentas.fecha', 'dateRange': ['2024-01-01', '2024-01-31']}]}}
    replacement = {'queries': [{'query': {'measures': [AMOUNT_KEY], 'filters': [{'member': CLIENT_KEY, 'operator': 'equals', 'values': ['Cliente B']}],
                                         'timeDimensions': [{'dimension': 'FactVentas.fecha', 'dateRange': ['2024-02-01', '2024-02-29']}]}}]}
    prompt = 'Ese cliente no: quiero Monto Total de Venta de Cliente B en febrero de 2024'
    with patch('services.semantic_planner._llm_plan', new=AsyncMock(return_value=replacement)):
        plan = asyncio.run(compile_analysis_plan(prompt=prompt, user_id='', connection_id='c', semantic_catalog=catalog,
                                                metric_catalog=metrics, context={'conversation_history': [{'role': 'assistant', 'content': 'Cliente A seleccionado', 'semantic_context': previous}]}))
    filters = [spec['query'].get('filters', []) for spec in plan.get('queries', [])]
    passed = bool(filters) and all('Cliente A' not in json.dumps(f) and 'Cliente B' in json.dumps(f) for f in filters)
    report['cases'].append({'id': 'MEM-negated-reference', 'prompt': prompt, 'previous_state': previous,
                            'simulated_correct_llm_plan': replacement, 'actual_plan': plan,
                            'checks': {'explicit_new_customer_preserved': passed}, 'passed': passed})
    save(output / 'memory-probes.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--connection-id', default='4572ee06-968d-49f1-bbb5-cd6b7c47b743')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    save(args.output / 'data-profile.json', profile(ROOT / 'data/excel' / args.connection_id))
    base = baseline(args.output)
    memory = memory_probe(args.output)
    print(json.dumps({'baseline_tests': base['tests_run'], 'baseline_passed': base['passed'],
                      'memory': [{'id': c['id'], 'passed': c.get('passed'), 'status': c.get('status')} for c in memory['cases']]}, ensure_ascii=False))
    sys.exit(0 if base['passed'] and all(c.get('passed', True) for c in memory['cases']) else 1)
