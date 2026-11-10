"""Subscription-backed, inference-only adapter for the local Codex App Server.

One serialized worker owns stdio; callers never receive or supply OAuth tokens.
Each completion gets an ephemeral thread with no environment or external tools.
"""
import asyncio
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

import httpx

CODEX_BASE_URL = "http://codex-app-server.local/v1"
DEFAULT_CODEX_MODEL = "gpt-5.6-luna"


class CodexError(RuntimeError):
    pass


def codex_executable() -> str:
    configured = os.getenv("CODEX_EXECUTABLE")
    if configured:
        if not Path(configured).is_file():
            raise CodexError("CODEX_EXECUTABLE no apunta a un ejecutable existente.")
        return configured
    found = shutil.which("codex")
    if found:
        return found
    # Codex Desktop versions its bundled CLI on Windows.
    root = Path(os.getenv("LOCALAPPDATA", "")) / "OpenAI/Codex/bin"
    candidates = list(root.glob("*/codex.exe")) if root.is_dir() else []
    if candidates:
        return str(max(candidates, key=lambda path: path.stat().st_mtime))
    raise CodexError("No encontré Codex CLI. Instalalo o configurá CODEX_EXECUTABLE.")


class CodexAppServer:
    def __init__(self):
        self._lock = threading.Lock()
        self._process = None
        self._messages = queue.Queue()
        self._request_id = 0
        self._workspace = None
        self._models = {}
        self._disabled_mcp = {}

    def close(self):
        process, self._process = self._process, None
        if process:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout):
                if pipe:
                    pipe.close()
        if self._workspace:
            self._workspace.cleanup()
            self._workspace = None
        self._models = {}

    def _read_stdout(self, process, inbox):
        try:
            for line in process.stdout:
                try:
                    inbox.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
        finally:
            inbox.put(None)

    def _send(self, message):
        if not self._process or self._process.poll() is not None:
            raise CodexError("Codex App Server no está disponible.")
        self._process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self._process.stdin.flush()

    def _next(self, deadline, cancelled):
        while True:
            if cancelled.is_set():
                raise CodexError("La solicitud a Codex fue cancelada.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Codex superó el tiempo máximo de respuesta.")
            try:
                message = self._messages.get(timeout=min(remaining, 0.25))
            except queue.Empty:
                continue
            if message is None:
                raise CodexError("Codex App Server cerró la conexión.")
            # No tool, approval, or credential-refresh requests are delegated to
            # the model or silently accepted. Authentication is CLI-managed.
            if "id" in message and "method" in message:
                self._send({"id": message["id"], "error": {"code": -32601, "message": "Inference-only client: tools and approvals are disabled."}})
                raise CodexError("Codex solicitó una herramienta o permiso no habilitado para esta integración.")
            return message

    def _rpc(self, method, params, deadline, cancelled):
        self._request_id += 1
        request_id = self._request_id
        self._send({"id": request_id, "method": method, "params": params})
        while True:
            message = self._next(deadline, cancelled)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise CodexError(f"Codex {method}: {message['error'].get('message', 'Error del protocolo')}")
            return message.get("result") or {}

    def _start(self, deadline, cancelled):
        if self._process and self._process.poll() is None:
            return
        self.close()
        self._workspace = tempfile.TemporaryDirectory(prefix="nyro-codex-")
        self._messages = queue.Queue()
        command = [codex_executable(), "app-server", "--stdio"]
        for feature in ["shell_tool", "unified_exec", "apps", "plugins", "browser_use", "computer_use", "skill_search", "workspace_dependencies"]:
            command.extend(["-c", f"features.{feature}=false"])
        command.extend(["-c", "features.skip_host_skill_discovery=true", "-c", 'web_search="disabled"'])
        environment = os.environ.copy()
        # Never switch this adapter to separately billed API authentication.
        for key in ("OPENAI_API_KEY", "CODEX_API_KEY"):
            environment.pop(key, None)
        self._process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
            cwd=self._workspace.name, env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(target=self._read_stdout, args=(self._process, self._messages), daemon=True).start()
        self._rpc("initialize", {"clientInfo": {"name": "nyro_analytics", "version": "1.0.0"},
                                 "capabilities": {"experimentalApi": True}}, deadline, cancelled)
        self._send({"method": "initialized", "params": {}})
        account = self._rpc("account/read", {}, deadline, cancelled).get("account") or {}
        if account.get("type") != "chatgpt":
            raise CodexError("Codex necesita iniciar sesión con ChatGPT. Ejecutá `codex login` en esta computadora; no uses una API key.")
        cursor = None
        while True:
            result = self._rpc("model/list", {"limit": 100, "cursor": cursor}, deadline, cancelled)
            self._models.update({item["model"]: item for item in result.get("data", [])})
            cursor = result.get("nextCursor")
            if not cursor:
                break
        # Disable all user-configured MCP servers for inference threads without
        # rewriting the user's global config or accessing their credentials.
        config = self._rpc("config/read", {"includeLayers": False}, deadline, cancelled).get("config") or {}
        self._disabled_mcp = {f"mcp_servers.{name}.enabled": False for name in config.get("mcp_servers", {})}

    def inspect(self):
        with self._lock:
            try:
                self._start(time.monotonic() + 45, threading.Event())
                return {"authentication": "chatgpt", "models": list(self._models),
                        "disabled_mcp_servers": len(self._disabled_mcp)}
            except Exception:
                self.close()
                raise

    async def complete(self, payload, timeout=120):
        cancelled = threading.Event()
        task = asyncio.create_task(asyncio.to_thread(self._complete_sync, payload, timeout, cancelled))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled.set()
            try:
                await asyncio.shield(task)
            except Exception:
                pass
            raise

    def _complete_sync(self, payload, timeout, cancelled):
        deadline = time.monotonic() + timeout
        while not self._lock.acquire(timeout=0.1):
            if cancelled.is_set() or time.monotonic() >= deadline:
                raise TimeoutError("Se agotó la espera en la cola de Codex.")
        try:
            self._start(deadline, cancelled)
            model = payload.get("model") or os.getenv("LLM_MODEL") or DEFAULT_CODEX_MODEL
            if model not in self._models:
                raise CodexError(f"El modelo {model} no está disponible en esta sesión de Codex. No se cambió a otro modelo.")
            effort = payload.get("reasoning_effort") or os.getenv("CODEX_REASONING_EFFORT", "low")
            supported = {item["reasoningEffort"] for item in self._models[model].get("supportedReasoningEfforts", [])}
            if supported and effort not in supported:
                raise CodexError(f"El modelo {model} no admite razonamiento {effort}.")
            instructions, conversation, schema, tool_names = prepare_completion(payload)
            started = self._rpc("thread/start", {
                "model": model, "modelProvider": "openai", "ephemeral": True,
                "cwd": self._workspace.name, "environments": [], "selectedCapabilityRoots": [],
                "approvalPolicy": "never", "sandbox": "read-only", "personality": "none",
                "baseInstructions": instructions, "developerInstructions": "",
                "config": {**self._disabled_mcp, "web_search": "disabled"},
            }, deadline, cancelled)
            thread_id = started["thread"]["id"]
            turn_params = {"threadId": thread_id, "model": model, "effort": effort,
                           "environments": [], "input": [{"type": "text", "text": conversation}]}
            if schema:
                turn_params["outputSchema"] = schema
            result = self._rpc("turn/start", turn_params, deadline, cancelled)
            turn_id = result["turn"]["id"]
            final_text = ""
            usage = {}
            while True:
                event = self._next(deadline, cancelled)
                params = event.get("params") or {}
                if params.get("threadId") != thread_id:
                    continue
                if event.get("method") == "item/completed":
                    item = params.get("item") or {}
                    if item.get("type") == "agentMessage" and item.get("phase") in {None, "final_answer"}:
                        final_text = item.get("text") or ""
                elif event.get("method") == "thread/tokenUsage/updated":
                    usage = (params.get("tokenUsage") or {}).get("last") or {}
                elif event.get("method") == "turn/completed" and params.get("turn", {}).get("id") == turn_id:
                    turn = params["turn"]
                    if turn.get("status") != "completed":
                        error = turn.get("error") or {}
                        raise CodexError(error.get("message") or f"Codex terminó con estado {turn.get('status')}.")
                    break
            response = completion_response(payload, final_text, model, usage, tool_names)
            self._rpc("thread/unsubscribe", {"threadId": thread_id}, deadline, cancelled)
            return response
        except Exception:
            # Also terminates any still-running turn; a timed-out request must
            # not continue consuming the subscription in the background.
            self.close()
            raise
        finally:
            self._lock.release()


def prepare_completion(payload):
    messages = payload.get("messages") or []
    systems = [str(message.get("content") or "") for message in messages if message.get("role") in {"system", "developer"}]
    history = [message for message in messages if message.get("role") not in {"system", "developer"}]
    instructions = ("Respondé a la última solicitud usando exclusivamente el contexto recibido. "
                    "No accedas a archivos, aplicaciones, internet ni herramientas del equipo. "
                    "El historial se entrega como JSON con roles; no simules resultados de herramientas.\n\n" + "\n\n".join(systems))
    response_format = payload.get("response_format") or {}
    schema = (response_format.get("json_schema") or {}).get("schema") if response_format.get("type") == "json_schema" else None
    if response_format.get("type") == "json_object":
        instructions += "\nDevolvé exclusivamente un objeto JSON válido, sin Markdown ni texto adicional."
    tool_names = []
    if payload.get("tools") and payload.get("tool_choice") != "none":
        functions = [item["function"] for item in payload["tools"] if item.get("type") == "function"]
        tool_names = [function["name"] for function in functions]
        if not tool_names:
            raise CodexError("Solo se admiten herramientas de tipo function.")
        instructions += ("\nLas siguientes funciones pertenecen al backend. Proponé llamadas en tool_calls; "
                         "el backend las validará y ejecutará. No las ejecutes ni inventes su resultado. "
                         "arguments debe ser un string JSON válido con los parámetros de la función.\n" + json.dumps(functions, ensure_ascii=False))
        schema = {"type": "object", "properties": {"content": {"type": ["string", "null"]}, "tool_calls": {
            "type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string", "enum": tool_names}, "arguments": {"type": "string"}},
                "required": ["name", "arguments"], "additionalProperties": False}}},
            "required": ["content", "tool_calls"], "additionalProperties": False}
        if payload.get("tool_choice") == "required":
            instructions += "\nEsta solicitud requiere al menos una llamada a función."
    return instructions, json.dumps(history, ensure_ascii=False), schema, tool_names


def completion_response(payload, text, model, usage, tool_names):
    if not text:
        raise CodexError("Codex no devolvió una respuesta final.")
    message = {"role": "assistant", "content": text}
    finish_reason = "stop"
    if tool_names:
        parsed = json.loads(text)
        calls = []
        for call in parsed.get("tool_calls", []):
            if call.get("name") not in tool_names or not isinstance(json.loads(call["arguments"]), dict):
                raise CodexError("Codex propuso una llamada de herramienta inválida.")
            calls.append({"id": "call_" + uuid.uuid4().hex, "type": "function", "function": {
                "name": call["name"], "arguments": call["arguments"]}})
        if payload.get("tool_choice") == "required" and not calls:
            raise CodexError("Codex no propuso la llamada de herramienta requerida.")
        message["content"] = parsed.get("content")
        if calls:
            message["tool_calls"] = calls
            finish_reason = "tool_calls"
    elif (payload.get("response_format") or {}).get("type") in {"json_object", "json_schema"}:
        if not isinstance(json.loads(text), dict):
            raise CodexError("Codex no devolvió el objeto JSON solicitado.")
    return {"id": "chatcmpl-" + uuid.uuid4().hex, "object": "chat.completion", "created": int(time.time()),
            "model": model, "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": usage.get("inputTokens", 0), "completion_tokens": usage.get("outputTokens", 0),
                      "total_tokens": usage.get("totalTokens", 0)}}


server = CodexAppServer()


class CodexTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self._http = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request):
        if str(request.url) != CODEX_BASE_URL + "/chat/completions":
            return await self._http.handle_async_request(request)
        payload = json.loads(await request.aread())
        timeout = float((request.extensions.get("timeout") or {}).get("read") or 120)
        try:
            result = await server.complete(payload, timeout)
        except TimeoutError as exc:
            return httpx.Response(504, json={"error": {"message": str(exc)}}, request=request)
        except (CodexError, ValueError) as exc:
            return httpx.Response(503, json={"error": {"message": str(exc)}}, request=request)
        if payload.get("stream"):
            # Send only completed, validated final content. This is buffered SSE,
            # not token streaming; never expose Codex commentary or reasoning.
            choice = result["choices"][0]
            chunk = {"id": result["id"], "object": "chat.completion.chunk", "model": result["model"],
                     "choices": [{"index": 0, "delta": choice["message"], "finish_reason": choice["finish_reason"]}]}
            body = "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\ndata: [DONE]\n\n"
            return httpx.Response(200, content=body.encode("utf-8"), headers={"Content-Type": "text/event-stream"}, request=request)
        return httpx.Response(200, json=result, request=request)

    async def aclose(self):
        await self._http.aclose()
