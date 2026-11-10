import os
import httpx
from urllib.parse import urljoin


GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
OLLAMA_OPENAI_BASE_URL = "http://localhost:11434/v1"


def _load_env_file() -> None:
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip("'\" "))


_load_env_file()


def get_llm_provider() -> str:
    provider = (os.getenv("LLM_PROVIDER") or "ollama").strip().lower()
    if provider not in {"ollama", "gemini", "codex"}:
        raise ValueError(f"LLM_PROVIDER no soportado: {provider}")
    return provider


def get_llm_model() -> str:
    if get_llm_provider() == "codex":
        from services.codex_llm import DEFAULT_CODEX_MODEL
        return (os.getenv("LLM_MODEL") or DEFAULT_CODEX_MODEL).strip()
    if get_llm_provider() == "ollama":
        return (os.getenv("LLM_MODEL") or DEFAULT_OLLAMA_MODEL).strip()
    return (os.getenv("GEMINI_MODEL") or os.getenv("LLM_MODEL") or DEFAULT_GEMINI_MODEL).strip()


def get_llm_base_url() -> str:
    if get_llm_provider() == "codex":
        from services.codex_llm import CODEX_BASE_URL
        return CODEX_BASE_URL
    if get_llm_provider() == "ollama":
        return (os.getenv("LLM_BASE_URL") or OLLAMA_OPENAI_BASE_URL).strip().rstrip("/")
    return (os.getenv("GEMINI_BASE_URL") or GEMINI_OPENAI_BASE_URL).strip().rstrip("/")


def get_llm_chat_url() -> str:
    base_url = get_llm_base_url()
    if base_url.endswith("/chat/completions"):
        return base_url
    return urljoin(f"{base_url}/", "chat/completions")


def get_llm_timeout(default_seconds: float) -> float:
    """Allow CPU inference time without changing hosted-provider defaults."""
    if get_llm_provider() == "codex":
        return max(default_seconds, float(os.getenv("CODEX_TIMEOUT_SECONDS") or "120"))
    if get_llm_provider() != "ollama":
        return default_seconds
    return max(default_seconds, float(os.getenv("OLLAMA_TIMEOUT_SECONDS") or "300"))


def get_llm_api_key() -> str:
    if get_llm_provider() in {"ollama", "codex"}:
        return ""
    return os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY") or ""


def get_llm_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    api_key = get_llm_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def llm_is_configured() -> bool:
    return get_llm_provider() in {"ollama", "codex"} or bool(get_llm_api_key())


def llm_missing_message() -> str:
    if get_llm_provider() == "codex":
        return "Verificá Codex CLI y su sesión de ChatGPT con codex login status."
    if get_llm_provider() == "ollama":
        return f"Verifica que Ollama este ejecutandose en {get_llm_base_url()} con el modelo {get_llm_model()}."
    return "GEMINI_API_KEY/LLM_API_KEY no esta configurada."


def llm_payload(payload: dict) -> dict:
    updated = dict(payload)
    updated["model"] = payload.get("model") or get_llm_model()
    if get_llm_provider() == "ollama":
        # Local Llama models do not support the Gemini thinking parameter.
        updated.pop("reasoning_effort", None)
    return updated


def llm_client(**kwargs):
    """Route Codex requests over stdio; other URLs retain normal HTTP transport."""
    if get_llm_provider() == "codex":
        from services.codex_llm import CodexTransport
        kwargs.update(transport=CodexTransport(), trust_env=False)
    return httpx.AsyncClient(**kwargs)
