from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import health
from services.supabase_rest import close_clients

app = FastAPI(title="Nyro Analytics API", version="0.1.0")

# Configuracion de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
from api import chat
app.include_router(chat.router)
from api import reports
app.include_router(reports.router)
from api import semantic_metrics
app.include_router(semantic_metrics.router)
from api import semantic_onboarding
app.include_router(semantic_onboarding.router)
from api import powerbi
app.include_router(powerbi.router)
from api import excel
app.include_router(excel.router)
from api import semantic_query
app.include_router(semantic_query.router)
from api import semantic_plan
app.include_router(semantic_plan.router)
from api import semantic_metric_drafts
app.include_router(semantic_metric_drafts.router)


@app.on_event("shutdown")
async def close_supabase_rest_clients() -> None:
    await close_clients()
    import asyncio
    from services.codex_llm import server
    await asyncio.to_thread(server.close)
