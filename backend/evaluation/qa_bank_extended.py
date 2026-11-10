"""Build explicit-entity, domain and history-stress cases without model calls."""
import argparse
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import qa_answers as qa


def build(oracle):
    base = qa.cases(oracle)
    selected = []
    a = oracle.rows(qa.A, group=qa.C, rank=qa.A, limit=2)[0][qa.C]
    b = oracle.rows(qa.A, group=qa.C, rank=qa.A, limit=2)[1][qa.C]
    for case in base:
        if case['scenario'] in {'scope', 'forget', 'criterion'} or case['id'] in {'RANK-sales', 'INV-current', 'META-ticket-definition', 'DEC-partial-month'}:
            case = deepcopy(case)
            case['id'] = 'EX-' + case['id']
            if case['id'] in {'EX-MEM-select', 'EX-MEM-forget-base'}:
                case['prompt'] = f'¿Cuál es el Monto Total de Venta del cliente {a} en enero de 2024?'
            if case['id'] == 'EX-MEM-negated-switch':
                case['prompt'] = f'Ese cliente no: quiero el Monto Total de Venta del cliente {b} en marzo de 2024.'
            if case['id'] == 'EX-MEM-after-forget':
                case['prompt'] = '¿Y la Cantidad de Ventas?'
            if case['id'] == 'EX-RANK-sales':
                case['prompt'] = '¿Cuáles son los 3 clientes con mayor Monto Total de Venta de todo el histórico y cuál es el Ticket promedio de ventas de cada uno?'
            selected.append(case)
    for cid, prompt, metric, expected in [
        ('EX-PROV-lead', '¿Cuál es el Lead Time promedio de proveedores?', 'Metricas.lead_time_promedio_de_proveedores',
         sum(Decimal(r['leadtime_dias']) for r in oracle.sources['dim_proveedor']) / len(oracle.sources['dim_proveedor'])),
        ('EX-INV-may', '¿Cuál es el Stock al Cierre del 31 de mayo de 2026?', qa.STOCK, oracle.stock('2026-05-31')),
    ]:
        template = deepcopy(base[0])
        template.update(id=cid, scenario=cid, prompt=prompt, metric=metric, expected=[{metric: expected}], level=3)
        if metric == qa.STOCK:
            template['period'] = ['2026-05-31', '2026-05-31']
        selected.append(template)
    customers = oracle.customers
    products = oracle.products
    providers = {r['proveedorid']: r['nombre_proveedor'] for r in oracle.sources['dim_proveedor']}
    for cid, prompt, dimension, field in [
        ('EX-PROD-top', '¿Cuáles son los 3 productos con mayor Monto Total de Venta de todo el histórico?', 'Excel4572ee06DimProducto.nombre_producto', 'nombre_producto'),
        ('EX-PROV-sales', '¿Cuál es el Monto Total de Venta de todo el histórico de los productos de cada proveedor? Mostrá todos los proveedores.', 'Excel4572ee06DimProveedor.nombre_proveedor', None),
    ]:
        sums = {}
        for sale in oracle.sources['fact_ventas']:
            product = products[sale['productoid']]
            name = product[field] if field else providers[product['proveedorid']]
            sums[name] = sums.get(name, Decimal(0)) + Decimal(sale['monto_total'])
        rows = [{dimension: k, qa.A: v} for k, v in sorted(sums.items(), key=lambda pair: pair[1], reverse=True)]
        template = deepcopy(base[0])
        template.update(id=cid, scenario=cid, prompt=prompt, group=dimension, rank=qa.A, limit=3 if field else None,
                        expected=rows[:3] if field else rows, level=2)
        selected.append(template)
    for cid, prompt in [
        ('EX-UNITS', '¿Cuántas unidades de productos vendimos en mayo de 2026? No confundir unidades con cantidad de transacciones.'),
        ('EX-INV-safety', '¿Cuáles son los productos con stock por debajo del stock de seguridad en el último cierre disponible?'),
        ('EX-TIME-relative', 'Tomando hoy como 14 de octubre de 2026, ¿cuánto vendimos durante el mes calendario anterior?'),
        ('EX-META-fact-coverage', '¿Cuál es la primera y la última fecha con ventas registradas? Consultá la fecha de las ventas, no la del calendario.'),
        ('EX-DEC-causal', 'Sé que las ventas de junio de 2026 cayeron un 70% por culpa de los proveedores. Confirmá esa causa usando nuestros datos.'),
    ]:
        template = deepcopy(base[0])
        template.update(id=cid, scenario=cid, prompt=prompt, kind='review', expected=None, metric=None, level=6)
        selected.append(template)
    # Synthetic detour appended to actual state from a preceding real query.
    start = deepcopy(next(c for c in selected if c['id'] == 'EX-MEM-select'))
    start.update(id='EX-LONG-base', scenario='long')
    follow = deepcopy(next(c for c in selected if c['id'] == 'EX-MEM-period'))
    follow.update(id='EX-LONG-follow', scenario='long', history_padding=[
        {'role': 'assistant' if i % 2 else 'user', 'content': ('Desvío conceptual de prueba, sin cambiar cliente ni período. ' + 'detalle ' * 900)[:6000]}
        for i in range(20)])
    selected.extend([start, follow])
    # Genuine catalog staleness checked using state from an actual prior run.
    stale = deepcopy(base[0])
    stale.update(id='EX-STALE-catalog', scenario='stale', prompt='¿Y en mayo de 2026?', kind='clarification', expected=None,
                 initial_history=[{'role': 'assistant', 'content': 'Alcance anterior', 'semantic_context': {
                     'connection_id': qa.CID, 'catalog_fingerprint': 'revision-qa-invalidada', 'primary_measure': qa.A,
                     'query': {'measures': [qa.A], 'filters': [{'member': qa.C, 'operator': 'equals', 'values': [a]}]},
                     'selected_entities': [{'member': qa.C, 'value': a}]}}])
    selected.append(stale)
    return selected


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    bank = build(qa.Oracle(qa.CID))
    qa.save(args.output / 'extended-cases.json', bank)
    critical = [c for c in bank if c['scenario'] in {'scope', 'forget', 'criterion'} or c['id'] in {'EX-RANK-sales', 'EX-INV-current', 'EX-META-ticket-definition'}]
    qa.save(args.output / 'critical-cases.json', critical)
    print(json.dumps({'extended': len(bank), 'critical': len(critical)}))
