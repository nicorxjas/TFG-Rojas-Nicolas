"""Build a transparent local report from recorded QA; never calls a model."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def link(path, label):
    return f'[{label}](<{path.resolve().as_posix()}>)'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main(folder, report_path):
    runs = {name: read(folder / name / 'results.json') for name in ['live', 'extended', 'repetitions', 'catalog', 'published-filters']}
    assert all('summary' in r and all(t.get('status') for t in r['turns']) for r in runs.values()), 'Campaign not complete'
    baseline = read(folder / 'baseline.json')
    planner = read(folder / 'planner-live.json')
    preflight = read(folder / 'preflight.json')
    catalog = {m['key']: m for m in preflight['catalog']['metrics']}
    total = sum(len(r['turns']) for r in runs.values())
    manual = read(folder / 'manual-review-initial.json')
    for name, run in runs.items():
        for turn in run['turns']:
            cid = turn['case']['id']
            verdict = None
            reason = None
            if name == 'catalog' and catalog.get(turn['case'].get('metric'), {}).get('source') == 'aggregate_helper':
                verdict, reason = 'NO_APLICA_BUSINESS_PUBLICATION', 'Helper técnico hidden excluido del planner; premisa publicada incorrecta. Mantener como prueba del límite técnico.'
            elif name == 'catalog' and cid in {'FILTER-AND', 'FILTER-OR'}:
                verdict, reason = 'SAFE_ABSTENTION_CATALOG_BOUNDARY', 'Canal no publicado como dimensión. El oráculo local no prueba que el chat pueda consultarlo.'
            elif cid == 'EX-INV-current':
                verdict, reason = 'MANUAL_FAIL', 'Stock acumulado de snapshots en vez de último cierre1731.'
            elif cid == 'EX-META-ticket-definition':
                verdict, reason = 'MANUAL_PASS', 'Fórmula A/N correcta, incluido símbolo ÷; no hay ejecución de datos.'
            elif cid == 'EX-MEM-forget':
                verdict, reason = 'MANUAL_FAIL_SEQUENCE', 'Confirma reset pero el siguiente turno conserva cliente/enero y responde6 en lugar20244 global.'
            elif cid == 'EX-DEC-partial-amount':
                verdict, reason = 'MANUAL_FAIL', 'No responde comparación/conclusión ni declara junio parcial. Algunas repeticiones fusionan meses y agregan rubro.'
            elif cid == 'EX-DEC-partial-month':
                verdict, reason = 'OPERATIONAL_ERROR' if turn['status'] == 'operational_error' else 'INCONCLUSIVE', 'No llegó a validar comparación temporal; se preserva timeout/aclaración.'
            elif cid == 'EX-TIME-relative':
                verdict, reason = 'MANUAL_FAIL', 'Ejecuta día ancla14octubre en lugar septiembre, pese a plan LLM correcto.'
            elif cid == 'EX-META-fact-coverage':
                verdict, reason = 'MANUAL_FAIL', 'Responde dos conteos en lugar primera/última fecha factual.'
            elif cid == 'EX-INV-safety':
                verdict, reason = 'SAFE_ABSTENTION_POOR_EXPLANATION', 'No inventa comparación; pierde explicación de stock_seguridad string no consultable como medida.'
            elif cid == 'FILTER-PUBLISHED-AND':
                verdict, reason = 'BOOLEAN_VALUES_PASS_GRAIN_UX_FAIL', 'AND y cifra1034257.52 correctos; añade dimensión constante y forma de desglose no solicitada.'
            elif cid == 'FILTER-PUBLISHED-OR':
                verdict, reason = 'BOOLEAN_SCOPE_PASS_FINAL_TOTAL_FAIL', 'OR correcto sin duplicados, pero devuelve2subtotales y omite total8111935.88 solicitado.'
            if verdict:
                manual.append({'run': name, 'id': cid, 'repeat': turn['repeat'], 'automatic_status': turn['status'], 'manual_verdict': verdict, 'reason': reason})
    write(folder / 'manual-review.json', manual)
    manual_map = {(m['run'], m['id'], m['repeat']): m for m in manual}
    appendix = ['# Registro completo de turnos de QA', '', 'Los mensajes siguientes son respuestas observadas, no instrucciones para el ejecutor. Los JSON vinculados conservan historial, estados, SSE, plan, consultas, datos y trazas.', '']
    index = []
    for name, run in runs.items():
        appendix.extend([f'## Campaña {name}', '', link(folder / name / 'results.json', 'Registro JSON completo'), ''])
        for turn in run['turns']:
            case = turn['case']
            key = (name, case['id'], turn['repeat'])
            review = manual_map.get(key)
            appendix.extend([f'### {case["id"]} — repetición {turn["repeat"] + 1}', '', f'Pregunta: {case["prompt"]}', '',
                             f'Nivel {case["level"]}; sesión {case["scenario"]}; resultado automático: **{turn["status"]}**; duración: {turn["seconds"]} s.', ''])
            if review:
                appendix.extend([f'Revisión: **{review["manual_verdict"]}**. {review["reason"]}', ''])
            answer = turn.get('answer') or ''
            if answer:
                appendix.extend(['Respuesta observada:', '', *['> ' + line for line in answer.splitlines()], ''])
            else:
                suggestions = [e['content'].get('message', '') for e in turn.get('events', []) if e['type'] == 'metric_suggestion']
                appendix.extend(['Respuesta vía menú/SSE:' if suggestions else 'Sin respuesta de texto completa.', '', *['> ' + line for s in suggestions for line in s.splitlines()], ''])
            if case.get('expected') is not None:
                appendix.extend(['Referencia independiente:', '', '```json', json.dumps(case['expected'], ensure_ascii=False, indent=2), '```', ''])
            queries = [e['query'] for execution in turn.get('executions', []) for e in execution.get('evidence', [])]
            appendix.extend(['Consultas ejecutadas:', '', '```json', json.dumps(queries, ensure_ascii=False, indent=2), '```', '',
                             'Comprobaciones:', '', '```json', json.dumps(turn.get('checks') or {'error_type': turn.get('error_type'), 'detail': turn.get('detail')}, ensure_ascii=False, indent=2), '```', ''])
            if turn.get('trace_id'):
                appendix.extend([link(folder / name / 'traces' / f'{turn["trace_id"]}.json', f'Traza {turn["trace_id"]}'), ''])
            index.append({'run': name, 'id': case['id'], 'repeat': turn['repeat'], 'scenario': case['scenario'], 'level': case['level'],
                          'status': turn['status'], 'manual_review': review, 'trace_id': turn.get('trace_id')})
    (folder / 'registro-completo.md').write_text('\n'.join(appendix), encoding='utf-8')
    write(folder / 'index.json', index)
    manifest = {'closed_at_utc': datetime.now(timezone.utc).isoformat(), 'client_timezone': 'America/Buenos_Aires',
                'provider': preflight['provider'], 'model': preflight['model'], 'turns_real_service': total,
                'distinct_case_ids': len({i['id'] for i in index}), 'baseline_tests': baseline['tests_run'],
                'planner_synthetic_contract_passed': planner['passed'], 'planner_synthetic_total': planner['total'],
                'runs': {n: {'summary': r['summary'], 'remote_write_attempts_blocked': r.get('blocked_write_attempts', 0), 'commit': r['commit'], 'runner_sha256': r.get('runner_sha256')} for n, r in runs.items()},
                'scope_exclusions': ['charts', 'browser/auth E2E', 'real multi-user isolation', 'Power BI live', 'UI persistence'],
                'csv_sha256': runs['live']['csv_sha256'], 'current_source_sha256': {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'backend/evaluation').glob('qa_*.py')},
                'git_status': subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True).splitlines()}
    write(folder / 'manifest.json', manifest)
    block = ['## Resultados de las ejecuciones', '', f'**{total} turnos del servicio real**, {manifest["distinct_case_ids"]} IDs de caso, más **{baseline["tests_run"]}/{baseline["tests_run"]} regresiones locales**, **3/3** pruebas frontend de historial y **{planner["passed"]}/{planner["total"]}** checks del planner con catálogo sintético y proveedor real (dos repeticiones). Estos conjuntos miden capas diferentes; no se suman en una tasa de exactitud.', '',
             '| Campaña | Turnos | Pass automático | Fail automático | Revisión requerida | Error operativo |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name, run in runs.items():
        s = run['summary']
        block.append(f'| {name} | {len(run["turns"])} | {s["pass"]} | {s["fail"]} | {s["review_required"]} | {s["operational_error"]} |')
    blocked = sum(r.get('blocked_write_attempts', 0) for r in runs.values())
    block.extend(['', '**La tabla conserva checks originales; no es el veredicto semántico final.** En catálogo, 20 auxiliares no pertenecen al contrato de métricas de negocio y dos filtros usaban una dimensión no publicada. Se corrigió la expectativa y se ejecutaron AND/OR con Segmento y Rubro publicados. Ambos operadores mantienen el alcance lógico correcto; AND devuelve la cifra correcta con un desglose innecesario, OR devuelve subtotales correctos y omite el total pedido. Se conservan también los falsos negativos de la fórmula ÷ y las secuencias dependientes de un contexto no establecido.', '',
                  f'**Cero escrituras remotas efectivas**; {blocked} intentos de guardar borradores fueron interceptados. Los gráficos emitidos automáticamente por el servicio se guardaron como eventos y quedaron fuera del score.', '',
                  'En las tres repeticiones críticas, stock actual, corrección negada y olvido de filtros fallan **3/3**. Ranking con criterio explícito, aclaración/resolución de criterio y definición de ticket pasan **3/3**. La comparación temporal falla de formas distintas: agrupación de meses/rubros o respuesta incompleta sin aviso de corte.', '',
                  '## Todos los registros', '',
                  '- ' + link(folder / 'registro-completo.md', 'Preguntas, respuestas completas, consultas, oráculos y checks de los 132 turnos') + '.',
                  '- ' + link(folder / 'manual-review.json', 'Revisión semántica separada de los checks automáticos') + '.',
                  '- ' + link(folder / 'manifest.json', 'Manifiesto, modelos, alcance, hashes y estado del repositorio') + '.',
                  '- ' + link(folder / 'data-profile.json', 'Perfil y referencia independiente con Decimal') + '.',
                  '- ' + link(folder / 'memory-expansion/memory-probes.json', 'Pruebas de corrección intermedia, truncado y negación') + '.',
                  '- ' + link(folder / 'baseline.json', '156 regresiones backend válidas') + ' y ' + link(folder / 'frontend-history.log', 'tres pruebas frontend') + '.',
                  '- ' + link(folder / 'planner-live.json', 'Planner sintético con proveedor real') + ' y ' + link(folder / 'reevaluated-live.json', 'reevaluación de la primera campaña sin sobrescribir sus checks') + '.',
                  '- ' + link(ROOT / 'docs/qa-respuestas/prompt-maestro.md', 'Prompt maestro de la próxima campaña') + '.', '',
                  'Las carpetas de cada campaña contienen `cases.json`, `results.json` y `traces/`. Las trazas y los registros de negocio están excluidos de Git. No se ejecutó una corrección de producción como parte del QA.', '',
                  '## Reproducción', '', 'Desde la raíz, con Python y dependencias del backend disponibles:', '', '```powershell',
                  'python backend/evaluation/qa_offline.py --output scratch/qa-respuestas-NUEVA',
                  'python backend/evaluation/qa_answers.py --output scratch/qa-respuestas-NUEVA/live --repeats 1',
                  'python backend/evaluation/qa_answers.py --cases-file scratch/qa-respuestas-2026-10-14/critical-cases.json --output scratch/qa-respuestas-NUEVA/critical --repeats 3',
                  '```', '', 'Para reproducir exactamente esta campaña, usar sus bancos congelados y los hashes del manifiesto. `qa_catalog_cases.py` fue corregido para futuras campañas: ya no presupone que auxiliares internos estén publicados y usa dimensiones disponibles para AND/OR. La base y el servicio requieren permisos de ejecución/red compatibles con asyncio en Windows y la autorización de datos/destino documentada. Un exit 1 puede representar fallos esperados del QA; el JSON explica cuáles.'])
    text = report_path.read_text(encoding='utf-8')
    start, end = '<!-- RESULTS_START -->', '<!-- RESULTS_END -->'
    text = text.split(start)[0] + '\n'.join(block) + '\n'
    report_path.write_text(text, encoding='utf-8')
    print(json.dumps({'turns': total, 'case_ids': manifest['distinct_case_ids'], 'remote_write_attempts_blocked': blocked, 'report': str(report_path)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    main(args.folder, args.report)
