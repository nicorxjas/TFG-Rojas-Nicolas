import os
import json
import httpx
import traceback
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, Response, status
from datetime import datetime, timezone
from pydantic import BaseModel
from api.llm import llm_client, get_llm_timeout, get_llm_chat_url, get_llm_headers, get_llm_model, llm_is_configured, llm_missing_message, llm_payload
from services import supabase_rest as sb
from services.semantic_query_engine import execute_semantic_query
from services.semantic_catalog import fetch_semantic_catalog
from services.semantic_planner import compile_analysis_plan, evidence_markdown, execute_analysis_plan
from services.company_context import company_context_prompt, fetch_company_context

router = APIRouter(prefix="/reports", tags=["reports"])

# Cargar .env manualmente como fallback si uvicorn no lo levanta automáticamente
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip("'\" "))


GEMINI_URL = get_llm_chat_url()

async def post_with_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """Realiza una petición POST asíncrona con reintentos y backoff exponencial ante fallas transitorias."""
    import asyncio
    max_retries = int(os.getenv("REPORT_LLM_MAX_RETRIES", "5"))
    delay = 3.0
    for attempt in range(max_retries):
        try:
            resp = await client.post(url, **kwargs)
            if resp.status_code in (429, 500, 502, 503, 504):
                print(f"[Retry HTTP POST] {url} respondió con {resp.status_code} (intento {attempt + 1}/{max_retries}). Reintentando en {delay}s...")
                await asyncio.sleep(delay)
                delay *= 2
                continue
            return resp
        except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectTimeout, httpx.NetworkError) as e:
            print(f"[Retry HTTP POST] Error de red o timeout ({type(e).__name__}) al conectar con {url} (intento {attempt + 1}/{max_retries}). Reintentando en {delay}s...")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(delay)
            delay *= 2
    return await client.post(url, **kwargs)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def report_llm_timeout(default_seconds: float) -> float:
    configured = os.getenv("REPORT_LLM_TIMEOUT_SECONDS")
    if configured:
        try:
            return float(configured)
        except ValueError:
            pass
    return default_seconds


def report_llm_max_tokens(default_tokens: int) -> int:
    configured = os.getenv("REPORT_LLM_MAX_TOKENS")
    if configured:
        try:
            return int(configured)
        except ValueError:
            pass
    return default_tokens


def get_report_llm_model() -> str:
    configured = os.getenv("REPORT_LLM_MODEL")
    if configured and configured.strip():
        return configured.strip()
    return get_llm_model()


async def complete_report_llm(client: httpx.AsyncClient, payload: dict, timeout: float) -> str:
    result = await complete_report_llm_result(client, payload, timeout)
    return result["content"]


async def complete_report_llm_result(client: httpx.AsyncClient, payload: dict, timeout: float) -> dict:
    response = await post_with_retry(
        client,
        GEMINI_URL,
        json=llm_payload(payload),
        headers=get_llm_headers(),
        timeout=get_llm_timeout(timeout),
    )
    response.raise_for_status()
    data = response.json()
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return {
        "content": (message.get("content") or "").strip(),
        "finish_reason": choice.get("finish_reason"),
        "usage": data.get("usage") or {},
    }

async def get_with_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """Realiza una petición GET asíncrona con reintentos y backoff exponencial ante fallas transitorias."""
    import asyncio
    max_retries = 5
    delay = 3.0
    for attempt in range(max_retries):
        try:
            resp = await client.get(url, **kwargs)
            if resp.status_code in (429, 500, 502, 503, 504):
                print(f"[Retry HTTP GET] {url} respondió con {resp.status_code} (intento {attempt + 1}/{max_retries}). Reintentando en {delay}s...")
                await asyncio.sleep(delay)
                delay *= 2
                continue
            return resp
        except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectTimeout, httpx.NetworkError) as e:
            print(f"[Retry HTTP GET] Error de red o timeout ({type(e).__name__}) al conectar con {url} (intento {attempt + 1}/{max_retries}). Reintentando en {delay}s...")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(delay)
            delay *= 2
    return await client.get(url, **kwargs)

def get_supabase_headers():
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise Exception("Faltan variables de entorno SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY")
    return {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json"
    }


async def resolve_report_connection_id(report_user_id: str, requested_connection_id: str | None = None) -> str | None:
    if requested_connection_id:
        try:
            catalog = await fetch_semantic_catalog(report_user_id, requested_connection_id)
            matching_connection = next(
                (
                    connection
                    for connection in catalog.get("connections", [])
                    if connection.get("id") == requested_connection_id
                    and connection.get("status") in {"ready", "connected"}
                ),
                None,
            )
            if matching_connection:
                return requested_connection_id
            print(f"[reports] Conexion semantica solicitada no disponible para informes: {requested_connection_id}")
        except Exception as exc:
            print(f"[reports] No se pudo validar la conexion semantica solicitada {requested_connection_id}: {exc}")

    try:
        catalog = await fetch_semantic_catalog(report_user_id, None)
    except Exception as exc:
        print(f"[reports] No se pudo resolver el catalogo semantico activo para informes: {exc}")
        return None

    connections = [
        connection
        for connection in catalog.get("connections", [])
        if connection.get("id") and connection.get("status") in {"ready", "connected"}
    ]
    selected_connection_id = catalog.get("selected_connection_id")
    if selected_connection_id and any(connection.get("id") == selected_connection_id for connection in connections):
        return selected_connection_id

    default_connections = [connection for connection in connections if connection.get("is_default")]
    if len(default_connections) == 1:
        return default_connections[0].get("id")

    if len(connections) == 1:
        return connections[0].get("id")

    return None


def safe_eval_formula(formula: str, context: dict) -> float:
    """Evalúa de forma segura una fórmula matemática simple usando un diccionario de contexto."""
    try:
        # Reemplazar variables en la fórmula
        sorted_keys = sorted(context.keys(), key=len, reverse=True)
        expr = formula
        for k in sorted_keys:
            val = context[k]
            try:
                val_float = float(val) if val is not None else 0.0
            except ValueError:
                val_float = 0.0
            expr = expr.replace(k, str(val_float))
        
        # Sanitizar expresión
        allowed_chars = "0123456789+-*/(). "
        if not all(c in allowed_chars for c in expr):
            raise Exception(f"Caracteres no permitidos en la expresión: {expr}")
        
        return eval(expr, {"__builtins__": None}, {})
    except Exception:
        return 0.0

def aggregate_data(cube_data: list, cube_config: dict) -> dict:
    """Agrega los datos del modelo semantico por cada dimension por separado."""
    cube_query = cube_config.get("cube_query", {})
    measures = cube_query.get("measures", [])
    dimensions = cube_query.get("dimensions", [])
    time_dims = cube_query.get("timeDimensions", [])
    dynamic_metrics = cube_config.get("dynamic_metrics", [])

    time_key = None
    if time_dims:
        base_dim = time_dims[0].get("dimension")
        if cube_data:
            for k in cube_data[0].keys():
                if k.startswith(base_dim):
                    time_key = k
                    break

    aggregated_results = {
        "monthly_evolution": [],
        "by_dimension": {},
        "dimension_time_evolution": {}
    }

    def init_measures():
        return {m: 0.0 for m in measures}

    def finalize_derived_metrics(meas_vals: dict) -> dict:
        return meas_vals

    # 1. Agregación Temporal
    if time_key:
        time_groups = {}
        for row in cube_data:
            t_val = row.get(time_key)
            if not t_val:
                continue
            # Si la granularidad es mensual, agrupar por YYYY-MM. De lo contrario, por día completo YYYY-MM-DD
            granularity = time_dims[0].get("granularity", "day")
            period = t_val[:7] if granularity == "month" else t_val[:10]
            
            if period not in time_groups:
                time_groups[period] = init_measures()
            for m in measures:
                val = row.get(m)
                if val is not None:
                    time_groups[period][m] += float(val)

        for period, meas_vals in sorted(time_groups.items()):
            context = {m: val for m, val in meas_vals.items()}
            for m, val in meas_vals.items():
                context[m.replace(".", "_")] = val
            
            meas_vals = finalize_derived_metrics(meas_vals)
            row_result = {"period": period, **{k.split(".")[-1]: v for k, v in meas_vals.items()}}
            for dm in dynamic_metrics:
                dm_id = dm.get("id")
                formula = dm.get("formula")
                row_result[dm_id] = safe_eval_formula(formula, context)
            aggregated_results["monthly_evolution"].append(row_result)

    # 2. Agregación por cada dimensión
    for dim in dimensions:
        dim_groups = {}
        for row in cube_data:
            dim_val = row.get(dim)
            if dim_val is None:
                dim_val = "<SIN CLASIFICAR>"
            
            if dim_val not in dim_groups:
                dim_groups[dim_val] = init_measures()
            for m in measures:
                val = row.get(m)
                if val is not None:
                    dim_groups[dim_val][m] += float(val)

        dim_list = []
        for d_val, meas_vals in dim_groups.items():
            context = {m: val for m, val in meas_vals.items()}
            for m, val in meas_vals.items():
                context[m.replace(".", "_")] = val
            
            meas_vals = finalize_derived_metrics(meas_vals)
            row_result = {"dimension_value": d_val, **{k.split(".")[-1]: v for k, v in meas_vals.items()}}
            
            # Find a representative row to extract other dimensions
            rep_row = None
            for r in cube_data:
                r_val = r.get(dim)
                if r_val == d_val or (r_val is None and d_val == "<SIN CLASIFICAR>"):
                    rep_row = r
                    break
            if rep_row:
                for other_dim in dimensions:
                    if other_dim != dim:
                        other_val = rep_row.get(other_dim)
                        if other_val is not None:
                            row_result[other_dim.split(".")[-1]] = other_val

            for dm in dynamic_metrics:
                dm_id = dm.get("id")
                formula = dm.get("formula")
                row_result[dm_id] = safe_eval_formula(formula, context)
            dim_list.append(row_result)

        if measures:
            sort_measure = measures[0]
            dim_list = sorted(dim_list, key=lambda x: x.get(sort_measure.split(".")[-1], 0.0), reverse=True)
        
        aggregated_results["by_dimension"][dim.split(".")[-1]] = dim_list[:10]

    # 3. Evolución temporal por dimensión (Cruce de Dimensión + Tiempo)
    if time_key and dimensions:
        for dim in dimensions:
            dim_field = dim.split(".")[-1]
            # No procesamos la misma dimension temporal como cruce consigo misma.
            if dim == time_key:
                continue
                
            dim_time_groups = {}
            for row in cube_data:
                dim_val = row.get(dim)
                if dim_val is None:
                    dim_val = "<SIN CLASIFICAR>"
                
                t_val = row.get(time_key)
                if not t_val:
                    continue
                granularity = time_dims[0].get("granularity", "day")
                period = t_val[:7] if granularity == "month" else t_val[:10]
                
                if dim_val not in dim_time_groups:
                    dim_time_groups[dim_val] = {
                        "dimension_value": dim_val,
                        "total_measures": init_measures(),
                        "history": {}
                    }
                
                for m in measures:
                    val = row.get(m)
                    if val is not None:
                        float_val = float(val)
                        dim_time_groups[dim_val]["total_measures"][m] += float_val
                        
                        if period not in dim_time_groups[dim_val]["history"]:
                            dim_time_groups[dim_val]["history"][period] = {m: 0.0 for m in measures}
                        dim_time_groups[dim_val]["history"][period][m] += float_val
            
            dim_time_list = []
            for d_val, group in dim_time_groups.items():
                # Find a representative row to extract other dimensions
                rep_row = None
                for r in cube_data:
                    r_val = r.get(dim)
                    if r_val == d_val or (r_val is None and d_val == "<SIN CLASIFICAR>"):
                        rep_row = r
                        break
                
                # Totales de la dimensión
                context_totals = {m: val for m, val in group["total_measures"].items()}
                for m, val in group["total_measures"].items():
                    context_totals[m.replace(".", "_")] = val
                
                group["total_measures"] = finalize_derived_metrics(group["total_measures"])
                totals_clean = {k.split(".")[-1]: v for k, v in group["total_measures"].items()}
                for dm in dynamic_metrics:
                    dm_id = dm.get("id")
                    formula = dm.get("formula")
                    totals_clean[dm_id] = safe_eval_formula(formula, context_totals)
                
                # Copiar otras dimensiones a totals_clean
                if rep_row:
                    for other_dim in dimensions:
                        if other_dim != dim:
                            other_val = rep_row.get(other_dim)
                            if other_val is not None:
                                totals_clean[other_dim.split(".")[-1]] = other_val
                
                # Historial temporal
                history_formatted = []
                for period, period_meas in group["history"].items():
                    context_period = {m: val for m, val in period_meas.items()}
                    for m, val in period_meas.items():
                        context_period[m.replace(".", "_")] = val
                    
                    period_meas = finalize_derived_metrics(period_meas)
                    period_clean = {"period": period, **{k.split(".")[-1]: v for k, v in period_meas.items()}}
                    for dm in dynamic_metrics:
                        dm_id = dm.get("id")
                        formula = dm.get("formula")
                        period_clean[dm_id] = safe_eval_formula(formula, context_period)
                    history_formatted.append(period_clean)
                
                # Ordenar historial cronológicamente
                history_formatted = sorted(history_formatted, key=lambda x: x["period"])
                
                dim_time_list.append({
                    "dimension_value": d_val,
                    "totals": totals_clean,
                    "history": history_formatted
                })
            
            # Ordenar las dimensiones por la medida principal total
            if measures:
                sort_measure = measures[0].split(".")[-1]
                dim_time_list = sorted(dim_time_list, key=lambda x: x["totals"].get(sort_measure, 0.0), reverse=True)
            
            limit = 30 if len(dim_time_list) > 20 else 20
            aggregated_results["dimension_time_evolution"][dim_field] = dim_time_list[:limit]

    return aggregated_results


def compact_report_data_for_llm(aggregated_data: dict) -> dict:
    """Reduce el payload para modelos locales sin perder las señales analíticas principales."""
    aggregated_data = aggregated_data or {}
    analytical_packs = aggregated_data.get("analytical_packs") or {}
    if analytical_packs:
        return {
            "analytical_packs": analytical_packs,
        }

    compact = {
        "monthly_evolution": (aggregated_data.get("monthly_evolution") or [])[-18:],
        "by_dimension": {},
        "dimension_time_evolution": {},
        "analytical_packs": analytical_packs,
    }

    for dim, rows in (aggregated_data.get("by_dimension") or {}).items():
        compact["by_dimension"][dim] = (rows or [])[:8]

    for dim, rows in (aggregated_data.get("dimension_time_evolution") or {}).items():
        compact_rows = []
        for row in (rows or [])[:8]:
            compact_rows.append({
                "dimension_value": row.get("dimension_value"),
                "totals": row.get("totals", {}),
                "history": (row.get("history") or [])[-12:],
            })
        compact["dimension_time_evolution"][dim] = compact_rows

    return compact


def evidence_ids_from_result(evidence_result: dict | None) -> list[str]:
    ids = []
    for item in (evidence_result or {}).get("evidence") or []:
        evidence_id = item.get("evidence_id")
        if evidence_id:
            ids.append(evidence_id)
    return ids


def filter_agent_findings_by_evidence(findings: str, evidence_ids: list[str]) -> str:
    if not findings or not evidence_ids:
        return findings or ""
    kept = []
    for line in findings.splitlines():
        stripped = line.strip()
        has_number = any(ch.isdigit() for ch in stripped)
        has_evidence = any(evidence_id in stripped for evidence_id in evidence_ids)
        if not stripped or stripped.startswith("#") or not has_number or has_evidence:
            kept.append(line)
    filtered = "\n".join(kept).strip()
    if filtered:
        return filtered
    return "Sin claims cuantitativos verificados con evidencia suficiente."


def build_report_analysis_prompt(report_data: dict, template: dict | None, agents_info: list[dict], custom_notes: str | None) -> str:
    template_payload = {}
    if template:
        template_payload = {
            "name": template.get("name"),
            "description": template.get("description"),
            "system_prompt": template.get("system_prompt"),
            "cube_query_config": template.get("cube_query_config"),
        }
    return "\n".join([
        f"Nombre del informe: {report_data.get('name') or ''}",
        f"Notas del usuario: {custom_notes or 'No se especificaron notas.'}",
        f"Plantilla: {json.dumps(template_payload, ensure_ascii=False)}",
        f"Agentes asignados: {json.dumps(agents_info or [], ensure_ascii=False)}",
        "Planifica todas las consultas necesarias para que el informe tenga hallazgos cuantitativos, riesgos, oportunidades y acciones respaldadas por evidencia.",
    ])


def _fmt_num(value) -> str:
    try:
        num = float(value or 0)
    except (TypeError, ValueError):
        return str(value)
    if num.is_integer():
        return f"{int(num):,}".replace(",", ".")
    return f"{num:,.2f}"


def _fmt_money(value) -> str:
    try:
        num = float(value or 0)
    except (TypeError, ValueError):
        return str(value)
    return f"${num:,.0f}".replace(",", ".")


def _metric(row: dict, *names: str, default=0.0) -> float:
    for name in names:
        if name in row and row.get(name) is not None:
            try:
                return float(row.get(name) or 0)
            except (TypeError, ValueError):
                return default
    return default


def _pct(value) -> str:
    try:
        return f"{float(value or 0) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(value)


def build_deterministic_report_content(
    aggregated_data: dict,
    report_scope: dict,
    report_name: str,
    custom_notes: str,
    fallback_reason: str | None = None,
    agent_findings: dict | None = None,
) -> dict:
    monthly = aggregated_data.get("monthly_evolution") or []
    by_dimension = aggregated_data.get("by_dimension") or {}
    latest = monthly[-1] if monthly else {}
    previous = monthly[-2] if len(monthly) > 1 else {}

    lines = [
        f"# {report_name or 'Informe analítico'}",
        "",
        "## Resumen ejecutivo",
    ]
    if fallback_reason:
        lines.append(
            "El informe fue generado con el motor analítico determinístico porque el LLM local no respondió dentro del tiempo operativo. "
            "Los hallazgos se basan estrictamente en los datos consultados en el modelo semantico activo."
        )
    if custom_notes:
        lines.append(f"Pedido analizado: {custom_notes}")

    analytical_packs = aggregated_data.get("analytical_packs") or {}
    evidence_items = analytical_packs.get("evidence") or []
    if evidence_items:
        lines.extend(["", "## Evidencia verificada"])
        for evidence in evidence_items[:4]:
            lines.append(f"### {evidence.get('label') or evidence.get('evidence_id') or 'Evidencia'}")
            if evidence.get("purpose"):
                lines.append(str(evidence.get("purpose")))
            virtual_results = evidence.get("virtual_metric_results") or {}
            for metric_key, result in virtual_results.items():
                count = result.get("count")
                metric_name = result.get("name") or metric_key
                if count is not None:
                    lines.append(f"- {metric_name}: **{_fmt_num(count)} casos**.")
                matching_rows = result.get("matching_rows") or []
                for row in matching_rows[:10]:
                    labels = []
                    for key, value in row.items():
                        if key.startswith("virtual_") or key.startswith("virtual."):
                            continue
                        if key in ((evidence.get("query") or {}).get("measures") or []):
                            continue
                        if value not in (None, ""):
                            labels.append(str(value))
                    if labels:
                        lines.append(f"  - {' | '.join(labels[:4])}")

    if latest:
        period = latest.get("period", "ultimo periodo disponible")
        lines.append(f"Ultimo periodo disponible: **{period}**.")
        metric_lines = []
        for key, value in latest.items():
            if key == "period" or not isinstance(value, (int, float)):
                continue
            formatted = _fmt_money(value) if any(term in key for term in ["monto", "importe", "costo", "precio", "revenue"]) else _fmt_num(value)
            metric_lines.append(f"- {key}: **{formatted}**.")
            if len(metric_lines) >= 6:
                break
        lines.extend(metric_lines)
    lines.extend(["", "## Lecturas por dimension"])
    dimension_sections = 0
    for dimension_name, rows in by_dimension.items():
        if not rows:
            continue
        dimension_sections += 1
        lines.append(f"### {dimension_name}")
        for row in rows[:5]:
            metric_parts = []
            for key, value in row.items():
                if key == "dimension_value" or not isinstance(value, (int, float)):
                    continue
                metric_parts.append(f"{key}: {_fmt_money(value) if any(term in key for term in ['monto', 'importe', 'costo', 'precio', 'revenue']) else _fmt_num(value)}")
                if len(metric_parts) >= 3:
                    break
            suffix = f" ({'; '.join(metric_parts)})" if metric_parts else ""
            lines.append(f"- **{row.get('dimension_value')}**{suffix}.")
        if dimension_sections >= 3:
            break
    if not dimension_sections:
        lines.append("No hay dimensiones agrupadas disponibles en la consulta del informe.")

    if agent_findings:
        lines.extend(["", "## Hallazgos de agentes"])
        for agent_name, findings in agent_findings.items():
            if findings:
                lines.append(f"### {agent_name}")
                lines.append(str(findings))

    actionables = [
        {
            "priority": "MEDIUM",
            "text": "Revisar las principales variaciones y concentraciones detectadas en las dimensiones disponibles del modelo semantico.",
        },
        {
            "priority": "MEDIUM",
            "text": "Si se necesita mayor precision, regenerar el informe con un periodo o una dimension especifica del catalogo activo.",
        },
    ]
    return {
        "executive_summary": "\n".join(lines),
        "actionables": actionables,
    }

def clean_and_parse_json(raw_str: str) -> dict:
    """Limpia y parsea de forma robusta un string JSON que puede contener bloques markdown o caracteres extraños."""
    import re
    s = raw_str.strip()
    
    # Remover bloques de código markdown si existen (```json ... ``` o ``` ... ```)
    if s.startswith("```"):
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline:].strip()
        else:
            s = s[3:].strip()
    if s.endswith("```"):
        s = s[:-3].strip()
    
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    
    # Intentar parseo directo primero
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    
    # Sanitización agresiva para respuestas de LLM con Markdown embebido:
    # 1. Escapar caracteres de control dentro de strings JSON (newlines, tabs literales)
    #    Procesamos carácter por carácter para escapar solo dentro de strings JSON
    def sanitize_json_strings(text: str) -> str:
        result = []
        in_string = False
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == '\\' and in_string:
                # Escape sequence - pasar el siguiente carácter tal cual
                if i + 1 < len(text):
                    result.append(ch)
                    result.append(text[i + 1])
                    i += 2
                    continue
                else:
                    result.append(ch)
                    i += 1
                    continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
            elif in_string:
                if ch == '\n':
                    result.append('\\n')
                elif ch == '\t':
                    result.append('\\t')
                else:
                    result.append(ch)
            else:
                result.append(ch)
            i += 1
        return ''.join(result)
    
    s_sanitized = sanitize_json_strings(s)
    
    # 2. Remover trailing commas antes de } o ]
    s_sanitized = re.sub(r',\s*([}\]])', r'\1', s_sanitized)
    
    return json.loads(s_sanitized)

def _looks_like_truncated_report_text(value: str) -> bool:
    import re

    text = (value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if text.endswith((",", ";", ":", "-", "(", "[", "{", "/")):
        return True
    if text.count("```") % 2:
        return True
    if re.search(r"\b20\d{0,1}$", text):
        return True
    if re.search(r"\b(?:de|del|para|por|con|en|y|e|o|que|segun|según|sobre|hacia|desde|entre)\s*$", lowered):
        return True
    last_line = text.splitlines()[-1].strip()
    if re.match(r"^#{1,6}\s+\S", last_line):
        return True
    return False


def validate_report_content_complete(report_content: dict, *, finish_reason: str | None = None) -> None:
    normalized_finish_reason = str(finish_reason or "").lower()
    if normalized_finish_reason and normalized_finish_reason not in {"stop", "tool_calls"}:
        raise ValueError(f"El LLM corto la respuesta antes de terminar: finish_reason={finish_reason}")
    if not isinstance(report_content, dict):
        raise ValueError("El informe generado no es un objeto JSON.")

    summary = report_content.get("executive_summary")
    if not isinstance(summary, str) or len(summary.strip()) < 120:
        raise ValueError("El resumen ejecutivo del informe esta vacio o incompleto.")
    if _looks_like_truncated_report_text(summary):
        raise ValueError("El resumen ejecutivo parece truncado.")

    actionables = report_content.get("actionables")
    if actionables is not None:
        if not isinstance(actionables, list):
            raise ValueError("Los accionables del informe no tienen formato de lista.")
        for action in actionables:
            text = action.get("text") if isinstance(action, dict) else None
            if isinstance(text, str) and _looks_like_truncated_report_text(text):
                raise ValueError("Un accionable del informe parece truncado.")


def normalize_text(value) -> str:
    return (value or "").strip().lower()

def build_report_scope(agents_info: list, custom_notes: str, template: dict, aggregated_data: dict) -> dict:
    """Construye el alcance editorial del informe a partir de agentes, notas y datos disponibles."""
    agents_info = agents_info or []
    categories = {normalize_text(agent.get("category")) for agent in agents_info if agent.get("category")}
    agent_text = " ".join(
        normalize_text(" ".join([
            agent.get("name") or "",
            agent.get("description") or "",
            agent.get("category") or ""
        ]))
        for agent in agents_info
    )
    notes_text = normalize_text(custom_notes)
    template_text = normalize_text(" ".join([
        template.get("name", "") if template else "",
        template.get("description", "") if template else "",
        template.get("system_prompt", "") if template else ""
    ]))

    available_dimensions = sorted(set(
        list((aggregated_data or {}).get("by_dimension", {}).keys()) +
        list((aggregated_data or {}).get("dimension_time_evolution", {}).keys())
    ))
    has_client_data = any(any(keyword in normalize_text(dim) for keyword in ("cliente", "customer", "cuenta", "account")) for dim in available_dimensions)

    client_keywords = ("cliente", "clientes", "cuenta", "cuentas", "churn", "retencion", "retención", "abandono")
    explicit_client_need = any(keyword in notes_text for keyword in client_keywords)
    client_agent = (
        "churn" in categories or
        "clientes" in categories or
        "retencion" in categories or
        "retención" in categories or
        any(keyword in agent_text for keyword in ("churn", "retencion", "retención", "abandono"))
    )
    client_template = any(keyword in template_text for keyword in ("churn", "retencion", "retención", "abandono"))
    allow_client_detail = bool(has_client_data and (client_agent or explicit_client_need or client_template))

    focus_domains = []
    domain_by_category = {
        "finanzas": "finanzas",
        "churn": "retencion",
        "clientes": "clientes",
        "oportunidad": "oportunidades",
        "oportunidades": "oportunidades",
        "riesgos": "riesgos",
        "inventario": "inventario",
        "stock": "inventario",
        "supply": "inventario",
    }
    for category in sorted(categories):
        domain = domain_by_category.get(category)
        if domain and domain not in focus_domains:
            focus_domains.append(domain)

    if not focus_domains:
        focus_domains = ["analisis_general"]

    if allow_client_detail and "clientes" not in focus_domains and "retencion" not in focus_domains:
        focus_domains.append("clientes")

    if allow_client_detail:
        client_rule = (
            "Puedes incluir una seccion de clientes solamente si usas nombres exactos presentes "
            "en los datos o en hallazgos de agentes, con la metrica que justifica cada mencion."
        )
    else:
        client_rule = (
            "No generes secciones llamadas 'Clientes en riesgo', 'clientes criticos' ni listados "
            "de clientes. Si aparece alguna mencion aislada de clientes en una plantilla o agente, "
            "mantenerla solo como metrica agregada y sin nombres propios."
        )

    return {
        "assigned_agents": [
            {
                "name": agent.get("name"),
                "category": agent.get("category"),
                "description": agent.get("description")
            }
            for agent in agents_info
        ],
        "focus_domains": focus_domains,
        "available_dimensions": available_dimensions,
        "has_client_data": has_client_data,
        "allow_client_detail": allow_client_detail,
        "client_rule": client_rule,
    }

def build_report_json_structure(include_charts: bool, allow_client_detail: bool) -> str:
    client_guidance = (
        "Si el alcance permite detalle de clientes y los datos lo justifican, incluir una seccion especifica con nombres exactos y evidencia numerica."
        if allow_client_detail
        else "No incluir secciones ni listados de clientes; el contenido debe seguir solo los dominios de los agentes asignados."
    )
    return f"""{{
  "executive_summary": "Resumen ejecutivo en Markdown, completo y bien estructurado. Debe sintetizar solo los dominios cubiertos por los agentes asignados y las notas del usuario. {client_guidance} No usar marcadores de posicion. Usar solo texto y tablas Markdown; no incluir imagenes, graficos, Mermaid, SVG ni codigo de visualizacion.",
  "actionables": [
    {{ "priority": "HIGH" | "MEDIUM" | "LOW", "text": "Accion recomendada sustentada en datos o hallazgos de agentes..." }}
  ]
}}"""

def enforce_report_scope(report_content: dict, report_scope: dict) -> dict:
    """Aplica una ultima barrera deterministica para que el informe no agregue clientes fuera de alcance."""
    if isinstance(report_content, dict):
        report_content.pop("chart_data", None)
    if not isinstance(report_content, dict) or report_scope.get("allow_client_detail"):
        return report_content

    import re

    summary = report_content.get("executive_summary")
    if isinstance(summary, str):
        # Quita secciones completas de Markdown dedicadas a clientes cuando no son parte del alcance.
        summary = re.sub(
            r"(?ims)^#{1,6}\s+[^\n]*(?:clientes?|churn|retenci[oó]n|abandono)[^\n]*\n.*?(?=^#{1,6}\s+|\Z)",
            "",
            summary
        ).strip()
        report_content["executive_summary"] = summary

    actionables = report_content.get("actionables")
    if isinstance(actionables, list):
        disallowed = re.compile(r"\b(clientes?\s+en\s+riesgo|churn|retenci[oó]n|abandono)\b", re.IGNORECASE)
        filtered = []
        for action in actionables:
            text = action.get("text", "") if isinstance(action, dict) else str(action)
            if not disallowed.search(text):
                filtered.append(action)
        report_content["actionables"] = filtered or actionables

    return report_content

def build_report_catalog_surface(semantic_catalog: dict, metric_catalog: list[dict] | None = None) -> dict:
    metric_catalog = metric_catalog or []
    metrics_by_key: dict[str, dict] = {}
    for metric in semantic_catalog.get("metrics") or []:
        key = metric.get("key")
        if not key or metric.get("source") == "aggregate_helper":
            continue
        metrics_by_key[key] = {
            "key": key,
            "name": metric.get("name") or key,
            "description": metric.get("description") or "",
            "format": metric.get("format") or "number",
            "source": metric.get("source") or metric.get("provider") or "semantic",
            "cube_dependencies": metric.get("cube_dependencies") or metric.get("provider_dependencies") or [key],
        }
    for metric in metric_catalog:
        key = metric.get("key")
        if metric.get("source") == "custom" and key:
            metrics_by_key[key] = {
                "key": key,
                "name": metric.get("name") or key,
                "description": metric.get("description") or "",
                "format": metric.get("format") or "number",
                "source": "custom",
                "cube_dependencies": metric.get("cube_dependencies") or metric.get("provider_dependencies") or [],
            }

    dimensions = []
    time_dimensions = []
    for field in semantic_catalog.get("fields") or []:
        key = field.get("semantic_key")
        if not key or field.get("is_hidden") or not field.get("is_ai_enabled", True):
            continue
        kind = field.get("field_kind") or "unknown"
        item = {
            "key": key,
            "name": field.get("business_name") or field.get("suggested_business_name") or field.get("display_name") or field.get("name") or key,
            "description": field.get("description") or field.get("suggested_description") or "",
            "kind": kind,
            "data_type": field.get("data_type") or kind,
        }
        if kind == "measure":
            continue
        if kind == "time":
            time_dimensions.append(item)
        else:
            dimensions.append(item)

    relationships = []
    seen_relationships = set()
    for rel in semantic_catalog.get("relationships") or []:
        relationship_key = (rel.get("from_table"), rel.get("to_table"))
        if not all(relationship_key) or relationship_key in seen_relationships:
            continue
        seen_relationships.add(relationship_key)
        relationships.append({
            "from_table": rel.get("from_table"),
            "to_table": rel.get("to_table"),
            "active": rel.get("is_active", True),
        })

    return {
        "metrics": list(metrics_by_key.values()),
        "dimensions": dimensions,
        "time_dimensions": time_dimensions,
        "relationships": relationships,
        "metric_keys": set(metrics_by_key.keys()),
        "dimension_keys": {item["key"] for item in dimensions},
        "time_keys": {item["key"] for item in time_dimensions},
    }


def _explicit_report_date_range(text: str) -> list[str] | None:
    normalized = normalize_text(text)
    import calendar
    import re
    months = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "setiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }
    for month_name, month_number in months.items():
        match = re.search(rf"\b{month_name}\s+(20\d{{2}})\b", normalized)
        if match:
            year = int(match.group(1))
            days = calendar.monthrange(year, month_number)[1]
            return [f"{year}-{month_number:02d}-01", f"{year}-{month_number:02d}-{days:02d}"]
    year_match = re.search(r"\b(20\d{2})\b", normalized)
    if year_match:
        year = year_match.group(1)
        return [f"{year}-01-01", f"{year}-12-31"]
    return None


def _coerce_report_limit(value, default: int = 1000) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = default
    return max(1, min(limit, 10000))


def report_cube_from_member(member: object) -> str | None:
    if not isinstance(member, str) or "." not in member:
        return None
    cube_name = member.split(".", 1)[0]
    return cube_name or None


def report_metric_source_cubes(surface: dict, measure_key: str | None) -> set[str]:
    if not measure_key:
        return set()
    metric = next((item for item in surface.get("metrics") or [] if item.get("key") == measure_key), None)
    dependencies = (metric or {}).get("cube_dependencies") or [measure_key]
    cubes = {
        cube
        for cube in (report_cube_from_member(dependency) for dependency in dependencies)
        if cube and cube != "Metricas"
    }
    if cubes:
        return cubes
    direct_cube = report_cube_from_member(measure_key)
    return {direct_cube} if direct_cube and direct_cube != "Metricas" else set()


def report_relationship_graph(surface: dict) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for relationship in surface.get("relationships") or []:
        if relationship.get("active") is False:
            continue
        from_cube = report_cube_from_member(relationship.get("from"))
        to_cube = report_cube_from_member(relationship.get("to"))
        if not from_cube or not to_cube:
            continue
        graph.setdefault(from_cube, set()).add(to_cube)
    return graph


def report_reachable_cubes(surface: dict, source_cube: str | None) -> set[str]:
    if not source_cube:
        return set()
    graph = report_relationship_graph(surface)
    seen = {source_cube}
    pending = [source_cube]
    while pending:
        cube = pending.pop()
        for neighbor in graph.get(cube, set()):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            pending.append(neighbor)
    return seen


def report_member_compatible(surface: dict, source_cube: str | None, member: str | None) -> bool:
    member_cube = report_cube_from_member(member)
    if not source_cube or not member_cube:
        return True
    return member_cube in report_reachable_cubes(surface, source_cube)


def report_measure_compatible(surface: dict, source_cube: str | None, measure_key: str | None) -> bool:
    source_cubes = report_metric_source_cubes(surface, measure_key)
    if not source_cube or not source_cubes:
        return True
    return source_cubes == {source_cube}


def choose_report_source_cube(surface: dict, measures: list[str], dimensions: list[str], time_dimensions: list[dict]) -> str | None:
    candidates: list[str] = []
    for measure in measures:
        for cube in sorted(report_metric_source_cubes(surface, measure)):
            if cube not in candidates:
                candidates.append(cube)
    if not candidates:
        return None

    def score(candidate: str) -> tuple[int, int]:
        value = 0
        for measure in measures:
            value += 3 if report_measure_compatible(surface, candidate, measure) else -3
        for dimension in dimensions:
            value += 1 if report_member_compatible(surface, candidate, dimension) else -2
        for item in time_dimensions:
            dimension = item.get("dimension") if isinstance(item, dict) else None
            if not dimension:
                continue
            time_cube = report_cube_from_member(dimension)
            if time_cube == candidate:
                value += 6
            elif report_member_compatible(surface, candidate, dimension):
                value += 2
            else:
                value -= 4
        return (value, -candidates.index(candidate))

    return max(candidates, key=score)


def preferred_report_time_dimension(surface: dict, source_cube: str | None) -> str | None:
    fields = surface.get("time_dimensions") or []
    if source_cube:
        same_cube = next((field for field in fields if str(field.get("key", "")).startswith(f"{source_cube}.")), None)
        if same_cube:
            return same_cube["key"]
        compatible = next(
            (
                field
                for field in fields
                if report_member_compatible(surface, source_cube, field.get("key"))
            ),
            None,
        )
        if compatible:
            return compatible["key"]
    return fields[0]["key"] if fields else None


def valid_report_granularity(value: object) -> str | None:
    if isinstance(value, str) and value in {"day", "week", "month", "quarter", "year"}:
        return value
    return None


def _sanitize_report_query(raw_query: dict | None, surface: dict, date_range: list[str] | None = None) -> dict:
    raw_query = raw_query or {}
    metric_keys = surface["metric_keys"]
    dimension_keys = surface["dimension_keys"]
    time_keys = surface["time_keys"]

    measures = [m for m in raw_query.get("measures", []) if isinstance(m, str) and m in metric_keys]
    if not measures:
        measures = [metric["key"] for metric in surface["metrics"][:3]]
    if not measures:
        raise ValueError("El catalogo semantico activo no tiene metricas disponibles para informes.")

    dimensions = [d for d in raw_query.get("dimensions", []) if isinstance(d, str) and d in dimension_keys]
    raw_time_dimensions = [item for item in raw_query.get("timeDimensions", []) or [] if isinstance(item, dict)]
    source_cube = choose_report_source_cube(surface, measures, dimensions, raw_time_dimensions)
    if source_cube:
        compatible_measures = [
            measure for measure in measures if report_measure_compatible(surface, source_cube, measure)
        ]
        if compatible_measures:
            measures = compatible_measures
        dimensions = [
            dimension for dimension in dimensions if report_member_compatible(surface, source_cube, dimension)
        ]

    if not dimensions and surface["dimensions"]:
        dimensions = [
            item["key"]
            for item in surface["dimensions"]
            if report_member_compatible(surface, source_cube, item["key"])
        ][:1]

    time_dimensions = []
    for item in raw_query.get("timeDimensions", []) or []:
        if not isinstance(item, dict):
            continue
        dimension = item.get("dimension")
        if not isinstance(dimension, str) or dimension not in time_keys:
            continue
        if source_cube and not report_member_compatible(surface, source_cube, dimension):
            dimension = preferred_report_time_dimension(surface, source_cube)
            if not dimension:
                continue
        clean_item = {"dimension": dimension}
        granularity = valid_report_granularity(item.get("granularity"))
        if granularity:
            clean_item["granularity"] = granularity
        if date_range:
            clean_item["dateRange"] = date_range
        elif isinstance(item.get("dateRange"), list) and len(item.get("dateRange")) == 2:
            clean_item["dateRange"] = item.get("dateRange")
        time_dimensions.append(clean_item)
        break

    if not time_dimensions and surface["time_dimensions"]:
        preferred_dimension = preferred_report_time_dimension(surface, source_cube)
        clean_item = {"dimension": preferred_dimension or surface["time_dimensions"][0]["key"], "granularity": "month"}
        if date_range:
            clean_item["dateRange"] = date_range
        time_dimensions.append(clean_item)

    query = {
        "measures": measures[:6],
        "limit": _coerce_report_limit(raw_query.get("limit"), 1000),
    }
    if dimensions:
        query["dimensions"] = dimensions[:4]
    if time_dimensions:
        query["timeDimensions"] = time_dimensions

    filters = []
    allowed_filter_members = metric_keys | dimension_keys | time_keys
    for item in raw_query.get("filters", []) or []:
        if not isinstance(item, dict):
            continue
        member = item.get("member") or item.get("dimension") or item.get("measure")
        if (
            isinstance(member, str)
            and member in allowed_filter_members
            and report_member_compatible(surface, source_cube, member)
        ):
            filters.append(item)
    if filters:
        query["filters"] = filters
    return query


def build_heuristic_cube_config(
    custom_notes: str,
    template_config: dict = None,
    assigned_agents: list = None,
    metric_catalog: list = None,
    semantic_catalog: dict | None = None,
) -> dict:
    if not semantic_catalog:
        raise ValueError("Los informes requieren un catalogo semantico activo.")
    surface = build_report_catalog_surface(semantic_catalog, metric_catalog)
    date_range = _explicit_report_date_range(" ".join([
        custom_notes or "",
        json.dumps(assigned_agents or [], ensure_ascii=False),
    ]))
    base_query = template_config.get("cube_query", {}) if isinstance(template_config, dict) else {}
    return {"cube_query": _sanitize_report_query(base_query, surface, date_range), "dynamic_metrics": []}


async def generate_dynamic_cube_config(
    custom_notes: str,
    gemini_key: str = "",
    template_config: dict = None,
    assigned_agents: list = None,
    metric_catalog: list = None,
    semantic_catalog: dict | None = None,
) -> dict:
    if not semantic_catalog:
        raise ValueError("Los informes requieren un catalogo semantico activo.")
    surface = build_report_catalog_surface(semantic_catalog, metric_catalog)
    if not surface["metrics"]:
        raise ValueError("El catalogo semantico activo no tiene metricas disponibles para informes.")

    date_range = _explicit_report_date_range(" ".join([
        custom_notes or "",
        json.dumps(assigned_agents or [], ensure_ascii=False),
    ]))

    catalog_payload = {
        "metrics": surface["metrics"][:120],
        "dimensions": surface["dimensions"][:160],
        "timeDimensions": surface["time_dimensions"][:40],
        "relationships": surface["relationships"][:120],
    }
    system_prompt = """Sos el traductor semantico de informes de Nyro.
Devolve exclusivamente JSON valido con los campos cube_query y dynamic_metrics.
Usa solo keys exactas del catalogo recibido. No inventes tablas, campos, metricas, formulas ni miembros.
El modelo semantico calcula las metricas; no crees formulas inline.
Si una plantilla trae miembros que no existen en el catalogo activo, descartalos.
No mezcles measures de facts o cubos no relacionados en una misma cube_query. Si el pedido cubre varios dominios, elegi el dominio principal mas relevante para la consulta.
Usa dimensiones y fechas compatibles con el cubo/fact de las metricas elegidas segun catalog.relationships.
Para tendencias usa timeDimensions con granularity. Para rankings usa dimensions y limit.
"""
    user_prompt = f"""Pedido del usuario: {custom_notes or 'No se proporcionaron notas especificas.'}
Agentes asignados: {json.dumps(assigned_agents or [], ensure_ascii=False)}
Plantilla base: {json.dumps(template_config or {}, ensure_ascii=False)}
Rango de fechas detectado por backend: {json.dumps(date_range, ensure_ascii=False) if date_range else 'ninguno'}
Catalogo activo: {json.dumps(catalog_payload, ensure_ascii=False)}
"""

    try:
        async with llm_client(trust_env=False) as client:
            payload = llm_payload({
                "model": get_report_llm_model(),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "stream": False,
                "temperature": 0.05,
            })
            resp = await post_with_retry(
                client,
                GEMINI_URL,
                json=payload,
                headers=get_llm_headers(),
                timeout=get_llm_timeout(60.0),
            )
            resp.raise_for_status()
            raw_content = resp.json()["choices"][0]["message"]["content"].strip()
            config = clean_and_parse_json(raw_content)
            if isinstance(config, dict):
                return {
                    "cube_query": _sanitize_report_query(config.get("cube_query") or config.get("query"), surface, date_range),
                    "dynamic_metrics": [],
                }
    except Exception as exc:
        print(f"[!] Error generando query semantica dinamica para informe: {exc}. Usando fallback de catalogo activo.")

    return build_heuristic_cube_config(
        custom_notes=custom_notes,
        template_config=template_config,
        assigned_agents=assigned_agents,
        metric_catalog=metric_catalog,
        semantic_catalog=semantic_catalog,
    )
async def process_report_async(report_id: str):
    import asyncio
    try:
        supabase_url = os.environ.get("SUPABASE_URL")
        
        if not llm_is_configured():
            raise Exception(llm_missing_message())

        print(f"[{report_id}] Procesando reporte de forma asíncrona...")

        async with llm_client() as client:
            # 1. Actualizar estado a GENERATING
            headers = get_supabase_headers()
            await client.patch(
                f"{supabase_url}/rest/v1/reports?id=eq.{report_id}",
                json={"status": "GENERATING", "updated_at": utc_now_iso(), "error_log": None},
                headers=headers
            )

            # 2. Leer información del reporte, template y agentes asociados
            res = await client.get(
                f"{supabase_url}/rest/v1/reports?id=eq.{report_id}&select=*,report_agents(agents(*))",
                headers=headers
            )
            res.raise_for_status()
            report_data_list = res.json()
            
            if not report_data_list:
                raise Exception("Reporte no encontrado en base de datos")
            
            report_data = report_data_list[0]
            report_user_id = report_data.get("user_id")
            requested_connection_id = report_data.get("semantic_connection_id") or report_data.get("connection_id")
            template = None
            custom_notes = report_data.get("prompt")
            if not report_user_id:
                raise Exception("El informe no tiene usuario asociado.")
            report_connection_id = await resolve_report_connection_id(report_user_id, requested_connection_id)
            if not report_connection_id:
                raise Exception("El informe requiere una conexion semantica activa. Conecta y selecciona una fuente lista antes de generarlo.")
            from api.semantic_metrics import build_metric_catalog
            metric_catalog = await build_metric_catalog(user_id=report_user_id, connection_id=report_connection_id)
            semantic_catalog = await fetch_semantic_catalog(report_user_id, report_connection_id)
            try:
                business_context_text = company_context_prompt(await fetch_company_context(report_user_id))
            except Exception:
                business_context_text = "Contexto de empresa no disponible."

            # Obtener nombres e información detallada de agentes asignados para el generador dinámico de queries
            report_agents = report_data.get("report_agents", [])
            agent_names = []
            agents_info = []
            for ra in report_agents:
                agent = ra.get("agents")
                if agent:
                    agent_name = agent.get("name")
                    agent_names.append(agent_name)
                    agents_info.append({
                        "name": agent_name,
                        "category": agent.get("category"),
                        "description": agent.get("description"),
                        "system_prompt": agent.get("system_prompt")
                    })

            # A. Obtener o Generar Dinámicamente la configuracion semantica
            base_cube_config = None
            if template:
                cube_config_raw = template.get("cube_query_config", {})
                if isinstance(cube_config_raw, str):
                    base_cube_config = json.loads(cube_config_raw)
                else:
                    base_cube_config = cube_config_raw
                system_prompt = template.get("system_prompt", "")
            else:
                system_prompt = "Eres un analista experto en inteligencia empresarial de Nyro Analytics."

            # Si hay notas personalizadas del usuario, o agentes específicos asignados, o no hay plantilla,
            # regeneramos la query de forma inteligente para adaptarla al contexto y agentes.
            print(f"[{report_id}] Compilando plan semantico y evidence packs...")
            evidence_result = {}
            evidence_text = ""
            analysis_plan = None
            try:
                analysis_prompt = build_report_analysis_prompt(report_data, template, agents_info, custom_notes)
                analysis_plan = await compile_analysis_plan(
                    prompt=analysis_prompt,
                    user_id=report_user_id,
                    connection_id=report_connection_id,
                    metric_catalog=metric_catalog,
                    semantic_catalog=semantic_catalog,
                    context={
                        "report_id": report_id,
                        "report_name": report_data.get("name"),
                        "agents": agents_info,
                        "template": template.get("name") if template else None,
                        "business_context": business_context_text,
                    },
                    use_llm=True,
                )
                evidence_result = await execute_analysis_plan(
                    plan=analysis_plan,
                    user_id=report_user_id,
                    connection_id=report_connection_id,
                    persist=True,
                    report_id=report_id,
                )
            except Exception as planner_exc:
                print(f"[{report_id}] Planner semantico fallo; usando fallback anterior: {planner_exc}")
                evidence_result = {
                    "evidence": [],
                    "evidence_digest": [],
                    "warnings": [str(planner_exc)],
                    "validation_errors": [str(planner_exc)],
                }

            if evidence_result.get("evidence"):
                first_evidence = evidence_result["evidence"][0]
                cube_query = first_evidence.get("query") or {}
                cube_config = {"cube_query": cube_query, "dynamic_metrics": []}
                cube_data = first_evidence.get("data") or []
                print(f"[{report_id}] Agrupando evidencia principal ({len(cube_data)} filas) y adjuntando packs completos...")
                aggregated_data = aggregate_data(cube_data, cube_config)
                aggregated_data["analytical_packs"] = {
                    "semantic_plan": {
                        "plan_id": (analysis_plan or {}).get("plan_id"),
                        "warnings": evidence_result.get("warnings") or [],
                        "validation_errors": evidence_result.get("validation_errors") or [],
                    },
                    "evidence": evidence_result.get("evidence_digest") or [],
                }
                llm_data = compact_report_data_for_llm(aggregated_data)
                evidence_text = evidence_markdown(evidence_result)
            else:
                print(f"[{report_id}] Generando query semantica fallback basada en catalogo activo...")
                cube_config = await generate_dynamic_cube_config(
                    custom_notes=custom_notes or "",
                    template_config=base_cube_config,
                    assigned_agents=agents_info,
                    metric_catalog=metric_catalog,
                    semantic_catalog=semantic_catalog,
                )

                cube_query = cube_config.get("cube_query", {})
                semantic_response = await execute_semantic_query(
                    {"connection_id": report_connection_id, "query": cube_query},
                    user_id=report_user_id,
                )
                processed_cube_response = {"data": semantic_response.get("data", [])}
                cube_data = processed_cube_response.get("data", [])

                print(f"[{report_id}] Agrupando y masticando {len(cube_data)} filas de datos...")
                aggregated_data = aggregate_data(cube_data, cube_config)
                llm_data = compact_report_data_for_llm(aggregated_data)
            
            # B. Ejecución Individual y Concurrente de los Agentes Asignados
            report_agents = report_data.get("report_agents", [])
            agent_findings = {}
            evidence_ids = evidence_ids_from_result(evidence_result)

            if report_agents:
                async def run_single_agent(agent_data):
                    agent = agent_data.get("agents")
                    if not agent:
                        return None, None
                    agent_id = agent.get("id")
                    agent_name = agent.get("name")
                    agent_prompt = agent.get("system_prompt")
                    agent_desc = agent.get("description", "")

                    print(f"[{report_id}] Ejecutando Agente: {agent_name}...")

                    # Determinar si este agente debe enfocarse en Churn/Clientes
                    agent_category = agent.get("category", "") or ""
                    is_churn_agent = agent_category.lower() == "churn" or "churn" in agent_name.lower() or "retencion" in agent_name.lower()

                    churn_instruction = ""
                    if is_churn_agent:
                        churn_instruction = """
CRITICO - ANALISIS DE CLIENTES / CHURN / RETENCION:
- Usa solamente las dimensiones de cliente que existan en `dimension_time_evolution` o `by_dimension` dentro de los datos provistos.
- Si hay historial por cliente, identifica cambios de comportamiento y clientes en riesgo usando el valor exacto de `dimension_value`.
- Si no hay una dimension de cliente en la consulta, indicalo claramente y no inventes nombres ni actividad transaccional."""
                    agent_system = f"""Eres un agente de inteligencia empresarial experto en Nyro Analytics.
Tu rol es: {agent_name}
Tu especialidad es: {agent_desc}

Contexto de empresa:
{business_context_text}

Instrucciones de tu rol:
{agent_prompt}

Tu tarea es analizar detalladamente los datos analíticos de negocio provistos y las notas de contexto del usuario, y redactar tus HALLAZGOS e INSIGHTS clave desde tu perspectiva profesional.
Comunicate con un tono sumamente corporativo, preciso y profesional. Identifica tendencias, riesgos latentes y oportunidades tácticas de mejora.

CRÍTICO - REGLA DE NO-ALUCINACIÓN Y ANCLAJE ESTRICTO A LOS DATOS (GROUNDING):
- Está TERMINANTEMENTE PROHIBIDO inventar, presuponer o rellenar con información ficticia cualquier dato, métrica, rubro, producto, cliente, período de tiempo o dimensión que NO figure explícitamente en el JSON de datos provistos.
- Si una dimensión, rubro, producto, campo o desglose es nulo, vacío, no tiene datos o no se encuentra en el JSON provisto, DEBES reportarlo explícitamente como 'No disponible', 'Sin datos en la consulta' o simplemente omitir el análisis de esa dimensión en particular. NUNCA inventes nombres de fantasía, categorías o valores de prueba.
- Los datos de entrada provistos son la única y absoluta verdad del negocio.
- Tenes tools conceptuales ya ejecutadas por el orquestador: inspect_catalog, plan_analysis, execute_query, define_metric y verify_claim.
- No escribas un hallazgo cuantitativo si no podes vincularlo a un evidence_id recibido. Cada claim con numeros debe incluir "(evidence_id: ...)".
{churn_instruction}"""

                    agent_user_msg = f"""Datos analíticos del negocio (consolidados):
{json.dumps(llm_data, indent=2)}

Evidence packs ejecutados por el Semantic Planner:
{evidence_text or 'No hay evidence packs disponibles; usar solo el JSON consolidado.'}

Notas de contexto del usuario / Instrucciones:
{custom_notes or 'No se especificaron notas de contexto adicionales.'}



Por favor, analice los datos y devuelva sus hallazgos y sugerencias tácticas clave."""

                    payload = llm_payload({
                        "model": get_report_llm_model(),
                        "messages": [
                            {"role": "system", "content": agent_system},
                            {"role": "user", "content": agent_user_msg}
                        ],
                        "stream": False,
                        "temperature": 0.2,
                        "max_tokens": report_llm_max_tokens(450)
                    })

                    try:
                        async with llm_client(trust_env=False) as agent_client:
                            findings = (await complete_report_llm(
                                agent_client,
                                payload,
                                timeout=report_llm_timeout(180.0)
                            ))[:4000]
                            findings = filter_agent_findings_by_evidence(findings, evidence_ids)
                            try:
                                await sb.rest_post(
                                    "report_agent_runs",
                                    {
                                        "report_id": report_id,
                                        "agent_id": agent_id,
                                        "analysis_run_id": evidence_result.get("analysis_run_id"),
                                        "status": "success",
                                        "tool_trace": [
                                            {"tool": "inspect_catalog", "status": "success"},
                                            {"tool": "plan_analysis", "status": "success"},
                                            {"tool": "execute_query", "status": "success", "evidence_ids": evidence_ids},
                                            {"tool": "verify_claim", "status": "success"},
                                        ],
                                        "evidence_keys": evidence_ids,
                                        "claims": [],
                                    },
                                    prefer="return=minimal",
                                )
                            except Exception as persist_exc:
                                print(f"[{report_id}] No se pudo persistir report_agent_runs para {agent_name}: {persist_exc}")
                            return agent_name, findings
                    except Exception as e:
                        print(f"[!] Error ejecutando agente {agent_name}: {e}")
                        try:
                            await sb.rest_post(
                                "report_agent_runs",
                                {
                                    "report_id": report_id,
                                    "agent_id": agent_id,
                                    "analysis_run_id": evidence_result.get("analysis_run_id"),
                                    "status": "failed",
                                    "tool_trace": [],
                                    "evidence_keys": evidence_ids,
                                    "claims": [],
                                    "error_log": str(e),
                                },
                                prefer="return=minimal",
                            )
                        except Exception:
                            pass
                        return agent_name, f"Error al ejecutar el análisis del agente: {str(e)}"

                tasks = [run_single_agent(ra) for ra in report_agents if ra and ra.get("agents")]
                if tasks:
                    results = await asyncio.gather(*tasks)
                    for agent_name, findings in results:
                        if agent_name:
                            agent_findings[agent_name] = findings

            # Sintetizar los hallazgos de los agentes en el resumen consolidado
            agents_findings_summary = ""
            for agent_name, findings in agent_findings.items():
                agents_findings_summary += f"\n### HALLAZGOS DE {agent_name.upper()}:\n{findings}\n"

            # C. Llamada a Gemini para el Orquestador y Redactor Principal
            base_template_instruction = ""
            if template:
                base_template_instruction = f"Instrucciones de la Plantilla de Informe:\n{system_prompt}"
            
            has_client_data = bool(aggregated_data.get("dimension_time_evolution") or aggregated_data.get("by_dimension"))
            is_churn_report = any(a.get("category") == "churn" for a in agents_info) or (template and "churn" in template.get("name", "").lower())

            client_instruction = ""
            if has_client_data and is_churn_report:
                client_instruction = "\nCRITICO: Si los datos provistos contienen desglose por cliente individual, usalos para listar clientes en riesgo o abandonos identificados por los agentes, utilizando siempre el valor exacto de la dimension disponible. Si no hay desglose de cliente, no inventes nombres."
            # Reports in the thesis edition contain narrative and tables only.
            include_charts = False
            report_scope = build_report_scope(
                agents_info=agents_info,
                custom_notes=custom_notes or "",
                template=template,
                aggregated_data=aggregated_data
            )
            json_structure = build_report_json_structure(include_charts, report_scope["allow_client_detail"])
            if not report_scope["allow_client_detail"]:
                client_instruction = ""

            orchestrator_system_prompt = f"""Sos el Orquestador y Redactor Principal de Informes de Nyro Analytics.{client_instruction}

CONTEXTO DE EMPRESA:
{business_context_text}

CRÍTICO - REGLA DE NO-ALUCINACIÓN Y ANCLAJE ESTRICTO A LOS DATOS (GROUNDING):
- Está TERMINANTEMENTE PROHIBIDO inventar, presuponer o rellenar con información ficticia cualquier dato, métrica, rubro, producto, cliente, período de tiempo o dimensión que NO figure explícitamente en el JSON de datos provistos o en los hallazgos de los agentes expertos.
- Si un agente experto reportó por error alguna categoría, dimensión o nombre inexistente, tu deber como orquestador es filtrarlo y corregirlo.
- Si una dimensión, rubro, producto, campo o desglose es nulo, vacío, no tiene datos o está ausente en el JSON, DEBES reportarlo explícitamente como 'No disponible', 'Sin especificar' o simplemente omitir esa sección, pero NUNCA inventes categorías o datos ficticios para rellenar la plantilla.



CRITICO - EVIDENCIA VERIFICADA:
- El informe final solo puede usar claims cuantitativos que aparezcan en los evidence packs o en hallazgos de agentes con evidence_id.
- Si falta una metrica, dimension o corte de analisis, declaralo como faltante y proponelo; no lo reemplaces por intuicion.
- Para riesgos, oportunidades y acciones, referencia la evidencia que los sustenta dentro del texto cuando sea natural.

CRITICO - ALCANCE EDITORIAL DINAMICO:
- El informe final debe depender de los agentes realmente asignados y de las notas del usuario. No incluyas secciones de finanzas, retencion, oportunidades, riesgos, inventario o clientes si ese dominio no esta en el alcance.
- Alcance resuelto del informe:
{json.dumps(report_scope, indent=2, ensure_ascii=False)}
- Regla especifica sobre clientes: {report_scope["client_rule"]}
- Si una plantilla base pide un bloque que queda fuera del alcance de los agentes asignados, adapta el bloque al dominio permitido u omitelo.

Tu tarea es tomar la data cruda, las instrucciones del usuario y las conclusiones generadas por tu equipo de agentes expertos para redactar el informe final consolidado de negocio.

El informe debe volcarse a la estructura de la plantilla de informe si existe, o seguir un formato corporativo de primer nivel de toma de decisiones.

{base_template_instruction}

Aportes e informes individuales de tu equipo de agentes expertos:
{agents_findings_summary if agent_findings else 'No se asignaron agentes específicos para este informe; realiza un análisis analítico general.'}

Tu informe final DEBE ser un objeto JSON único y válido con exactamente la siguiente estructura:
{json_structure}

IMPORTANTE: DEBES RESPONDER ÚNICA Y ESTRICTAMENTE EN FORMATO JSON VÁLIDO.
No incluyas comentarios, bloques de código markdown ni texto fuera del JSON.
Usá comillas simples (') dentro de los valores de texto para evitar romper el formato JSON."""

            user_content = f"""Datos analíticos del negocio:
{json.dumps(llm_data, indent=2)}

Evidence packs verificados:
{evidence_text or 'No hay evidence packs adicionales.'}

Nombre del Informe: {report_data.get('name')}
Notas de contexto adicionales: {custom_notes or 'No se especificaron notas.'}

Generá el informe consolidado final respetando estrictamente el formato JSON."""

            gemini_payload = llm_payload({
                "model": get_report_llm_model(),
                "messages": [
                    {"role": "system", "content": orchestrator_system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "response_format": {"type": "json_object"},
                "stream": False,
                "temperature": 0.2,
                "max_tokens": max(report_llm_max_tokens(4200), 4200)
            })

            llm_result = await complete_report_llm_result(
                client,
                gemini_payload,
                timeout=report_llm_timeout(180.0)
            )
            llm_raw = llm_result["content"]
            
            # Intentar parsear JSON con reintentos
            try:
                report_content = clean_and_parse_json(llm_raw)
                validate_report_content_complete(report_content, finish_reason=llm_result.get("finish_reason"))
            except (json.JSONDecodeError, ValueError) as parse_err:
                print(f"[{report_id}] Primer intento de parse JSON falló: {parse_err}. Reintentando con corrección...")
                # Reintento: pedirle a Gemini que corrija el JSON roto
                retry_payload = llm_payload({
                    "model": get_report_llm_model(),
                    "messages": [
                        {"role": "system", "content": "Si el JSON recibido ya es valido pero el texto esta incompleto, NO lo copies: reescribi el informe completo, cerrado y conciso usando solo la evidencia del JSON disponible."},
                        {"role": "system", "content": "Sos un corrector de JSON. Recibís un string JSON mal formado y devolvés SOLO el JSON corregido y válido, sin explicaciones ni markdown."},
                        {"role": "user", "content": f"Corregí este JSON para que sea válido:\n\n{llm_raw[:8000]}"}
                    ],
                    "response_format": {"type": "json_object"},
                    "stream": False,
                    "temperature": 0.1,
                    "max_tokens": max(report_llm_max_tokens(5200), 5200)
                })
                retry_result = await complete_report_llm_result(
                    client,
                    retry_payload,
                    timeout=report_llm_timeout(180.0)
                )
                report_content = clean_and_parse_json(retry_result["content"])
                validate_report_content_complete(report_content, finish_reason=retry_result.get("finish_reason"))

            # Eliminar chart_data si include_charts está desactivado
            report_content = enforce_report_scope(report_content, report_scope)

            if not include_charts and isinstance(report_content, dict) and "chart_data" in report_content:
                report_content.pop("chart_data", None)

            # 5. Guardar en BD (SUCCESS)
            await client.patch(
                f"{supabase_url}/rest/v1/reports?id=eq.{report_id}",
                json={"status": "SUCCESS", "content": report_content, "include_charts": False, "updated_at": utc_now_iso()},
                headers=headers
            )
            print(f"[{report_id}] Reporte generado exitosamente.")

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"[{report_id}] Error generando reporte: {error_msg}")
        traceback.print_exc()
        try:
            # 6. Fallback a FAILED en BD
            supabase_url = os.environ.get("SUPABASE_URL")
            if supabase_url:
                headers = get_supabase_headers()
                async with llm_client() as client:
                    if "aggregated_data" in locals() and "report_scope" in locals() and "report_data" in locals():
                        fallback_content = build_deterministic_report_content(
                            aggregated_data=locals().get("aggregated_data") or {},
                            report_scope=locals().get("report_scope") or {},
                            report_name=(locals().get("report_data") or {}).get("name"),
                            custom_notes=locals().get("custom_notes") or "",
                            fallback_reason=error_msg,
                            agent_findings=locals().get("agent_findings") or {},
                        )
                        await client.patch(
                            f"{supabase_url}/rest/v1/reports?id=eq.{report_id}",
                            json={
                                "status": "SUCCESS",
                                "content": fallback_content,
                                "include_charts": False,
                                "error_log": f"Fallback deterministico por error LLM: {error_msg}",
                                "updated_at": utc_now_iso(),
                            },
                            headers=headers
                        )
                    else:
                        await client.patch(
                            f"{supabase_url}/rest/v1/reports?id=eq.{report_id}",
                            json={"status": "FAILED", "error_log": error_msg, "updated_at": utc_now_iso()},
                            headers=headers
                        )
        except Exception as inner_e:
            print(f"[{report_id}] Error fatal al guardar el fallo: {str(inner_e)}")


@router.post("/{report_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_report(report_id: str, background_tasks: BackgroundTasks, authorization: Optional[str] = Header(default=None)):
    """
    Reprocesa un informe existente con el planner semantico actual.
    El worker vuelve a validar usuario, conexion, plantilla y agentes desde Supabase.
    """
    background_tasks.add_task(process_report_async, report_id)
    return {"message": "Report regeneration triggered", "id": report_id}


@router.post("/generate-report", status_code=status.HTTP_202_ACCEPTED)
async def generate_report_webhook(payload: dict, background_tasks: BackgroundTasks):
    """
    Webhook invocado por Supabase cuando se inserta un reporte en estado PENDING.
    Retorna 202 Inmediatamente para que pg_net no de timeout y reintente.
    """
    record = payload.get("record") or {}
    report_id = payload.get("report_id") or record.get("id")
    force = bool(payload.get("force") or payload.get("retry"))
    
    if not report_id:
        return Response(content="Report ID missing", status_code=400)
    
    status_db = record.get("status")
    if not force:
        if status_db and status_db != "PENDING":
            return Response(content="Report is not PENDING", status_code=200)
        try:
            supabase_url = os.environ.get("SUPABASE_URL")
            headers = get_supabase_headers()
            async with llm_client(timeout=30.0) as client:
                res = await client.get(
                    f"{supabase_url}/rest/v1/reports?id=eq.{report_id}&select=status",
                    headers=headers
                )
                res.raise_for_status()
                rows = res.json()
                current_status = rows[0].get("status") if rows else None
            if current_status and current_status != "PENDING":
                return {"message": f"Report is already {current_status}", "id": report_id}
        except Exception as e:
            print(f"[{report_id}] No se pudo validar estado previo antes de encolar: {e}")

    # Encolar la tarea para procesamiento en background
    background_tasks.add_task(process_report_async, report_id)
    
    return {"message": "Report generation triggered", "id": report_id}
