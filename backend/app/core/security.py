"""Password hashing and signed session tokens."""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from functools import cache
from uuid import UUID

_MAX_PASSWORD_LENGTH = 256
_MAX_PASSWORD_HASH_LENGTH = 256
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 3
_SCRYPT_MAXMEM = 64 * 1024 * 1024
_SCRYPT_SALT_BYTES = 16
_SCRYPT_KEY_BYTES = 32
_PASSWORD_SCHEME = "scrypt"
_PASSWORD_VERSION = "v1"

_SESSION_VERSION = 1
_SESSION_SIGNATURE_BYTES = 32
_MAX_SESSION_TOKEN_LENGTH = 512
_MAX_SESSION_PAYLOAD_BYTES = 256
_SESSION_SIGNING_CONTEXT = b"salesluv-session-v1."
_MIN_SESSION_SECRET_BYTES = 32


def hash_password(password: str) -> str:
    """Hash a password without normalizing or trimming it."""
    password_bytes = _password_bytes(password)
    salt = secrets.token_bytes(_SCRYPT_SALT_BYTES)
    digest = _derive_password_key(password_bytes, salt)
    return "$".join(
        (
            _PASSWORD_SCHEME,
            _PASSWORD_VERSION,
            _encode_base64url(salt),
            _encode_base64url(digest),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    """Return whether a password matches a supported encoded hash."""
    if not isinstance(encoded, str) or len(encoded) > _MAX_PASSWORD_HASH_LENGTH:
        return False

    try:
        password_bytes = _password_bytes(password)
        scheme, version, salt_text, digest_text = encoded.split("$")
        if scheme != _PASSWORD_SCHEME or version != _PASSWORD_VERSION:
            return False

        salt = _decode_base64url(salt_text)
        expected = _decode_base64url(digest_text)
        if len(salt) != _SCRYPT_SALT_BYTES or len(expected) != _SCRYPT_KEY_BYTES:
            return False

        actual = _derive_password_key(password_bytes, salt)
    except (TypeError, ValueError, UnicodeError):
        return False

    return secrets.compare_digest(actual, expected)


@cache
def dummy_password_hash() -> str:
    """Return one lazily-created hash for account-enumeration-safe verification."""
    return hash_password(secrets.token_urlsafe(32))


def create_session_token(
    member_id: UUID,
    secret: str | bytes,
    ttl_seconds: int,
    now: int | None = None,
) -> str:
    """Create a compact HMAC-SHA256 signed session token."""
    member_uuid = member_id if isinstance(member_id, UUID) else UUID(str(member_id))
    secret_bytes = _session_secret_bytes(secret)
    current_time = _timestamp(now)
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be a positive integer")

    payload = json.dumps(
        {"v": _SESSION_VERSION, "sub": str(member_uuid), "exp": current_time + ttl_seconds},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    payload_text = _encode_base64url(payload)
    signature = _sign_session_payload(payload_text, secret_bytes)
    return f"{payload_text}.{_encode_base64url(signature)}"


def read_session_token(
    token: str,
    secret: str | bytes,
    now: int | None = None,
) -> UUID | None:
    """Validate a session token and return its member UUID, or None."""
    if not isinstance(token, str) or not 0 < len(token) <= _MAX_SESSION_TOKEN_LENGTH:
        return None

    try:
        secret_bytes = _session_secret_bytes(secret)
        current_time = _timestamp(now)
        payload_text, signature_text = token.split(".")
        signature = _decode_base64url(signature_text)
        if len(signature) != _SESSION_SIGNATURE_BYTES:
            return None

        expected_signature = _sign_session_payload(payload_text, secret_bytes)
        if not hmac.compare_digest(signature, expected_signature):
            return None

        payload_bytes = _decode_base64url(payload_text)
        if len(payload_bytes) > _MAX_SESSION_PAYLOAD_BYTES:
            return None
        payload = json.loads(payload_bytes)
        if not isinstance(payload, dict) or set(payload) != {"v", "sub", "exp"}:
            return None
        if type(payload["v"]) is not int or payload["v"] != _SESSION_VERSION:
            return None
        if type(payload["sub"]) is not str or type(payload["exp"]) is not int:
            return None
        if payload["exp"] <= current_time:
            return None

        member_id = UUID(payload["sub"])
        if str(member_id) != payload["sub"]:
            return None
    except (TypeError, ValueError, UnicodeError, json.JSONDecodeError):
        return None

    return member_id


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str):
        raise TypeError("password must be a string")
    if len(password) > _MAX_PASSWORD_LENGTH:
        raise ValueError(f"password must be at most {_MAX_PASSWORD_LENGTH} characters")
    return password.encode("utf-8")


def _derive_password_key(password: bytes, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password,
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        maxmem=_SCRYPT_MAXMEM,
        dklen=_SCRYPT_KEY_BYTES,
    )


def _sign_session_payload(payload_text: str, secret: bytes) -> bytes:
    message = _SESSION_SIGNING_CONTEXT + payload_text.encode("ascii")
    return hmac.digest(secret, message, "sha256")


def _session_secret_bytes(secret: str | bytes) -> bytes:
    if isinstance(secret, str):
        value = secret.encode("utf-8")
    elif isinstance(secret, bytes):
        value = secret
    else:
        raise TypeError("secret must be a string or bytes")
    if len(value) < _MIN_SESSION_SECRET_BYTES:
        raise ValueError(f"secret must be at least {_MIN_SESSION_SECRET_BYTES} bytes")
    return value


def _timestamp(now: int | None) -> int:
    if now is None:
        return int(time.time())
    if isinstance(now, bool) or not isinstance(now, int):
        raise TypeError("now must be an integer Unix timestamp")
    return now


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str) -> bytes:
    if not value or "=" in value:
        raise ValueError("invalid base64url value")
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid base64url value") from exc
    if _encode_base64url(decoded) != value:
        raise ValueError("non-canonical base64url value")
    return decoded
