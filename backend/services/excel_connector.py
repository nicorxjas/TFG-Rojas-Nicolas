import csv
import json
import posixpath
import re
import shutil
import tempfile
import zipfile
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

from fastapi import HTTPException
import httpx

try:
    import duckdb
    DUCKDB_IMPORT_ERROR: Optional[BaseException] = None
except ImportError as exc:  # pragma: no cover - exercised only in deployments without optional dependency.
    duckdb = None
    DUCKDB_IMPORT_ERROR = exc

from api.llm import llm_client, get_llm_timeout, get_llm_chat_url, get_llm_headers, get_llm_model, llm_is_configured, llm_payload
from services import supabase_rest as sb
from services.company_context import company_context_prompt, require_company_context
from services.semantic_catalog import (
    clear_semantic_catalog_cache,
    create_sync_run,
    finish_sync_run,
    infer_field_kind,
    is_sensitive_field,
    list_connections,
    normalize_alias,
    persist_catalog,
    utc_now_iso,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
EXCEL_DATA_DIR = DATA_DIR / "excel"
CUBE_MODEL_DIR = ROOT_DIR / "cube" / "model"
MAX_EXCEL_UPLOAD_BYTES = 25 * 1024 * 1024
REUSABLE_EXCEL_STATUSES = {"draft", "syncing", "review", "ready", "connected", "error"}
XLSX_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RELS_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
BUILTIN_EXCEL_DATE_FORMATS = {
    14,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    27,
    28,
    29,
    30,
    31,
    32,
    33,
    34,
    35,
    36,
    45,
    46,
    47,
    50,
    51,
    52,
    53,
    54,
    55,
    56,
    57,
    58,
}


def _safe_identifier(value: str, fallback: str) -> str:
    normalized = normalize_alias(value)
    if not normalized:
        normalized = normalize_alias(fallback)
    if not normalized:
        normalized = "field"
    if normalized[0].isdigit():
        normalized = f"c_{normalized}"
    return normalized


def _unique(values: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for value in values:
        candidate = value
        if candidate in seen:
            seen[candidate] += 1
            candidate = f"{candidate}_{seen[value]}"
        else:
            seen[candidate] = 1
        result.append(candidate)
    return result


def _excel_serial_to_date(value: int | float) -> str:
    return (date(1899, 12, 30) + timedelta(days=float(value))).isoformat()


def _column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return max(index - 1, 0)


def _load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall("x:si", XLSX_NS):
        parts = [node.text or "" for node in item.findall(".//x:t", XLSX_NS)]
        strings.append("".join(parts))
    return strings


def _load_workbook_relationships(zf: zipfile.ZipFile) -> dict[str, str]:
    if "xl/_rels/workbook.xml.rels" not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rels = {}
    for rel in root.findall("r:Relationship", RELS_NS):
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target", "")
        if not rel_id or not target:
            continue
        if target.startswith("/"):
            rels[rel_id] = target.lstrip("/")
        else:
            rels[rel_id] = posixpath.normpath(posixpath.join("xl", target))
    return rels


def _looks_like_date_format(format_code: str) -> bool:
    cleaned = re.sub(r'"[^"]*"', "", format_code.lower())
    cleaned = re.sub(r"\[[^\]]+\]", "", cleaned)
    return any(token in cleaned for token in ("yy", "dd", "mm/", "/mm", "m/d", "d/m"))


def _load_date_style_ids(zf: zipfile.ZipFile) -> set[str]:
    if "xl/styles.xml" not in zf.namelist():
        return set()
    root = ET.fromstring(zf.read("xl/styles.xml"))
    custom_date_numfmts = set()
    for num_fmt in root.findall(".//x:numFmt", XLSX_NS):
        num_fmt_id = num_fmt.attrib.get("numFmtId")
        format_code = num_fmt.attrib.get("formatCode", "")
        if num_fmt_id and _looks_like_date_format(format_code):
            custom_date_numfmts.add(num_fmt_id)

    date_style_ids = set()
    cell_formats = root.find("x:cellXfs", XLSX_NS)
    if cell_formats is None:
        return date_style_ids
    for idx, xf in enumerate(cell_formats.findall("x:xf", XLSX_NS)):
        num_fmt_id = xf.attrib.get("numFmtId")
        if not num_fmt_id:
            continue
        try:
            builtin_date = int(num_fmt_id) in BUILTIN_EXCEL_DATE_FORMATS
        except ValueError:
            builtin_date = False
        if builtin_date or num_fmt_id in custom_date_numfmts:
            date_style_ids.add(str(idx))
    return date_style_ids


def _cell_value(cell: ET.Element, shared_strings: list[str], date_style_ids: set[str]) -> Any:
    value_node = cell.find("x:v", XLSX_NS)
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        parts = [node.text or "" for node in cell.findall(".//x:t", XLSX_NS)]
        return "".join(parts)
    if value_node is None or value_node.text is None:
        return None
    raw = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except Exception:
            return raw
    if cell_type == "b":
        return raw == "1"
    if cell_type == "e":
        return None
    try:
        numeric = float(raw)
        if cell.attrib.get("s") in date_style_ids:
            return _excel_serial_to_date(numeric)
        return int(numeric) if numeric.is_integer() else numeric
    except ValueError:
        return raw


def _parse_number_text(text: str) -> Any:
    normalized = text.strip()
    if not normalized:
        return text
    if re.match(r"^0\d+", normalized):
        return text
    if not re.match(r"^-?[\d.,]+%?$", normalized):
        return text
    is_percent = normalized.endswith("%")
    normalized = normalized.rstrip("%")
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        normalized = normalized.replace(",", ".")
    try:
        value = float(normalized)
    except ValueError:
        return text
    if is_percent:
        value = value / 100
    return int(value) if value.is_integer() else value


def _coerce_for_header(header: str, value: Any) -> Any:
    if value is None or value == "":
        return None
    normalized = normalize_alias(header)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if any(token in normalized for token in ("fecha", "date", "periodo")):
            return _excel_serial_to_date(value)
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if any(token in normalized for token in ("fecha", "date", "periodo")):
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(text[:10], fmt).date().isoformat()
                except ValueError:
                    continue
        if not any(token in normalized for token in ("id", "codigo", "cod", "sku", "zip", "postal")):
            return _parse_number_text(text)
        return text
    return value


def _infer_data_type(values: list[Any]) -> str:
    non_empty = [value for value in values if value is not None and value != ""]
    if not non_empty:
        return "string"
    if all(isinstance(value, bool) for value in non_empty):
        return "boolean"
    if all(isinstance(value, (date, datetime)) for value in non_empty):
        return "date"
    if all(isinstance(value, int) and not isinstance(value, bool) for value in non_empty):
        return "integer"
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in non_empty):
        return "number"
    if all(isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", value) for value in non_empty):
        return "date"
    return "string"


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _get_duckdb() -> Any:
    global duckdb, DUCKDB_IMPORT_ERROR
    if duckdb is not None:
        return duckdb
    try:
        import importlib

        duckdb = importlib.import_module("duckdb")
        DUCKDB_IMPORT_ERROR = None
        return duckdb
    except ImportError as exc:
        DUCKDB_IMPORT_ERROR = exc
        hint = f" Detalle tecnico: {exc}" if exc else ""
        raise HTTPException(
            status_code=503,
            detail=f"DuckDB no esta instalado en el backend. Agrega `duckdb>=1.4,<2` e intenta nuevamente.{hint}",
        ) from exc


def _profile_column(values: list[Any], data_type: str) -> dict[str, Any]:
    row_count = len(values)
    non_empty = [value for value in values if value is not None and value != ""]
    distinct_seen: set[str] = set()
    samples = []
    for value in non_empty:
        safe_value = _json_safe_value(value)
        key = json.dumps(safe_value, ensure_ascii=False, default=str)
        distinct_seen.add(key)
        if len(samples) < 5 and safe_value not in samples:
            samples.append(safe_value)

    profile: dict[str, Any] = {
        "inferred_type": data_type,
        "row_count": row_count,
        "null_count": row_count - len(non_empty),
        "approx_distinct": len(distinct_seen),
        "samples": samples,
    }

    if non_empty and data_type in {"integer", "number"}:
        numeric_values = [float(value) for value in non_empty if isinstance(value, (int, float)) and not isinstance(value, bool)]
        if numeric_values:
            profile["min"] = min(numeric_values)
            profile["max"] = max(numeric_values)
    elif non_empty and data_type == "date":
        ordered = sorted(str(_json_safe_value(value)) for value in non_empty)
        if ordered:
            profile["min"] = ordered[0]
            profile["max"] = ordered[-1]
    return profile


def _load_workbook_sheet_names(zf: zipfile.ZipFile) -> list[str]:
    relationships = _load_workbook_relationships(zf)
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    sheet_names = []
    names = set(zf.namelist())
    for sheet in workbook.findall(".//x:sheets/x:sheet", XLSX_NS):
        sheet_name = sheet.attrib.get("name") or "Sheet"
        rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        sheet_path = relationships.get(rel_id or "")
        if sheet_path and sheet_path in names:
            sheet_names.append(sheet_name)
    return sheet_names


def _duckdb_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _duckdb_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sheet_sql(file_path: Path, sheet_name: str) -> str:
    return (
        "read_xlsx("
        f"{_duckdb_string(str(file_path))}, "
        f"sheet = {_duckdb_string(sheet_name)}, "
        "header = true, ignore_errors = true, empty_as_varchar = true"
        ")"
    )


def _load_duckdb_excel_extension(connection: Any) -> None:
    try:
        connection.execute("LOAD excel")
        return
    except Exception:
        pass

    try:
        connection.execute("INSTALL excel")
        connection.execute("LOAD excel")
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "No pude activar la extension Excel de DuckDB. "
                "Instala/carga la extension `excel` en el entorno del backend e intenta nuevamente."
            ),
        ) from exc


def _column_clean_expr(column_name: str) -> str:
    return f"NULLIF(TRIM(CAST({_duckdb_identifier(column_name)} AS VARCHAR)), '')"


def _column_number_expr(clean_expr: str) -> str:
    stripped_percent_expr = f"REPLACE({clean_expr}, '%', '')"
    parsed_expr = (
        "COALESCE("
        f"TRY_CAST({stripped_percent_expr} AS DOUBLE), "
        f"TRY_CAST(REPLACE({stripped_percent_expr}, ',', '.') AS DOUBLE), "
        f"TRY_CAST(REPLACE(REPLACE({stripped_percent_expr}, '.', ''), ',', '.') AS DOUBLE)"
        ")"
    )
    return (
        "(CASE "
        f"WHEN RIGHT({clean_expr}, 1) = '%' THEN ({parsed_expr}) / 100 "
        f"ELSE {parsed_expr} "
        "END)"
    )


def _column_export_expr(column: dict[str, Any]) -> str:
    column_name = str(column["name"])
    alias = _duckdb_identifier(column_name)
    clean_expr = _column_clean_expr(column_name)
    data_type = str(column.get("data_type") or "")
    if data_type in {"integer", "number"}:
        return f"{_column_number_expr(clean_expr)} AS {alias}"
    if data_type == "date":
        return f"TRY_CAST({clean_expr} AS DATE) AS {alias}"
    return f"{clean_expr} AS {alias}"


def _profile_column_with_duckdb(
    connection: Any,
    temp_table: str,
    field_name: str,
    display_header: str,
) -> dict[str, Any]:
    table_ref = _duckdb_identifier(temp_table)
    clean_expr = _column_clean_expr(field_name)
    number_expr = _column_number_expr(clean_expr)
    date_expr = f"TRY_CAST({clean_expr} AS DATE)"
    stats = connection.execute(
        f"""
        SELECT
          COUNT(*)::BIGINT AS row_count,
          COUNT({clean_expr})::BIGINT AS non_empty_count,
          COUNT(DISTINCT {clean_expr})::BIGINT AS approx_distinct,
          SUM(CASE WHEN {number_expr} IS NOT NULL THEN 1 ELSE 0 END)::BIGINT AS numeric_count,
          SUM(CASE WHEN {date_expr} IS NOT NULL THEN 1 ELSE 0 END)::BIGINT AS date_count
        FROM {table_ref}
        """
    ).fetchone()
    row_count = int(stats[0] or 0)
    non_empty_count = int(stats[1] or 0)
    approx_distinct = int(stats[2] or 0)
    numeric_count = int(stats[3] or 0)
    date_count = int(stats[4] or 0)
    normalized_header = normalize_alias(display_header)
    id_like = any(token in normalized_header for token in ("id", "codigo", "cod", "sku", "zip", "postal"))
    date_like = any(token in normalized_header for token in ("fecha", "date", "periodo"))

    if non_empty_count == 0:
        data_type = "string"
    elif date_like and date_count >= max(1, int(non_empty_count * 0.8)):
        data_type = "date"
    elif not id_like and numeric_count == non_empty_count:
        integer_count = connection.execute(
            f"""
            SELECT
              SUM(
                CASE
                  WHEN {number_expr} IS NOT NULL AND {number_expr} = FLOOR({number_expr}) THEN 1
                  ELSE 0
                END
              )::BIGINT
            FROM {table_ref}
            """
        ).fetchone()[0]
        data_type = "integer" if int(integer_count or 0) == non_empty_count else "number"
    else:
        data_type = "string"

    sample_rows = connection.execute(
        f"""
        SELECT {clean_expr}
        FROM {table_ref}
        WHERE {clean_expr} IS NOT NULL
        GROUP BY {clean_expr}
        LIMIT 5
        """
    ).fetchall()
    samples = [_json_safe_value(row[0]) for row in sample_rows]

    profile: dict[str, Any] = {
        "inferred_type": data_type,
        "row_count": row_count,
        "null_count": row_count - non_empty_count,
        "approx_distinct": approx_distinct,
        "samples": samples,
    }

    if non_empty_count and data_type in {"integer", "number"}:
        min_value, max_value = connection.execute(
            f"SELECT MIN({number_expr}), MAX({number_expr}) FROM {table_ref}"
        ).fetchone()
        profile["min"] = _json_safe_value(min_value)
        profile["max"] = _json_safe_value(max_value)
    elif non_empty_count and data_type == "date":
        min_value, max_value = connection.execute(
            f"SELECT MIN({date_expr}), MAX({date_expr}) FROM {table_ref}"
        ).fetchone()
        profile["min"] = _json_safe_value(min_value)
        profile["max"] = _json_safe_value(max_value)
    return profile


def _read_sheet_with_duckdb(
    connection: Any,
    file_path: Path,
    sheet_name: str,
    csv_path: Path,
    table_index: int,
) -> Optional[dict[str, Any]]:
    sql = f"SELECT * FROM {_sheet_sql(file_path, sheet_name)} LIMIT 0"
    try:
        cursor = connection.execute(sql)
        description = cursor.description or []
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"No pude leer la hoja `{sheet_name}` con DuckDB: {exc}",
        ) from exc

    if not description:
        return None

    display_headers = [str(col[0] or "").strip() or f"Column {idx + 1}" for idx, col in enumerate(description)]
    field_names = _unique([_safe_identifier(value, f"column_{idx + 1}") for idx, value in enumerate(display_headers)])
    select_exprs = [
        f"{_duckdb_identifier(display_headers[idx])} AS {_duckdb_identifier(field_name)}"
        for idx, field_name in enumerate(field_names)
    ]
    source_sql = f"SELECT {', '.join(select_exprs)} FROM {_sheet_sql(file_path, sheet_name)}"
    temp_table = f"excel_sheet_{table_index}_{_safe_identifier(sheet_name, 'sheet')}"
    table_ref = _duckdb_identifier(temp_table)
    non_empty_predicate = " OR ".join(f"{_column_clean_expr(field_name)} IS NOT NULL" for field_name in field_names)

    try:
        connection.execute(f"DROP TABLE IF EXISTS {table_ref}")
        connection.execute(
            f"""
            CREATE TEMP TABLE {table_ref} AS
            SELECT *
            FROM ({source_sql}) AS source
            WHERE {non_empty_predicate}
            """
        )
        row_count = int(connection.execute(f"SELECT COUNT(*) FROM {table_ref}").fetchone()[0] or 0)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"No pude preparar la hoja `{sheet_name}` con DuckDB: {exc}",
        ) from exc

    if row_count == 0:
        return None

    columns = []
    for idx, field_name in enumerate(field_names):
        profile = _profile_column_with_duckdb(connection, temp_table, field_name, display_headers[idx])
        columns.append({
            "name": field_name,
            "display_name": display_headers[idx],
            "data_type": profile["inferred_type"],
            "profile": profile,
        })

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    export_exprs = ", ".join(_column_export_expr(column) for column in columns)
    try:
        connection.execute(
            f"COPY (SELECT {export_exprs} FROM {table_ref}) TO {_duckdb_string(str(csv_path))} (HEADER)"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"No pude exportar la hoja `{sheet_name}` para Cube: {exc}",
        ) from exc

    return {
        "sheet_name": sheet_name,
        "table_name": _safe_identifier(sheet_name, "sheet"),
        "columns": columns,
        "row_count": row_count,
        "csv_path": str(csv_path),
    }


def _parse_sheet(
    *,
    zf: zipfile.ZipFile,
    sheet_path: str,
    sheet_name: str,
    shared_strings: list[str],
    date_style_ids: set[str],
) -> Optional[dict[str, Any]]:
    root = ET.fromstring(zf.read(sheet_path))
    rows = []
    for row in root.findall(".//x:sheetData/x:row", XLSX_NS):
        values: dict[int, Any] = {}
        for cell in row.findall("x:c", XLSX_NS):
            cell_ref = cell.attrib.get("r", "")
            col_idx = _column_index(cell_ref)
            values[col_idx] = _cell_value(cell, shared_strings, date_style_ids)
        if values:
            max_idx = max(values)
            rows.append([values.get(idx) for idx in range(max_idx + 1)])

    header_idx = _detect_header_row(rows)
    if header_idx is None:
        return None

    display_headers = [str(value or "").strip() or f"Column {idx + 1}" for idx, value in enumerate(rows[header_idx])]
    field_names = _unique([_safe_identifier(value, f"column_{idx + 1}") for idx, value in enumerate(display_headers)])
    data_rows = []
    for raw_row in rows[header_idx + 1 :]:
        padded = raw_row + [None] * (len(field_names) - len(raw_row))
        values = {
            field_names[idx]: _coerce_for_header(display_headers[idx], padded[idx])
            for idx in range(len(field_names))
        }
        if any(value is not None and value != "" for value in values.values()):
            data_rows.append(values)

    if not data_rows:
        return None

    columns = []
    for idx, field_name in enumerate(field_names):
        column_values = [row.get(field_name) for row in data_rows]
        columns.append({
            "name": field_name,
            "display_name": display_headers[idx],
            "data_type": _infer_data_type(column_values),
        })

    return {
        "sheet_name": sheet_name,
        "table_name": _safe_identifier(sheet_name, "sheet"),
        "columns": columns,
        "rows": data_rows,
    }


def _row_non_empty_count(row: list[Any]) -> int:
    return sum(1 for value in row if str(value or "").strip())


def _detect_header_row(rows: list[list[Any]]) -> Optional[int]:
    candidates = []
    for idx, row in enumerate(rows[:25]):
        non_empty = _row_non_empty_count(row)
        if non_empty == 0:
            continue
        next_non_empty = _row_non_empty_count(rows[idx + 1]) if idx + 1 < len(rows) else 0
        text_like = sum(1 for value in row if isinstance(value, str) and value.strip())
        score = non_empty * 10 + text_like * 3 + min(next_non_empty, non_empty)
        if non_empty >= 2:
            candidates.append((score, -idx, idx))
    if candidates:
        return max(candidates)[2]
    return next((idx for idx, row in enumerate(rows) if _row_non_empty_count(row)), None)


def parse_xlsx_workbook(content: bytes) -> dict[str, Any]:
    duckdb_module = _get_duckdb()

    try:
        zf = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=422, detail="El archivo no es un .xlsx valido") from exc

    names = set(zf.namelist())
    if "xl/workbook.xml" not in names:
        raise HTTPException(status_code=422, detail="El archivo no contiene un workbook Excel valido")

    sheet_names = _load_workbook_sheet_names(zf)
    if not sheet_names:
        raise HTTPException(status_code=422, detail="El archivo no contiene hojas legibles")

    temp_dir = tempfile.mkdtemp(prefix="nyro_excel_")
    temp_path = Path(temp_dir)
    temp_name = temp_path / "workbook.xlsx"
    tables = []
    try:
        with temp_name.open("wb") as tmp:
            tmp.write(content)

        connection = duckdb_module.connect(database=":memory:")
        try:
            _load_duckdb_excel_extension(connection)
            csv_dir = temp_path / "csv"
            for idx, sheet_name in enumerate(sheet_names):
                parsed = _read_sheet_with_duckdb(
                    connection,
                    temp_name,
                    sheet_name,
                    csv_dir / f"{_safe_identifier(sheet_name, f'sheet_{idx + 1}')}.csv",
                    idx,
                )
                if parsed:
                    tables.append(parsed)
        finally:
            connection.close()
    except Exception:
        shutil.rmtree(temp_path, ignore_errors=True)
        raise

    if not tables:
        shutil.rmtree(temp_path, ignore_errors=True)
        raise HTTPException(status_code=422, detail="No encontre hojas con datos tabulares en el workbook")

    return {"tables": tables, "engine": "duckdb", "profiled_with": "duckdb_excel", "temp_dir": temp_dir}


def _cube_name(connection_id: str, table_name: str) -> str:
    suffix = re.sub(r"[^a-zA-Z0-9]", "", connection_id)[:8] or "Workbook"
    pascal = "".join(part.capitalize() for part in table_name.split("_") if part)
    return f"Excel{suffix}{pascal or 'Sheet'}"


def _is_fact_table(table_name: str, sheet_name: str) -> bool:
    text = f"{table_name} {sheet_name}".lower()
    return text.startswith("fact") or " fact" in text


def _is_dim_table(table_name: str, sheet_name: str) -> bool:
    text = f"{table_name} {sheet_name}".lower()
    return text.startswith("dim") or " dim" in text


def _field_kind(table: dict[str, Any], column: dict[str, Any]) -> str:
    inferred = infer_field_kind(column["name"], column.get("data_type"))
    if inferred in {"time", "id"}:
        return inferred
    if (
        _is_fact_table(table["table_name"], table["sheet_name"])
        and column.get("data_type") in {"integer", "number"}
    ):
        return "measure"
    return inferred


def _strip_technical_prefix(value: str) -> str:
    text = str(value or "").strip()
    return re.sub(r"^(fact|facts|dim|dims|dimension|dimensions)[\s_\-.]+", "", text, flags=re.I).strip() or text


def _humanize_label(value: str) -> str:
    text = _strip_technical_prefix(value)
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    text = re.sub(r"[_\-.]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return value or "Campo"
    return " ".join(part[:1].upper() + part[1:] for part in text.split(" "))


def _is_technical_excel_field(column: dict[str, Any], kind: str) -> bool:
    normalized = normalize_alias(f"{column.get('name', '')} {column.get('display_name', '')}")
    tokens = set(normalized.split("_"))
    if kind == "id":
        return True
    if tokens.intersection({"id", "codigo", "cod", "clave", "llave", "key", "pk", "fk", "hash"}):
        return True
    if any(
        normalized.startswith(prefix) and len(normalized) > len(prefix) + 1
        for prefix in ("id", "codigo", "cod", "clave", "key")
    ):
        return True
    if normalized in {
        "row_number",
        "numero_fila",
        "load_date",
        "fecha_carga",
        "created_at",
        "updated_at",
        "deleted_at",
        "hash",
        "record_hash",
        "source_file",
        "file_name",
    }:
        return True
    if tokens.intersection({"etl", "audit", "auditoria", "surrogate", "technical"}):
        return True
    return normalized.endswith("_key") or normalized.endswith("_hash")


def _field_suggestion_description(table_label: str, field_label: str, kind: str, data_type: str) -> str:
    if kind == "measure":
        return f"Valor numerico agregado de {field_label.lower()} para analizar {table_label.lower()}."
    if kind == "time":
        return f"Fecha o periodo asociado a {table_label.lower()}."
    if kind == "id":
        return f"Identificador tecnico usado para relacionar {table_label.lower()}."
    if data_type in {"integer", "number"}:
        return f"Atributo numerico de {table_label.lower()}."
    return f"Atributo descriptivo de {table_label.lower()}."


def _table_entity_tokens(table: dict[str, Any]) -> set[str]:
    text = normalize_alias(f"{table.get('table_name', '')} {table.get('sheet_name', '')}")
    tokens = {
        token
        for token in text.split("_")
        if token and token not in {"dim", "fact", "mensual", "monthly", "detalle", "maestro"}
    }
    return tokens


def _dimension_key_columns(table: dict[str, Any]) -> list[str]:
    id_columns = [
        column
        for column in table.get("columns", [])
        if infer_field_kind(column["name"], column.get("data_type")) == "id"
    ]
    entity_tokens = _table_entity_tokens(table)
    matching_ids = [
        column
        for column in id_columns
        if any(token in normalize_alias(column["name"]) for token in entity_tokens)
    ]
    if matching_ids:
        return [matching_ids[0]["name"]]
    if len(id_columns) == 1:
        return [id_columns[0]["name"]]

    time_columns = [
        column
        for column in table.get("columns", [])
        if infer_field_kind(column["name"], column.get("data_type")) == "time"
    ]
    if len(time_columns) == 1 and _table_entity_tokens(table).intersection({"fecha", "date", "periodo"}):
        return [time_columns[0]["name"]]

    return []


def _relationship_key(source_table: str, source_field: str, target_table: str, target_field: str) -> tuple[str, str, str, str]:
    return (source_table, source_field, target_table, target_field)


def _infer_workbook_relationships(workbook: dict[str, Any]) -> list[dict[str, Any]]:
    relationships = []
    seen: set[tuple[str, str, str, str]] = set()
    dimensions = [table for table in workbook["tables"] if _is_dim_table(table["table_name"], table["sheet_name"])]

    for source in workbook["tables"]:
        source_columns = {column["name"] for column in source.get("columns", [])}
        for target in dimensions:
            if source is target:
                continue
            for target_key in _dimension_key_columns(target):
                if target_key not in source_columns:
                    continue
                rel_key = _relationship_key(source["cube_name"], target_key, target["cube_name"], target_key)
                if rel_key in seen:
                    continue
                seen.add(rel_key)
                relationships.append({
                    "from_table": source["cube_name"],
                    "from_field": target_key,
                    "to_table": target["cube_name"],
                    "to_field": target_key,
                    "cardinality": "many_to_one",
                    "cross_filter_behavior": "single",
                    "is_active": True,
                    "metadata": {
                        "source": "excel",
                        "provider": "cube",
                        "sheet_relationship": f"{source['sheet_name']}->{target['sheet_name']}",
                        "inferred_from": "shared_dimension_key",
                    },
                })
                break

    return relationships


def _cube_primary_key_columns(table: dict[str, Any]) -> set[str]:
    if _is_dim_table(table["table_name"], table["sheet_name"]):
        return set(_dimension_key_columns(table))
    return set()


def _build_catalog(connection_id: str, file_name: str, workbook: dict[str, Any]) -> dict[str, Any]:
    tables = []
    fields = []

    for table in workbook["tables"]:
        cube_name = _cube_name(connection_id, table["table_name"])
        table["cube_name"] = cube_name
        table_business_name = _humanize_label(table["sheet_name"])
        tables.append({
            "external_table_id": table["sheet_name"],
            "name": cube_name,
            "display_name": table_business_name,
            "description": "",
            "business_name": table_business_name,
            "suggested_business_name": table_business_name,
            "suggested_description": f"Entidad de negocio importada desde la hoja {table['sheet_name']}.",
            "approval_status": "review",
            "is_hidden": False,
            "metadata": {
                "source": "excel",
                "provider": "cube",
                "sheet_name": table["sheet_name"],
                "table_name": table["table_name"],
                "row_count": table.get("row_count", 0),
                "cube_name": cube_name,
            },
        })
        count_display = "Filas"
        normalized_table_name = normalize_alias(f"{table['sheet_name']} {table['table_name']}")
        if "producto" in normalized_table_name:
            count_display = "Cantidad de productos"
        elif "cliente" in normalized_table_name:
            count_display = "Cantidad de clientes"
        elif "proveedor" in normalized_table_name:
            count_display = "Cantidad de proveedores"
        fields.append({
            "table_name": cube_name,
            "external_field_id": "count",
            "semantic_key": f"{cube_name}.count",
            "name": "count",
            "display_name": count_display,
            "description": "",
            "business_name": count_display,
            "suggested_business_name": count_display,
            "suggested_description": f"Conteo de registros en {table_business_name}.",
            "approval_status": "review",
            "field_kind": "measure",
            "data_type": "number",
            "expression": None,
            "expression_language": None,
            "format_string": None,
            "is_hidden": False,
            "is_sensitive": False,
            "is_ai_enabled": True,
            "metadata": {
                "source": "excel",
                "provider": "cube",
                "sheet_name": table["sheet_name"],
                "cube_name": cube_name,
                "cube_member": "count",
                "physical_column": None,
                "aggregation": "count",
                "generated": True,
            },
        })

        for column in table["columns"]:
            kind = _field_kind(table, column)
            sensitive = is_sensitive_field(column["display_name"]) or is_sensitive_field(column["name"])
            technical = _is_technical_excel_field(column, kind)
            hidden = sensitive or technical
            field_business_name = _humanize_label(column["display_name"] or column["name"])
            suggested_description = _field_suggestion_description(
                table_business_name,
                field_business_name,
                kind,
                column["data_type"],
            )
            metadata = {
                "source": "excel",
                "provider": "cube",
                "sheet_name": table["sheet_name"],
                "cube_name": cube_name,
                "cube_member": column["name"],
                "physical_column": column["name"],
                "physical_display_name": column["display_name"],
                "profile": column.get("profile") or {},
            }
            if kind == "measure":
                metadata["aggregation"] = "sum"
            fields.append({
                "table_name": cube_name,
                "external_field_id": column["name"],
                "semantic_key": f"{cube_name}.{column['name']}",
                "name": column["name"],
                "display_name": field_business_name,
                "description": "",
                "business_name": field_business_name,
                "suggested_business_name": field_business_name,
                "suggested_description": suggested_description,
                "approval_status": "approved" if hidden else "review",
                "field_kind": kind,
                "data_type": column["data_type"],
                "expression": None,
                "expression_language": None,
                "format_string": None,
                "is_hidden": hidden,
                "is_sensitive": sensitive,
                "is_ai_enabled": not hidden,
                "metadata": metadata,
            })

    relationships = _infer_workbook_relationships(workbook)

    return {
        "model": {
            "external_model_id": connection_id,
            "workspace_id": "excel",
            "dataset_id": connection_id,
            "name": file_name,
            "description": "",
            "metadata": {
                "source": "excel",
                "provider": "cube",
                "sheets": [table["sheet_name"] for table in workbook["tables"]],
            },
        },
        "tables": tables,
        "fields": fields,
        "relationships": relationships,
    }


def _suggestion_payload_for_llm(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    tables_by_name = {table.get("name"): table for table in normalized.get("tables", [])}
    payload = []
    for field in normalized.get("fields", []):
        if field.get("is_hidden") or field.get("is_ai_enabled") is False:
            continue
        if len(payload) >= 120:
            break
        table = tables_by_name.get(field.get("table_name") or "")
        profile = ((field.get("metadata") or {}).get("profile") or {})
        payload.append({
            "semantic_key": field.get("semantic_key"),
            "physical_name": field.get("name"),
            "detected_label": field.get("display_name"),
            "suggested_business_name": field.get("suggested_business_name"),
            "table": (table or {}).get("suggested_business_name") or (table or {}).get("display_name"),
            "field_kind": field.get("field_kind"),
            "data_type": field.get("data_type"),
            "profile": {
                "inferred_type": profile.get("inferred_type"),
                "null_count": profile.get("null_count"),
                "approx_distinct": profile.get("approx_distinct"),
                "min": profile.get("min"),
                "max": profile.get("max"),
                "samples": profile.get("samples", [])[:5],
            },
        })
    return payload


async def _apply_ai_field_suggestions(normalized: dict[str, Any], company_context: dict[str, Any]) -> None:
    fields_for_llm = _suggestion_payload_for_llm(normalized)
    if not fields_for_llm or not llm_is_configured():
        return

    payload = llm_payload({
        "model": get_llm_model(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "Sos el asistente de onboarding semantico de Nyro BI AI. "
                    "Generas nombres comerciales y descripciones breves para campos detectados en un Excel. "
                    "Usa estrictamente el contexto de empresa y el perfil estadistico recibido. "
                    "No inventes procesos, productos, clientes ni metricas que no se infieran de nombres, muestras o contexto. "
                    "Responde solo JSON valido con la forma {\"fields\":[{\"semantic_key\":\"...\",\"business_name\":\"...\",\"description\":\"...\"}]}."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Contexto de empresa obligatorio:\n{company_context_prompt(company_context)}\n\n"
                    f"Campos detectados:\n{json.dumps(fields_for_llm, ensure_ascii=False, default=str)}\n\n"
                    "Las descripciones deben tener una frase corta de negocio, apta para C-Level."
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "stream": False,
        "temperature": 0.2,
    })

    try:
        async with llm_client(trust_env=False) as client:
            resp = await client.post(
                get_llm_chat_url(),
                json=payload,
                headers=get_llm_headers(),
                timeout=get_llm_timeout(45.0),
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            suggestion_json = json.loads(content)
    except Exception as exc:
        print(f"[excel onboarding] No se pudieron generar sugerencias IA: {exc}")
        return

    suggestions = suggestion_json.get("fields") if isinstance(suggestion_json, dict) else None
    if not isinstance(suggestions, list):
        return

    by_key = {
        str(item.get("semantic_key")): item
        for item in suggestions
        if isinstance(item, dict) and item.get("semantic_key")
    }
    for field in normalized.get("fields", []):
        suggestion = by_key.get(field.get("semantic_key"))
        if not suggestion:
            continue
        business_name = str(suggestion.get("business_name") or "").strip()
        description = str(suggestion.get("description") or "").strip()
        if business_name:
            field["suggested_business_name"] = business_name[:120]
        if description:
            field["suggested_description"] = description[:500]


def _js_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def _cube_dimension_type(data_type: str, kind: str) -> str:
    if kind == "time" or data_type == "date":
        return "time"
    if data_type in {"integer", "number"}:
        return "number"
    return "string"


def _supports_numeric_field_aggregates(table: dict[str, Any], column: dict[str, Any], kind: str) -> bool:
    if kind in {"measure", "id", "time"}:
        return False
    if column.get("data_type") not in {"integer", "number"}:
        return False
    if _table_entity_tokens(table).intersection({"fecha", "date", "periodo", "calendario", "calendar"}):
        return False
    return True


def _generate_cube_model(connection_id: str, workbook: dict[str, Any], relationships: list[dict[str, Any]]) -> str:
    rels_by_from: dict[str, list[dict[str, Any]]] = {}
    for rel in relationships:
        rels_by_from.setdefault(rel["from_table"], []).append(rel)

    parts = [
        "// Generated by Nyro Excel connector. Do not edit manually.",
        "",
    ]
    for table in workbook["tables"]:
        cube_name = table["cube_name"]
        csv_path = f"/data/excel/{connection_id}/{table['table_name']}.csv"
        joins = rels_by_from.get(cube_name, [])
        primary_key_columns = _cube_primary_key_columns(table)
        needs_generated_primary_key = bool(joins) and not primary_key_columns
        parts.append(f"cube(`{cube_name}`, {{")
        select_clause = "ROW_NUMBER() OVER () AS __nyro_row_id, *" if needs_generated_primary_key else "*"
        parts.append(
            f"  sql: `SELECT {select_clause} FROM read_csv_auto('{_js_string(csv_path)}', header=true)`,"
        )
        parts.append("")
        if joins:
            parts.append("  joins: {")
            for rel in joins:
                parts.append(f"    {rel['to_table']}: {{")
                parts.append(
                    f"      sql: `${{CUBE}}.{rel['from_field']} = ${{{rel['to_table']}}}.{rel['to_field']}`,"
                )
                parts.append("      relationship: `belongsTo`")
                parts.append("    },")
            parts.append("  },")
            parts.append("")
        parts.append("  measures: {")
        parts.append("    count: {")
        parts.append("      type: `count`,")
        parts.append("      title: `Filas`")
        parts.append("    },")
        for column in table["columns"]:
            kind = _field_kind(table, column)
            if kind == "measure":
                parts.append(f"    {column['name']}: {{")
                parts.append(f"      sql: `{column['name']}`,")
                parts.append("      type: `sum`,")
                parts.append(f"      title: `{_js_string(column['display_name'])}`")
                parts.append("    },")
            elif kind == "time":
                for operation, title_prefix in (("min", "Primera"), ("max", "Ultima")):
                    parts.append(f"    {column['name']}_{operation}: {{")
                    parts.append(f"      sql: `{column['name']}`,")
                    parts.append(f"      type: `{operation}`,")
                    parts.append(f"      title: `{title_prefix} {_js_string(column['display_name'])}`")
                    parts.append("    },")
            elif kind == "id":
                parts.append(f"    {column['name']}_count_distinct: {{")
                parts.append(f"      sql: `{column['name']}`,")
                parts.append("      type: `countDistinct`,")
                parts.append(f"      title: `Cantidad unica de {_js_string(column['display_name'])}`")
                parts.append("    },")
            elif _supports_numeric_field_aggregates(table, column, kind):
                for operation, title_prefix in (("sum", "Suma"), ("avg", "Promedio")):
                    parts.append(f"    {column['name']}_{operation}: {{")
                    parts.append(f"      sql: `{column['name']}`,")
                    parts.append(f"      type: `{operation}`,")
                    parts.append(f"      title: `{title_prefix} {_js_string(column['display_name'])}`")
                    parts.append("    },")
        parts.append("  },")
        parts.append("")
        parts.append("  dimensions: {")
        if needs_generated_primary_key:
            parts.append("    __nyro_row_id: {")
            parts.append("      sql: `__nyro_row_id`,")
            parts.append("      type: `number`,")
            parts.append("      primaryKey: true,")
            parts.append("      title: `Nyro Row ID`")
            parts.append("    },")
        for column in table["columns"]:
            kind = _field_kind(table, column)
            if kind == "measure":
                continue
            parts.append(f"    {column['name']}: {{")
            parts.append(f"      sql: `{column['name']}`,")
            parts.append(f"      type: `{_cube_dimension_type(column['data_type'], kind)}`,")
            if column["name"] in primary_key_columns:
                parts.append("      primaryKey: true,")
            parts.append(f"      title: `{_js_string(column['display_name'])}`")
            parts.append("    },")
        parts.append("  }")
        parts.append("});")
        parts.append("")
    return "\n".join(parts)


def _excel_model_path(connection_id: str) -> Path:
    return CUBE_MODEL_DIR / f"Excel_{connection_id.replace('-', '')[:12]}.js"


def _remove_excel_artifacts(connection_id: str) -> None:
    target_dir = EXCEL_DATA_DIR / connection_id
    if target_dir.exists() and target_dir.is_dir():
        shutil.rmtree(target_dir)

    model_path = _excel_model_path(connection_id)
    if model_path.exists():
        model_path.unlink()


def _write_excel_artifacts(connection_id: str, workbook: dict[str, Any], relationships: list[dict[str, Any]]) -> None:
    target_dir = EXCEL_DATA_DIR / connection_id
    target_dir.mkdir(parents=True, exist_ok=True)
    for old_csv in target_dir.glob("*.csv"):
        old_csv.unlink()

    for table in workbook["tables"]:
        csv_path = target_dir / f"{table['table_name']}.csv"
        source_csv_path = Path(str(table.get("csv_path") or ""))
        if not source_csv_path.is_file():
            raise HTTPException(
                status_code=500,
                detail=f"No encontre el CSV temporal para la hoja `{table['sheet_name']}`.",
            )
        shutil.copyfile(source_csv_path, csv_path)

    CUBE_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = _excel_model_path(connection_id)
    model_path.write_text(_generate_cube_model(connection_id, workbook, relationships), encoding="utf-8")


async def _active_excel_connection(user_id: str) -> Optional[dict[str, Any]]:
    connections = [
        connection
        for connection in await list_connections(user_id)
        if connection.get("connector_key") == "excel"
        and connection.get("status") in REUSABLE_EXCEL_STATUSES
    ]
    return next((connection for connection in connections if connection.get("is_default")), connections[0] if connections else None)


async def _disable_stale_excel_connections(user_id: str, active_connection_id: str) -> None:
    connections = [
        connection
        for connection in await list_connections(user_id)
        if connection.get("connector_key") == "excel"
        and connection.get("id") != active_connection_id
        and connection.get("status") != "disabled"
    ]
    if not connections:
        return

    await sb.rest_patch(
        "connector_instances",
        {
            "is_default": False,
            "status": "disabled",
            "health": {
                "metadata": "disabled",
                "reason": "superseded_by_excel_reprocess",
                "active_connection_id": active_connection_id,
            },
        },
        params={
            "owner_user_id": f"eq.{user_id}",
            "connector_key": "eq.excel",
            "id": f"neq.{active_connection_id}",
        },
        prefer="",
    )
    for connection in connections:
        _remove_excel_artifacts(connection["id"])


async def _prepare_excel_connection(user_id: str, clean_file_name: str) -> dict[str, Any]:
    syncing_payload = {
        "provider": "cube",
        "name": clean_file_name,
        "auth_mode": "connector",
        "status": "syncing",
        "is_default": True,
        "last_error": None,
        "config": {
            "source": "excel",
            "file_name": clean_file_name,
            "engine": "duckdb+cube",
            "storage": "connector_generated_files",
        },
        "health": {"metadata": "syncing"},
    }
    existing = await _active_excel_connection(user_id)
    if existing:
        updated = await sb.rest_patch(
            "connector_instances",
            syncing_payload,
            params={"id": f"eq.{existing['id']}", "owner_user_id": f"eq.{user_id}"},
        )
        connection = updated[0] if updated else {**existing, **syncing_payload}
        await _disable_stale_excel_connections(user_id, connection["id"])
        return connection

    created = await sb.rest_post(
        "connector_instances",
        {
            "owner_user_id": user_id,
            "connector_key": "excel",
            **syncing_payload,
        },
    )
    return created[0]


async def create_excel_connection_from_upload(user_id: str, file_name: str, content: bytes) -> dict[str, Any]:
    clean_file_name = file_name or "workbook.xlsx"
    if not clean_file_name.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Por ahora el conector Excel acepta archivos .xlsx")
    if len(content) > MAX_EXCEL_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="El workbook supera el limite de 25 MB")

    company_context = await require_company_context(user_id)
    workbook = parse_xlsx_workbook(content)
    try:
        connection = await _prepare_excel_connection(user_id, clean_file_name)
        connection_id = connection["id"]
        sync = await create_sync_run(user_id, connection_id)

        try:
            normalized = _build_catalog(connection_id, clean_file_name, workbook)
            await _apply_ai_field_suggestions(normalized, company_context)
            _write_excel_artifacts(connection_id, workbook, normalized["relationships"])
            counters = await persist_catalog(
                owner_user_id=user_id,
                connection_id=connection_id,
                provider="cube",
                normalized=normalized,
                preserve_existing_approvals=False,
            )
            table_summaries = [
                {
                    "sheet_name": table["sheet_name"],
                    "table_name": table["table_name"],
                    "cube_name": table["cube_name"],
                    "rows": table.get("row_count", 0),
                    "columns": len(table["columns"]),
                }
                for table in workbook["tables"]
            ]
            await sb.rest_patch(
                "connector_instances",
                {
                    "status": "review",
                    "last_sync_at": utc_now_iso(),
                    "last_error": None,
                    "config": {
                        "source": "excel",
                        "file_name": clean_file_name,
                        "engine": "duckdb+cube",
                        "storage": "connector_generated_files",
                        "tables": table_summaries,
                        "onboarding": {"status": "review"},
                    },
                    "health": {
                        "metadata": "review",
                        "tables": len(table_summaries),
                        "onboarding": {"status": "review"},
                    },
                },
                params={"id": f"eq.{connection_id}"},
            )
            clear_semantic_catalog_cache(user_id, connection_id)
            await finish_sync_run(sync["id"], "success", counters={**counters, "tables_detail": table_summaries})
            visible_fields = [
                field for field in normalized.get("fields", [])
                if not field.get("is_hidden") and field.get("is_ai_enabled") is not False
            ]
            review_fields = [field for field in visible_fields if field.get("approval_status") == "review"]
            return {
                "connection": {
                    **connection,
                    "status": "review",
                    "is_default": True,
                    "config": {
                        "source": "excel",
                        "file_name": clean_file_name,
                        "engine": "duckdb+cube",
                        "storage": "connector_generated_files",
                        "tables": table_summaries,
                        "onboarding": {"status": "review"},
                    },
                },
                "onboarding": {
                    "connection_id": connection_id,
                    "status": "review",
                    "phase": "fields",
                    "company_context": company_context,
                    "fields_total": len(visible_fields),
                    "fields_in_review": len(review_fields),
                    "technical_fields_hidden": len(normalized.get("fields", [])) - len(visible_fields),
                },
                "tables": table_summaries,
                "catalog": counters,
            }
        except Exception as exc:
            detail = getattr(exc, "detail", None) or str(exc)
            await sb.rest_patch(
                "connector_instances",
                {"status": "error", "last_error": str(detail), "health": {"metadata": "error"}},
                params={"id": f"eq.{connection_id}"},
                prefer="",
            )
            clear_semantic_catalog_cache(user_id, connection_id)
            await finish_sync_run(sync["id"], "failed", error=str(detail))
            raise
    finally:
        temp_dir = workbook.get("temp_dir")
        if temp_dir:
            shutil.rmtree(Path(str(temp_dir)), ignore_errors=True)
