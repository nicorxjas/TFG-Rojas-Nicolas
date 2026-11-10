from typing import Any, Optional

from fastapi import HTTPException

from services import supabase_rest as sb


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _context_complete(context: dict[str, Any]) -> bool:
    return bool(_clean_text(context.get("sector")) and _clean_text(context.get("details")))


async def fetch_company_context(user_id: Optional[str]) -> dict[str, Any]:
    if not user_id:
        return {
            "company_name": "",
            "sector": "",
            "details": "",
            "complete": False,
        }

    rows = await sb.rest_get(
        "company_settings",
        {
            "select": "company_name,sector,details",
            "id": f"eq.{user_id}",
            "limit": "1",
        },
    )
    row = rows[0] if rows else {}
    context = {
        "company_name": _clean_text(row.get("company_name")),
        "sector": _clean_text(row.get("sector")),
        "details": _clean_text(row.get("details")),
    }
    context["complete"] = _context_complete(context)
    return context


def company_context_prompt(context: Optional[dict[str, Any]]) -> str:
    context = context or {}
    lines = []
    company_name = _clean_text(context.get("company_name"))
    sector = _clean_text(context.get("sector"))
    details = _clean_text(context.get("details"))

    if company_name:
        lines.append(f"Empresa: {company_name}")
    if sector:
        lines.append(f"Sector: {sector}")
    if details:
        lines.append(f"Descripcion, objetivos y contexto operativo: {details}")

    if not lines:
        return "Contexto de empresa no configurado."
    return "\n".join(lines)


async def require_company_context(user_id: str) -> dict[str, Any]:
    context = await fetch_company_context(user_id)
    if not context.get("complete"):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "company_context_required",
                "message": "Completa el sector y la descripcion del negocio en Perfil antes de generar el catalogo semantico.",
                "company_context": context,
            },
        )
    return context
