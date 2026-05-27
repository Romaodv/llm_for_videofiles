import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from backend.app.config import settings

PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_GROQ = "groq"


def save_secret(provider: str, secret: str) -> dict:
    normalized = secret.strip()
    if not normalized:
        raise ValueError("API key vazia")

    payload = read_payload()
    encrypted = get_fernet().encrypt(normalized.encode("utf-8")).decode("utf-8")
    payload[provider] = {
        "encrypted": encrypted,
        "masked": mask_secret(normalized),
    }
    write_payload(payload)
    return secret_status(provider)


def get_secret(provider: str) -> str | None:
    payload = read_payload()
    item = payload.get(provider)
    if not item:
        return None
    encrypted = item.get("encrypted")
    if not encrypted:
        return None
    try:
        return get_fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def delete_secret(provider: str) -> dict:
    payload = read_payload()
    payload.pop(provider, None)
    write_payload(payload)
    return secret_status(provider)


def secret_status(provider: str) -> dict:
    payload = read_payload()
    item = payload.get(provider)
    return {
        "provider": provider,
        "configured": bool(item),
        "masked": item.get("masked") if item else None,
        "storage": str(settings.secrets_path),
    }


def get_fernet() -> Fernet:
    settings.ensure_dirs()
    key_path = settings.secret_key_path
    if key_path.exists():
        key = key_path.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        key_path.write_bytes(key + b"\n")
        chmod_owner_only(key_path)
    return Fernet(key)


def read_payload() -> dict:
    if not settings.secrets_path.exists():
        return {}
    try:
        return json.loads(settings.secrets_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_payload(payload: dict) -> None:
    settings.ensure_dirs()
    settings.secrets_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    chmod_owner_only(settings.secrets_path)


def chmod_owner_only(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}{'*' * max(4, len(secret) - 8)}{secret[-4:]}"
