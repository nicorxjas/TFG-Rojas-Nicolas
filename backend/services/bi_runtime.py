"""Same JSON action protocol for Codex, Ollama and compatible chat providers."""
import asyncio
import hashlib
import json
import time
from typing import Callable
from api.llm import (llm_client, llm_payload, get_llm_chat_url, get_llm_headers,
                     get_llm_model, get_llm_provider, get_llm_timeout)
from services.bi_contracts import Plan, CatalogAction, validation_feedback, CONTRACT_VERSION
from services.bi_catalog_tools import CatalogTools
from services.bi_trace import record, trace_run


def provider_capabilities():
    provider = get_llm_provider()
    return {"provider": provider, "model": get_llm_model(), "json_object": True,
            "native_tool_calls_required": False, "reasoning_effort": provider != "ollama",
            "token_streaming": provider != "codex"}


async def complete_json(messages, *, timeout=60, effort="medium"):
    payload = llm_payload({"model": get_llm_model(), "messages": messages,
                           "response_format": {"type": "json_object"}, "stream": False,
                           "temperature": 0, "reasoning_effort": effort, "max_tokens": 8192})
    started = time.monotonic()
    async with llm_client() as client:
        response = await client.post(get_llm_chat_url(), json=payload, headers=get_llm_headers(), timeout=timeout)
        response.raise_for_status()
        body = response.json()
    record("completion", {"provider": get_llm_provider(), "requested_model": get_llm_model(),
                          "returned_model": body.get("model"), "effort": effort,
                          "usage": body.get("usage"), "seconds": time.monotonic()-started})
    content = body["choices"][0]["message"]["content"]
    record("completion_text", content)
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError("Se requiere un objeto JSON.")
    return result


DISCOVERY_INSTRUCTIONS = """
ARNES DE EJECUCION:
Recibis una vista inicial del catalogo, no necesariamente el catalogo completo.
Podes devolver {"action":{"tool":"search_catalog","text":"concepto o sinonimos","kind":"metrics|dimensions|time_dimensions|all","offset":0}},
{"action":{"tool":"get_members","keys":["key exacta"]}} o
{"action":{"tool":"get_relationships","source":"tabla o cubo","offset":0}}.
Estas herramientas solo leen metadatos publicados; nunca ejecutan consultas ni crean metricas.
Busca por definicion y aliases, lee dependencias, unidades, grano y relaciones antes de elegir.
La falta de coincidencia lexical no demuestra que una metrica no existe: proba sinonimos y usa paginacion cuando corresponda.
Cuando puedas resolver, devuelve el objeto del plan directamente, sin action, usando el formato indicado.
Si recibis validation_errors, corrige esos errores sin quitar restricciones del pedido ni reemplazarlo por otra pregunta.
El estado conversacional recibido es alcance anterior, no evidencia de resultados actuales.
"""


async def run_planner(prompt, graph, context, system, validator: Callable, *, complete=complete_json,
                      max_calls=6, max_repairs=2, timeout=None):
    """Bound discovery, semantic repair and wall time. Only validated plans exit."""
    budget = timeout if timeout is not None else get_llm_timeout(90)
    toolbox = CatalogTools(graph)
    state = context.get("conversation_state") or {}
    seed = toolbox.seed(prompt, state)
    request = {"prompt": prompt, "context": context, "catalog": seed}
    messages = [{"role": "system", "content": system + DISCOVERY_INSTRUCTIONS},
                {"role": "user", "content": json.dumps(request, ensure_ascii=False)}]
    start = time.monotonic()
    repairs = 0
    tool_calls = []
    seen = set()
    final = None
    with trace_run("planner", {"prompt": prompt, "context": context}) as trace:
        span_start = len(trace["events"])
        record("configuration", {**provider_capabilities(), "contract": CONTRACT_VERSION,
                                 "prompt_sha256": hashlib.sha256(messages[0]["content"].encode()).hexdigest(),
                                 "system_prompt": messages[0]["content"], "budget_seconds": budget})
        record("catalog_snapshot", {"members": toolbox.groups, "relationships": graph.get("relationships") or [],
                                    "fingerprint": toolbox.fingerprint})
        try:
            async with asyncio.timeout(budget):
                for attempt in range(max_calls):
                    record("model_input", messages)
                    try:
                        raw = await complete(messages, timeout=max(0.1, budget-(time.monotonic()-start)))
                        record("model_output", raw)
                        if "action" in raw:
                            if set(raw) != {"action"}:
                                raise ValueError("No mezclar acciones de descubrimiento y planes.")
                            action = CatalogAction.model_validate(raw["action"]).model_dump(exclude_none=True)
                            signature = json.dumps(action, sort_keys=True)
                            if signature in seen:
                                raise ValueError("La accion ya fue respondida; usa su resultado o cambia la busqueda.")
                            seen.add(signature)
                            result = toolbox.execute(action)
                            tool_calls.append({"action": action, "result": result})
                            record("catalog_tool", tool_calls[-1])
                            messages.extend([{"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)},
                                             {"role": "user", "content": json.dumps({"tool_result": result}, ensure_ascii=False)}])
                            continue
                        plan = Plan.model_validate(raw).model_dump(exclude_none=True)
                        errors = validator(plan)
                        if errors:
                            raise ValueError("; ".join(errors))
                        # Validate against the whole authorized catalog, even
                        # when the initial discovery window omitted this member.
                        missing = plan.get("missing_metric_request")
                        if missing:
                            exact = [item for item in toolbox.groups["metrics"] if any(
                                normalize_identity(missing) == normalize_identity(name)
                                for name in [item["key"], item.get("name", ""), *(item.get("aliases") or [])])]
                            if exact:
                                raise ValueError("La metrica ya esta publicada: " + json.dumps(exact, ensure_ascii=False))
                        final = plan
                        break
                    except (ValueError, KeyError, TypeError) as exc:
                        repairs += 1
                        feedback = validation_feedback(exc)
                        record("validation_errors", feedback)
                        if repairs > max_repairs:
                            break
                        messages.append({"role": "user", "content": json.dumps({"validation_errors": feedback}, ensure_ascii=False)})
        except Exception as exc:
            record("provider_error", {"type": type(exc).__name__})
        if final is None:
            final = {"queries": [], "clarification": "No pude validar una consulta completa. Indicame la métrica y el alcance que querés analizar.",
                     "warnings": ["Se agotó el presupuesto de descubrimiento o corrección del arnés."]}
        final["harness"] = {"version": CONTRACT_VERSION, "trace_id": trace["trace_id"],
                            "span_start_event": span_start,
                            "catalog_fingerprint": toolbox.fingerprint, "capabilities": provider_capabilities(),
                            "tool_calls": len(tool_calls), "repairs": repairs,
                            "duration_ms": round((time.monotonic()-start)*1000)}
        record("validated_plan", final)
        return final


def normalize_identity(value):
    from services.semantic_graph import normalize_text
    return normalize_text(value)
