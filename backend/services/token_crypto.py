import base64
import hashlib
import hmac
import json
import os
import secrets
from typing import Any


def _secret() -> bytes:
    key = os.getenv("POWERBI_TOKEN_ENCRYPTION_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_JWT_SECRET", "")
    if not key:
        raise RuntimeError("No hay secreto disponible para cifrar tokens de Power BI")
    return key.encode("utf-8")


def _fernet():
    key = os.getenv("POWERBI_TOKEN_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("POWERBI_TOKEN_ENCRYPTION_KEY no esta configurado")
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise RuntimeError("Fernet no esta disponible para cifrar tokens de Power BI") from exc


def _xor_bytes(data: bytes, key_stream: bytes) -> bytes:
    return bytes(byte ^ key_stream[idx] for idx, byte in enumerate(data))


def _stream(secret: bytes, nonce: bytes, size: int) -> bytes:
    chunks = []
    counter = 0
    while sum(len(chunk) for chunk in chunks) < size:
        counter_bytes = counter.to_bytes(4, "big")
        chunks.append(hmac.new(secret, nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return b"".join(chunks)[:size]


def _seal_stdlib(payload: bytes) -> dict[str, str]:
    secret = _secret()
    nonce = secrets.token_bytes(16)
    key_stream = _stream(secret, nonce, len(payload))
    ciphertext = _xor_bytes(payload, key_stream)
    tag = hmac.new(secret, nonce + ciphertext, hashlib.sha256).digest()
    return {
        "scheme": "hmac-stream:v1",
        "nonce": base64.urlsafe_b64encode(nonce).decode("utf-8"),
        "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("utf-8"),
        "tag": base64.urlsafe_b64encode(tag).decode("utf-8"),
    }


def _unseal_stdlib(envelope: dict[str, Any]) -> bytes:
    secret = _secret()
    nonce = base64.urlsafe_b64decode(str(envelope.get("nonce") or "").encode("utf-8"))
    ciphertext = base64.urlsafe_b64decode(str(envelope.get("ciphertext") or "").encode("utf-8"))
    tag = base64.urlsafe_b64decode(str(envelope.get("tag") or "").encode("utf-8"))
    expected = hmac.new(secret, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise RuntimeError("Secreto de Power BI invalido o alterado")
    key_stream = _stream(secret, nonce, len(ciphertext))
    return _xor_bytes(ciphertext, key_stream)


def seal_json(payload: dict[str, Any]) -> dict[str, str]:
    plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        ciphertext = _fernet().encrypt(plaintext).decode("utf-8")
        return {"scheme": "fernet:v1", "ciphertext": ciphertext}
    except RuntimeError:
        return _seal_stdlib(plaintext)


def unseal_json(envelope: dict[str, Any]) -> dict[str, Any]:
    if envelope.get("scheme") == "fernet:v1":
        ciphertext = str(envelope.get("ciphertext") or "").encode("utf-8")
        if not ciphertext:
            raise RuntimeError("Secreto vacio")
        plaintext = _fernet().decrypt(ciphertext)
    elif envelope.get("scheme") == "hmac-stream:v1":
        plaintext = _unseal_stdlib(envelope)
    else:
        raise RuntimeError("Formato de secreto no soportado")
    return json.loads(plaintext.decode("utf-8"))
