import asyncio
import json
import os
import threading
import time
import unittest
from unittest.mock import AsyncMock, patch

from api.llm import get_llm_headers, get_llm_model, get_llm_chat_url, llm_client
from services.codex_llm import (
    CODEX_BASE_URL, CodexAppServer, CodexError, completion_response,
    prepare_completion, server,
)


class CodexAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_provider_never_sends_api_credentials(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "codex", "GEMINI_API_KEY": "secret", "LLM_API_KEY": "secret"}, clear=True):
            self.assertEqual(get_llm_model(), "gpt-5.6-luna")
            self.assertEqual(get_llm_headers(), {"Content-Type": "application/json"})
            self.assertEqual(get_llm_chat_url(), CODEX_BASE_URL + "/chat/completions")

    def test_preserves_history_and_generic_function_definitions(self):
        history = [{"role": "user", "content": "Consulta"}, {"role": "tool", "tool_call_id": "x", "content": "[]"}]
        payload = {"messages": [{"role": "system", "content": "Regla del dominio"}, *history],
                   "tools": [{"type": "function", "function": {"name": "arbitrary_lookup", "parameters": {"type": "object"}}}]}
        instructions, conversation, schema, names = prepare_completion(payload)
        self.assertIn("Regla del dominio", instructions)
        self.assertEqual(json.loads(conversation), history)
        self.assertEqual(names, ["arbitrary_lookup"])
        self.assertEqual(schema["properties"]["tool_calls"]["items"]["properties"]["name"]["enum"], names)

    def test_rejects_invented_function_and_missing_required_call(self):
        for text in ['{"content":null,"tool_calls":[{"name":"invented","arguments":"{}"}]}', '{"content":"x","tool_calls":[]}']:
            with self.assertRaises(CodexError):
                completion_response({"tool_choice": "required"}, text, "test", {}, ["lookup"])

    def test_maps_backend_calls_without_executing_them(self):
        result = completion_response({}, '{"content":null,"tool_calls":[{"name":"lookup","arguments":"{\\"key\\": 3}"}]}', "test", {}, ["lookup"])
        choice = result["choices"][0]
        self.assertEqual(choice["finish_reason"], "tool_calls")
        self.assertEqual(json.loads(choice["message"]["tool_calls"][0]["function"]["arguments"]), {"key": 3})

    async def test_routes_json_and_buffered_sse_without_network(self):
        result = completion_response({}, "respuesta", "test", {}, [])
        with patch.dict(os.environ, {"LLM_PROVIDER": "codex"}), patch.object(server, "complete", new=AsyncMock(return_value=result)) as complete:
            async with llm_client() as client:
                response = await client.post(get_llm_chat_url(), json={"messages": []})
                self.assertEqual(response.json()["choices"][0]["message"]["content"], "respuesta")
                async with client.stream("POST", get_llm_chat_url(), json={"stream": True}) as response:
                    lines = [line async for line in response.aiter_lines() if line]
                self.assertEqual(lines[-1], "data: [DONE]")
                self.assertEqual(json.loads(lines[0][6:])["choices"][0]["delta"]["content"], "respuesta")
            self.assertEqual(complete.await_count, 2)

    async def test_provider_errors_are_visible(self):
        for error, status in [(CodexError("login required"), 503), (TimeoutError("timeout"), 504)]:
            with patch.dict(os.environ, {"LLM_PROVIDER": "codex"}), patch.object(server, "complete", new=AsyncMock(side_effect=error)):
                async with llm_client() as client:
                    response = await client.post(get_llm_chat_url(), json={})
                    self.assertEqual(response.status_code, status)

    def test_rejects_server_tool_requests(self):
        worker = CodexAppServer()
        worker._messages.put({"id": 1, "method": "item/commandExecution/requestApproval"})
        with patch.object(worker, "_send") as send:
            with self.assertRaises(CodexError):
                worker._next(time.monotonic() + 1, threading.Event())
            self.assertIn("error", send.call_args.args[0])

    async def test_cancellation_signals_worker_before_returning(self):
        worker = CodexAppServer()
        stopped = threading.Event()
        def fake_complete(payload, timeout, cancelled):
            cancelled.wait(2)
            if cancelled.is_set():
                stopped.set()
        with patch.object(worker, "_complete_sync", side_effect=fake_complete):
            task = asyncio.create_task(worker.complete({}))
            await asyncio.sleep(0.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(stopped.is_set())
