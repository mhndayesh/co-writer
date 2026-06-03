import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import AppError

log = logging.getLogger("gink.security")


def _truncate(pw: str) -> bytes:
    # bcrypt has a hard 72-byte limit. Truncating is the standard workaround.
    return pw.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_truncate(password), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_truncate(password), password_hash.encode())
    except Exception:
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, *, token_version: int = 0, extra: dict[str, Any] | None = None) -> str:
    s = get_settings()
    payload = {
        "sub": user_id,
        "type": "access",
        "tv": token_version,  # session epoch — checked against users.token_version
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(minutes=s.access_token_ttl_minutes)).timestamp()),
        **(extra or {}),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def create_refresh_token(user_id: str, *, jti: str) -> str:
    s = get_settings()
    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": jti,  # server-side row id (refresh_tokens) — enables rotation/revocation
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(days=s.refresh_token_ttl_days)).timestamp()),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])


# ── Clerk session-token verification ──────────────────────────────────────────
# Clerk signs session JWTs with RS256 and publishes the public keys at a JWKS
# endpoint. PyJWKClient fetches + caches them (per signing-key `kid`), so we
# verify the signature without ever holding a shared secret.

_jwks_client: "jwt.PyJWKClient | None" = None


def _get_jwks_client() -> "jwt.PyJWKClient":
    global _jwks_client
    if _jwks_client is None:
        url = get_settings().clerk_jwks_url
        if not url:
            raise AppError("Clerk is not configured (CLERK_JWKS_URL unset)", status_code=500)
        # cache_keys lets the client reuse fetched keys across calls.
        _jwks_client = jwt.PyJWKClient(url, cache_keys=True)
    return _jwks_client


def verify_clerk_token(token: str) -> dict[str, Any]:
    """Verify a Clerk RS256 session token against the JWKS and return its claims.

    Raises on bad signature / expiry / wrong issuer (caller maps to Unauthorized).
    `verify_aud=False` — Clerk session tokens carry `azp` (authorized party), not
    a standard `aud`, so audience isn't checked here.
    """
    s = get_settings()
    # Fail closed: if Clerk is enabled (JWKS set) but the issuer isn't configured,
    # refuse to verify rather than silently skipping the `iss` check — otherwise a
    # validly-signed token from ANY Clerk tenant would be accepted. Issuer required.
    if not s.clerk_issuer:
        raise AppError("Clerk issuer is not configured (CLERK_ISSUER unset)", status_code=500)
    signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=s.clerk_issuer,
        options={"verify_aud": False, "require": ["exp", "iat", "sub"]},
        # small leeway absorbs minor clock skew between Clerk and this server
        leeway=10,
    )


def _fernet() -> Fernet | None:
    key = get_settings().llm_key_encryption_key
    if not key:
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        log.error("LLM_KEY_ENCRYPTION_KEY is set but not a valid Fernet key")
        return None


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    f = _fernet()
    if f is None:
        # Fail loud rather than silently persisting a third-party API key in
        # plaintext. (validate_secrets() already blocks startup outside
        # development when the key is missing/invalid, so this only fires in a
        # misconfigured dev box — where it's a clear, actionable error.)
        raise AppError(
            "Server cannot securely store API keys: LLM_KEY_ENCRYPTION_KEY is "
            "missing or invalid. Set a valid Fernet key and retry.",
            status_code=500,
        )
    return f.encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    f = _fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # The stored ciphertext can't be decrypted with the current key — almost
        # always a key rotation / env mismatch / restored DB. Surface it in logs
        # so it isn't misdiagnosed as "user never added a key". Return "" so the
        # caller's BYOK guard prompts a re-entry.
        log.warning(
            "Stored secret failed to decrypt (LLM_KEY_ENCRYPTION_KEY rotation or "
            "environment mismatch). The user must re-enter their API key."
        )
        return ""
