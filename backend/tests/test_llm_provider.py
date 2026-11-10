import os
import unittest
from unittest.mock import patch

from api.llm import (
    get_llm_chat_url, get_llm_headers, get_llm_model,
    get_llm_provider, get_llm_timeout, llm_is_configured, llm_payload,
)


class LlmProviderTests(unittest.TestCase):
    def test_cpu_timeout_only_applies_to_ollama(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_llm_timeout(45), 300)
        with patch.dict(os.environ, {"OLLAMA_TIMEOUT_SECONDS": "180"}, clear=True):
            self.assertEqual(get_llm_timeout(45), 180)
            self.assertEqual(get_llm_timeout(400), 400)
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini"}, clear=True):
            self.assertEqual(get_llm_timeout(45), 45)

    def test_local_default_ignores_old_gemini_credentials(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "secret", "GEMINI_MODEL": "gemini-old"}, clear=True):
            self.assertEqual(get_llm_provider(), "ollama")
            self.assertEqual(get_llm_model(), "llama3.1:8b")
            self.assertEqual(get_llm_chat_url(), "http://localhost:11434/v1/chat/completions")
            self.assertEqual(get_llm_headers(), {"Content-Type": "application/json"})
            self.assertTrue(llm_is_configured())

    def test_local_override_and_payload_preserve_structured_streaming(self):
        with patch.dict(os.environ, {"LLM_MODEL": "local:test", "LLM_BASE_URL": "http://localhost:11434/v1/chat/completions/"}, clear=True):
            original = {"reasoning_effort": "low", "stream": True, "response_format": {"type": "json_object"}}
            result = llm_payload(original)
            self.assertEqual(result["model"], "local:test")
            self.assertNotIn("reasoning_effort", result)
            self.assertIn("reasoning_effort", original)
            self.assertTrue(result["stream"])
            self.assertEqual(result["response_format"], original["response_format"])
            self.assertEqual(get_llm_chat_url(), "http://localhost:11434/v1/chat/completions")

    def test_gemini_remains_explicitly_available(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test", "GEMINI_MODEL": "gemini-test"}, clear=True):
            self.assertEqual(get_llm_model(), "gemini-test")
            self.assertIn("googleapis.com", get_llm_chat_url())
            self.assertEqual(get_llm_headers()["Authorization"], "Bearer test")
            self.assertEqual(llm_payload({"reasoning_effort": "low"})["reasoning_effort"], "low")
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini"}, clear=True):
            self.assertFalse(llm_is_configured())

    def test_unknown_provider_fails_instead_of_using_remote_api(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "typo"}, clear=True):
            with self.assertRaises(ValueError):
                get_llm_provider()

    def test_reports_accept_local_model(self):
        from api.reports import get_report_llm_model
        with patch.dict(os.environ, {"REPORT_LLM_MODEL": "llama3.1:8b"}, clear=True):
            self.assertEqual(get_report_llm_model(), "llama3.1:8b")
