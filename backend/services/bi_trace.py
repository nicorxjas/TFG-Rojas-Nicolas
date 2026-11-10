"""Local, opt-in replay snapshots; never credentials or hidden reasoning."""
import contextvars
import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from services.bi_contracts import CONTRACT_VERSION

_active = contextvars.ContextVar("bi_trace", default=None)
SENSITIVE = {"authorization", "api_key", "access_token", "refresh_token", "password", "secret",
             "supabase_service_role_key", "user_id", "owner_user_id"}


def safe_snapshot(value):
    if isinstance(value, dict):
        return {str(key): safe_snapshot(item) for key, item in value.items()
                if str(key).lower() not in SENSITIVE}
    if isinstance(value, (list, tuple, set)):
        return [safe_snapshot(item) for item in value]
    return value


def record(event, payload):
    trace = _active.get()
    if trace is not None:
        trace["events"].append({"event": event, "elapsed_ms": round((time.monotonic()-trace["started"])*1000),
                                "payload": safe_snapshot(payload)})


@contextmanager
def trace_run(operation, request):
    if _active.get() is not None:
        record(operation, request)
        yield _active.get()
        return
    trace = {"trace_id": uuid.uuid4().hex, "contract_version": CONTRACT_VERSION,
             "operation": operation, "request": safe_snapshot(request), "events": [], "started": time.monotonic()}
    token = _active.set(trace)
    try:
        yield trace
    except BaseException as exc:
        record("failure", {"type": type(exc).__name__})
        raise
    finally:
        trace["duration_ms"] = round((time.monotonic()-trace.pop("started"))*1000)
        _active.reset(token)
        # The complete snapshot can contain business data. Persistence is an
        # explicit deployment setting; evaluation enables it in its own folder.
        destination = os.getenv("BI_TRACE_DIR")
        if destination:
            try:
                folder = Path(destination).resolve()
                folder.mkdir(parents=True, exist_ok=True)
                content = json.dumps(trace, ensure_ascii=False, default=str)
                trace["snapshot_sha256"] = hashlib.sha256(content.encode()).hexdigest()
                (folder / f"{trace['trace_id']}.json").write_text(
                    json.dumps(trace, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            except OSError:
                pass  # Observability must not turn a valid answer into failure.
