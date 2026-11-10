from api.semantic_metrics import evaluate_compiled_expression

def normalize_date_range_val(val):
    if isinstance(val, str):
        val_clean = val.strip("'\" ")
        if val_clean.isdigit() and len(val_clean) == 4:
            return [f"{val_clean}-01-01", f"{val_clean}-12-31"]
        return val_clean
    elif isinstance(val, list):
        if len(val) == 1 and isinstance(val[0], str):
            item = val[0].strip("'\" ")
            if item.isdigit() and len(item) == 4:
                return [f"{item}-01-01", f"{item}-12-31"]
        new_list = []
        for item in val:
            if isinstance(item, str):
                item_clean = item.strip("'\" ")
                if item_clean.isdigit() and len(item_clean) == 4:
                    new_list.append(f"{item_clean}-01-01")
                else:
                    new_list.append(item)
            else:
                new_list.append(item)
        return new_list
    return val

def normalize_compare_range_val(val):
    if isinstance(val, str):
        val_clean = val.strip("'\" ")
        if val_clean.isdigit() and len(val_clean) == 4:
            return [f"{val_clean}-01-01", f"{val_clean}-12-31"]
        return val_clean
    elif isinstance(val, list):
        new_list = []
        for item in val:
            if isinstance(item, str):
                item_clean = item.strip("'\" ")
                if item_clean.isdigit() and len(item_clean) == 4:
                    new_list.append(f"{item_clean}-01-01")
                    new_list.append(f"{item_clean}-12-31")
                else:
                    new_list.append(item)
            elif isinstance(item, list):
                new_sublist = []
                for subitem in item:
                    if isinstance(subitem, str):
                        subitem_clean = subitem.strip("'\" ")
                        if subitem_clean.isdigit() and len(subitem_clean) == 4:
                            new_sublist.append(f"{subitem_clean}-01-01")
                            new_sublist.append(f"{subitem_clean}-12-31")
                        else:
                            new_sublist.append(subitem)
                    else:
                        new_sublist.append(subitem)
                new_list.append(new_sublist)
            else:
                new_list.append(item)
        return new_list
    return val

def normalize_time_dimensions(query: dict) -> dict:
    if not isinstance(query, dict):
        return query
        
    q = query.copy()
    time_dims = q.get("timeDimensions", [])
    if not isinstance(time_dims, list):
        if isinstance(time_dims, dict):
            time_dims = [time_dims]
        else:
            time_dims = []
            
    normalized = []
    merged_compare = None
    
    for td in time_dims:
        if not isinstance(td, dict):
            continue
            
        if "compareDateRange" in td:
            merged_compare = td["compareDateRange"]
            if len(td) == 1 or (len(td) == 2 and "dimension" not in td):
                continue
                
        normalized.append(td)
        
    if not normalized and (merged_compare or time_dims):
        normalized.append({})
        
    new_time_dims = []
    for td in normalized:
        td_copy = td.copy()
        
        import re
        if (
            "dimension" not in td_copy 
            or not td_copy["dimension"] 
            or not isinstance(td_copy["dimension"], str)
            or not re.match(r"^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$", td_copy["dimension"])
        ):
            continue
            
        if "dateRange" in td_copy:
            td_copy["dateRange"] = normalize_date_range_val(td_copy["dateRange"])
            
        if "compareDateRange" in td_copy:
            td_copy["compareDateRange"] = normalize_compare_range_val(td_copy["compareDateRange"])
            
        # Strip compareDateRange to prevent CubeJS client error
        if "compareDateRange" in td_copy:
            del td_copy["compareDateRange"]
            
        new_time_dims.append(td_copy)
        
    q["timeDimensions"] = new_time_dims
    return q

def map_invalid_dimensions(query: dict) -> tuple[dict, dict]:
    return query, {}

def process_computed_metrics(query: dict, metric_catalog: list[dict] = None) -> tuple[dict, list[str], dict]:
    """
    Analiza una consulta de Cube, remueve las mÃ©tricas calculadas que Cube no soporta
    directamente y agrega sus dependencias. Devuelve la query reescrita, la lista de
    measures originales y un mapeo de las mÃ©tricas calculadas que deben procesarse.
    """
    original_measures = query.get("measures", [])
    if not original_measures:
        return query, original_measures, {}

    computed_info = {}
    query_measures = []
    
    COMPUTED_DEFINITIONS = {}

    for metric in metric_catalog or []:
        if metric.get("source") != "custom":
            continue

        metric_key = metric.get("key")
        dependencies = metric.get("cube_dependencies") or []
        compiled_expression = metric.get("compiled_expression")
        variables = metric.get("variables") or {}
        if not metric_key or not dependencies or not compiled_expression:
            continue

        def calculate_custom(row, calculated_vals=None, expr=compiled_expression, vars_map=variables):
            values_row = dict(row)
            values_row.update(calculated_vals or {})
            return evaluate_compiled_expression(expr, vars_map, values_row)

        COMPUTED_DEFINITIONS[metric_key] = {
            "dependencies": list(dict.fromkeys([*dependencies, *variables.values()])),
            "calculate": calculate_custom
        }
    
    visiting = set()
    def include_metric(member):
        if member in visiting:
            raise ValueError("Hay una dependencia circular entre metricas.")
        if member in computed_info:
            return
        if member in COMPUTED_DEFINITIONS:
            visiting.add(member)
            for dependency in COMPUTED_DEFINITIONS[member]["dependencies"]:
                include_metric(dependency)
            visiting.remove(member)
            computed_info[member] = COMPUTED_DEFINITIONS[member]
        elif member not in query_measures:
            query_measures.append(member)
    for member in original_measures:
        include_metric(member)

    if not computed_info:
        return query, original_measures, {}
        
    rewritten_query = query.copy()
    rewritten_query["measures"] = query_measures
    return rewritten_query, original_measures, computed_info


def post_process_cube_response(cube_response: dict, original_measures: list[str], computed_info: dict, strip_dependencies: bool = True, reverse_map: dict = None) -> dict:
    """
    Toma la respuesta de Cube y calcula las mÃ©tricas dinÃ¡micas para cada fila,
    preservando el orden y estructura de columnas que el cliente originalmente solicitÃ³.
    """
    if not computed_info and not reverse_map:
        return cube_response
        
    data = cube_response.get("data", [])
    new_data = []
    
    # Identificar quÃ© llaves corresponden a dependencias
    query_measures = []
    if computed_info:
        for info in computed_info.values():
            query_measures.extend(info["dependencies"])
        
    for row in data:
        calculated_vals = {}
        if computed_info:
            def calculate_metric(metric_key: str):
                if metric_key in calculated_vals:
                    return calculated_vals[metric_key]
                info = computed_info.get(metric_key)
                if not info:
                    return row.get(metric_key)
                for dep in info.get("dependencies", []):
                    if dep in computed_info:
                        calculate_metric(dep)
                try:
                    value = info["calculate"](row, calculated_vals)
                except TypeError:
                    value = info["calculate"](row)
                calculated_vals[metric_key] = value
                return value

            for m in computed_info.keys():
                calculate_metric(m)
            
        new_row = {}
        
        # 1. Agregar llaves de dimensiones/fecha primero (que no son medidas)
        for k, v in row.items():
            if k not in query_measures and k not in original_measures:
                mapped_key = reverse_map.get(k, k) if reverse_map else k
                new_row[mapped_key] = v
                
        # 2. Agregar measures originales solicitadas en el orden correcto
        for m in original_measures:
            if m in calculated_vals:
                new_row[m] = calculated_vals[m]
            else:
                new_row[m] = row.get(m)
                
        # 3. Si NO queremos eliminar las dependencias, las agregamos al final
        if not strip_dependencies:
            for dep in query_measures:
                if dep not in new_row:
                    new_row[dep] = row.get(dep)
                    
        new_data.append(new_row)
        
    rewritten_response = cube_response.copy()
    rewritten_response["data"] = new_data
    return rewritten_response
