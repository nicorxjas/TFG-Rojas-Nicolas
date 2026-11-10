"""Validate Cube filter trees without changing their Boolean meaning."""

from typing import Any, Callable


FILTER_OPERATORS = {
    "equals", "notEquals", "contains", "notContains", "startsWith", "notStartsWith",
    "endsWith", "notEndsWith", "gt", "gte", "lt", "lte", "set", "notSet",
    "inDateRange", "notInDateRange", "beforeDate", "afterDate",
    "beforeOrOnDate", "afterOrOnDate",
}


def validate_filters(filters: Any, require_member: Callable[[str], None], depth: int = 0) -> None:
    if not isinstance(filters, list) or depth > 10:
        raise ValueError("La estructura de filtros no es valida.")
    for item in filters:
        if not isinstance(item, dict):
            raise ValueError("Cada filtro debe ser un objeto.")
        groups = set(item).intersection({"and", "or"})
        if groups:
            if len(groups) != 1 or len(item) != 1:
                raise ValueError("Un grupo de filtros debe contener solo AND u OR.")
            children = item[next(iter(groups))]
            if not children:
                raise ValueError("Un grupo de filtros no puede estar vacio.")
            validate_filters(children, require_member, depth + 1)
            continue
        member = item.get("member") or item.get("dimension") or item.get("measure")
        if not isinstance(member, str):
            raise ValueError("Falta el campo del filtro.")
        require_member(member)
        operator = item.get("operator")
        if operator not in FILTER_OPERATORS:
            raise ValueError("El operador del filtro no esta soportado.")
        values = item.get("values")
        if operator in {"set", "notSet"}:
            if values not in (None, []):
                raise ValueError("Este filtro no admite valores.")
        elif not isinstance(values, list) or not values or any(
            not isinstance(value, str) for value in values
        ):
            raise ValueError("El filtro requiere una lista de valores de texto.")
        elif operator in {"inDateRange", "notInDateRange"} and len(values) != 2:
            raise ValueError("El filtro temporal requiere inicio y fin.")
