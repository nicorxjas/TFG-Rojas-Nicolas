"""Collect a QA iteration without changing original results or their verdicts."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def collect(folder):
    manifest = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "runs": {},
                "note": "Los estados automáticos originales no se modifican. La revisión semántica se registra por separado."}
    register = ["# Registro completo de la iteración de QA", "",
                "Cada intento conserva preguntas, respuestas, oráculos, eventos SSE, historial seleccionado y trazas en su results.json original.", ""]
    for path in sorted(folder.glob("*/results.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        turns = data.get("turns") or []
        complete = [t for t in turns if t.get("status")]
        counts = dict(Counter(t["status"] for t in complete))
        manifest["runs"][path.parent.name] = {"turns_completed": len(complete), "counts": counts,
            "run_finished": bool(data.get("summary")), "fatal_error": data.get("fatal_error"),
            "model": data.get("model"), "provider": data.get("provider"),
            "blocked_write_attempts": data.get("blocked_write_attempts"),
            "runner_sha256": data.get("runner_sha256"), "implementation_sha256": data.get("implementation_sha256"),
            "csv_sha256": data.get("csv_sha256"), "results_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        register.extend([f"## {path.parent.name}", "", f"Estados originales: `{json.dumps(counts)}`. Archivo: [{path.name}](<{path.as_posix()}>).", ""])
        for turn in turns:
            case = turn["case"]
            register.extend([f"### {case['id']} · repetición {turn['repeat'] + 1}", "",
                f"**Pregunta:** {case['prompt']}", "", f"**Estado automático:** {turn.get('status', 'interrumpido/sin finalizar')}", "",
                "**Respuesta de texto:**", "", turn.get("answer") or "(Sin chunk de texto; ver eventos de sugerencia, error o interrupción.)", ""])
            for event in turn.get("events") or []:
                if event.get("type") in {"metric_suggestion", "error"}:
                    register.extend([f"**Evento {event['type']}:**", "", "```json", json.dumps(event.get("content"), ensure_ascii=False, indent=2), "```", ""])
            checks = turn.get("checks") or {}
            register.extend([f"**Checks fallidos:** {', '.join(k for k, v in checks.items() if not v) or 'ninguno'}.", "",
                             f"**Traza:** `{turn.get('trace_id')}`. **Duración:** {turn.get('seconds')} s.", "",
                             "**Oráculo congelado:**", "", "```json", json.dumps(case.get("expected"), ensure_ascii=False, indent=2), "```", ""])
            for execution in turn.get("executions") or []:
                register.extend(["**Consultas, evidencia y errores de ejecución:**", "", "```json", json.dumps({
                    "queries": [spec.get("query") for spec in execution.get("plan", {}).get("queries") or []],
                    "validation_errors": execution.get("validation_errors"),
                    "evidence": [{key: item.get(key) for key in ("query", "data", "coverage", "warnings")}
                                 for item in execution.get("evidence") or []]}, ensure_ascii=False, indent=2), "```", ""])
    manifest["final_source_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [ROOT / name for name in ("backend/api/chat.py", "backend/api/semantic_metrics.py",
            "backend/services/semantic_planner.py", "backend/services/semantic_query_engine.py",
            "backend/services/bi_conversation.py", "backend/services/conversation_context.py",
            "backend/services/recommendation_evidence.py", "frontend/src/lib/chat-history.ts",
            "frontend/src/lib/chat-events.ts", "frontend/src/components/layout/PlatformLayout.tsx",
            "frontend/src/components/chat/Sidebar.tsx", "frontend/src/components/chat/ChatSidebar.tsx", "frontend/src/components/chat/ChatArea.tsx")]}
    manifest["git_status"] = subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True, encoding="utf-8").splitlines()
    manifest["test_logs"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob("*.log")}
    save(folder / "manifest.json", manifest)
    (folder / "registro-completo.md").write_text("\n".join(register), encoding="utf-8")
    print(json.dumps({name: run["counts"] for name, run in manifest["runs"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    collect(parser.parse_args().output.resolve())
