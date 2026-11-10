"""Bound history without silently dropping corrections or explicit scope changes."""

import re
import unicodedata


HISTORY_BUDGET = 48_000
MESSAGE_BUDGET = 6_000
TRUNCATION_MARKER = "\n[Mensaje truncado: se omitió parte del contenido intermedio.]\n"
CORRECTION_PATTERN = re.compile(
    r"\b(?:correccion|corrijo|rectifico|quise decir|me equivoque|en realidad|"
    r"desde ahora|a partir de ahora|olvida|olvidate|no uses|en lugar de|"
    r"reemplaza|reemplazar|sustitui|sustituye)\b"
)


def _normalized_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _bounded_content(content: str) -> str:
    if len(content) <= MESSAGE_BUDGET:
        return content
    available = MESSAGE_BUDGET - len(TRUNCATION_MARKER)
    head = (available + 1) // 2
    tail = available - head
    return content[:head] + TRUNCATION_MARKER + content[-tail:]


def scope_reset_request(prompt: str) -> dict[str, bool] | None:
    """Identify explicit scope edits; a data request may accompany the edit.

    Filters and periods are independent: a global business scope removes entity
    filters, while a temporal reset must be requested separately. Consumers must
    still answer any analytical question accompanying the instruction.
    """
    text = _normalized_text(prompt)
    if re.search(r"\b(?:que significa|que quiere decir|que es|definicion de|como se define)\b", text):
        return None
    action = (r"olvida|olvidate|olvidemos|borra|borrar|quita|quitar|saca|sacar|"
              r"elimina|eliminar|retira|retirar|descarta|descartar|limpia|limpiar|"
              r"reinicia|reiniciar|resetea|resetear|no uses|no tengas en cuenta|"
              r"deja de filtrar|sin filtrar")
    preserve = r"mantene|conserva|respeta|sin cambiar|no (?:borres|quites|olvides|elimines)|salvo|excepto|menos"
    # Bound command objects before a new instruction/question. Entity nouns are
    # deliberately absent: the same grammar applies to any connected domain.
    boundary = (r"pero|quiero|necesito|mostra|mostrame|dame|consulta|calcula|analiza|"
                r"desde ahora|a partir de ahora|" + preserve)
    raw = unicodedata.normalize("NFKD", prompt.lower())
    raw = "".join(char for char in raw if not unicodedata.combining(char))
    clauses = [_normalized_text(clause) for clause in re.split(r"[.,;:!?\n]+", raw)]

    def objects(pattern: str) -> list[str]:
        found = []
        for clause in clauses:
            for match in re.finditer(r"\b(?:" + pattern + r")\b\s+(.+?)(?=\b(?:" + boundary + r")\b|$)", clause):
                found.append(match.group(1).strip())
        return found

    temporal_words = {"periodo", "periodos", "fecha", "fechas", "temporal", "temporales",
                      "tiempo", "mes", "meses", "ano", "anos", "dia", "dias", "semana", "semanas"}
    # These describe measurements/instructions rather than selected entities.
    metric_words = {"metrica", "metricas", "medida", "medidas", "indicador", "indicadores",
                    "kpi", "calculo", "calculos", "formula", "formulas", "promedio", "suma", "conteo"}
    fillers = {"el", "la", "los", "las", "un", "una", "al", "del", "de", "a", "en", "por", "y", "o",
               "solo", "solamente", "unicamente", "exclusivamente", "todo", "toda", "todos", "todas", "anterior", "anteriores",
               "previo", "previa", "previos", "previas", "actual", "actuales", "seleccionado",
               "seleccionada", "seleccionados", "seleccionadas", "elegido", "elegida", "elegidos",
               "elegidas", "mismo", "misma", "favor"}

    def targets(value: str) -> tuple[bool, bool]:
        entity = temporal = False
        for part in re.split(r"\b(?:y|o|ni)\b", value):
            words = [word for word in part.split() if word not in fillers]
            if not words or words[0] in metric_words:
                continue
            # Interpret the object of the command, not entities appearing in its
            # qualifiers: "período del paciente" edits only the period.
            is_temporal = words[0] in temporal_words or (
                words[0] in {"filtro", "filtros", "restriccion", "restricciones", "rango", "intervalo", "corte"}
                and len(words) > 1 and words[1] in temporal_words)
            temporal |= is_temporal
            entity |= not is_temporal
        return entity, temporal

    command_objects = objects(action)
    preserve_objects = objects(preserve)
    command_targets = [targets(value) for value in command_objects]
    preserve_targets = [targets(value) for value in preserve_objects]
    preserve_filters = any(entity for entity, _ in preserve_targets)
    preserve_period = any(temporal for _, temporal in preserve_targets)
    clear_request = bool(re.search(r"\b(?:nuevo chat|nueva conversacion|empeza de nuevo|empezar de nuevo)\b", text))
    for value in command_objects:
        substantive = set(value.split()) - fillers
        clear_request |= bool(substantive.intersection({"contexto", "conversacion", "chat"})
                              or (not substantive and re.search(r"\b(?:todo|toda)\b", value)))
    global_scope = bool(re.search(
        r"\b(?:negocio completo|todo el negocio|negocio en general|empresa completa|toda la empresa)\b", text
    ))
    # "Todos los <objetos>" may expand one field while retaining another
    # entity's filter. Leave that field-specific request to the semantic planner.
    temporal_scope = bool(re.search(
        r"\b(?:sin filtro temporal|sin filtros temporales|sin filtro de fecha|"
        r"sin filtro de periodo|todo el historico|todo el historial|todos los periodos)\b", text
    ))
    reset_filters = (clear_request or global_scope or any(entity for entity, _ in command_targets)) and not preserve_filters
    reset_period = (clear_request or temporal_scope or any(temporal for _, temporal in command_targets)) and not preserve_period
    if not reset_filters and not reset_period:
        return None
    return {"reset_filters": bool(reset_filters), "reset_period": bool(reset_period),
            "clear_all": bool(clear_request and not preserve_period and not preserve_filters)}


def select_conversation_history(history: list[dict]) -> list[dict]:
    messages = [message for message in history if isinstance(message, dict)
                and not message.get("isLoading")
                and (message.get("content") or isinstance(message.get("semantic_context"), dict))
                and not str(message.get("content") or "").startswith("Error:")]
    indices = list(range(len(messages)))
    state_indices = [index for index in indices if isinstance(messages[index].get("semantic_context"), dict)]
    corrections = [index for index in indices if messages[index].get("role") == "user"
                   and CORRECTION_PATTERN.search(_normalized_text(str(messages[index].get("content") or "")))]
    priority = [*state_indices[-1:], *indices[-6:][::-1], *corrections[::-1], *indices[:6],
                *[index for index in indices if messages[index].get("role") == "user"][::-1],
                *indices[::-1]]
    selected = set()
    remaining = HISTORY_BUDGET
    for index in priority:
        size = min(len(str(messages[index].get("content") or "")), MESSAGE_BUDGET)
        if index not in selected and size <= remaining:
            selected.add(index)
            remaining -= size
    return [{**message, "content": _bounded_content(str(message.get("content") or ""))}
            for index, message in enumerate(messages) if index in selected]
