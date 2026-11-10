"""Independent reference cases for all remaining published metrics."""
import argparse
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import re
import qa_answers as qa


def build(folder):
    oracle = qa.Oracle(qa.CID)
    catalog = json.loads((folder / 'preflight.json').read_text(encoding='utf-8'))['catalog']['metrics']
    covered = {qa.A, qa.COST, qa.N, qa.T, qa.STOCK, 'Excel4572ee06DimCliente.count',
               'Excel4572ee06DimProducto.count', 'Excel4572ee06DimProveedor.count', 'Metricas.lead_time_promedio_de_proveedores'}
    table_map = {f'Excel4572ee06{k}': v for k, v in [('DimFecha', 'dim_fecha'), ('DimCliente', 'dim_cliente'),
                   ('DimProducto', 'dim_producto'), ('DimProveedor', 'dim_proveedor'),
                   ('FactVentas', 'fact_ventas'), ('FactInventarioMensual', 'fact_inventario_mensual')]}
    template = qa.cases(oracle)[0]
    bank = []
    for metric in catalog:
        key, expression = metric['key'], metric['expression']
        if key in covered:
            continue
        if key == 'Metricas.tiempo_promedio_entre_ventas':
            dates = [r['fecha'] for r in oracle.sources['fact_ventas']]
            days = (date.fromisoformat(max(dates)) - date.fromisoformat(min(dates))).days
            expected = Decimal(days) / (len(dates) - 1)
        else:
            match = re.fullmatch(r'(count|count_distinct|sum|avg|min|max)\((\w+)\.(\w+)\)', expression)
            if not match:
                raise ValueError(f'No independent oracle for {key}')
            operation, table, field = match.groups()
            records = oracle.sources[table_map[table]]
            values = [r[field] for r in records] if operation != 'count' else []
            if operation == 'count':
                expected = len(records)
            elif operation == 'count_distinct':
                expected = len(set(values))
            elif operation in {'sum', 'avg'}:
                expected = sum((Decimal(v) for v in values), Decimal(0))
                if operation == 'avg':
                    expected /= len(values)
            else:
                expected = min(values) if operation == 'min' else max(values)
        case = deepcopy(template)
        case_id = 'CAT-' + key
        case.update(id=case_id, scenario=case_id, prompt=f'¿Cuál es el valor global de la métrica publicada «{metric["name"]}» considerando todos sus registros? Necesito un único valor, sin desglose ni filtros.',
                    metric=key, expected=[{key: expected}], level=3)
        if metric.get('source') == 'aggregate_helper':
            # Helpers are dependencies, explicitly excluded from the planner.
            # The first campaign retained its original bank; future banks test
            # this access boundary rather than falsely assuming publication.
            case.update(kind='review', source_contract='internal_helper_excluded_from_planner',
                        reference_offline=[{key: expected}], expected=None,
                        prompt=f'¿Podés consultar directamente el cálculo «{metric["name"]}» sobre todos sus registros? Si es una medida auxiliar interna que no está publicada para el chat, explicá esa limitación y el paso para habilitarla; no publiques nada.')
        if isinstance(expected, str) and metric.get('source') != 'aggregate_helper':
            case['kind'] = 'datetime'
        bank.append(case)
    # Boolean filters must use dimensions actually published to the planner.
    segment = sorted({r['segmento'] for r in oracle.sources['dim_cliente']})[0]
    category = sorted({r['rubro'] for r in oracle.sources['dim_producto']})[0]
    customers = {r['clienteid']: r for r in oracle.sources['dim_cliente']}
    seg_key, category_key = 'Excel4572ee06DimCliente.segmento', 'Excel4572ee06DimProducto.rubro'
    for op in ['and', 'or']:
        records = []
        for sale in oracle.sources['fact_ventas']:
            left = customers[sale['clienteid']]['segmento'] == segment
            right = oracle.products[sale['productoid']]['rubro'] == category
            if (left and right) if op == 'and' else (left or right):
                records.append(sale)
        predicates = [{'member': seg_key, 'operator': 'equals', 'values': [segment]},
                      {'member': category_key, 'operator': 'equals', 'values': [category]}]
        case = deepcopy(template)
        case_id = 'FILTER-PUBLISHED-' + op.upper()
        case.update(id=case_id, scenario=case_id, level=2,
                    prompt=f'¿Cuál es el Monto Total de Venta de todo el histórico para ventas que cumplan {"ambas condiciones" if op == "and" else "al menos una condición, sin duplicar las que cumplen ambas"}: cliente del segmento {segment} {"y" if op == "and" else "o"} producto del rubro {category}? Usá {op.upper()}. Necesito un único total, sin desgloses.',
                    expected=[{qa.A: sum((Decimal(r['monto_total']) for r in records), Decimal(0))}],
                    expected_filters=predicates if op == 'and' else [{'or': predicates}])
        bank.append(case)
    return bank


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    bank = build(args.output)
    qa.save(args.output / 'catalog-cases.json', bank)
    print(json.dumps({'catalog_and_filters_cases': len(bank)}))
