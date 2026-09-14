"""HMAC-bound, short-lived approval challenges.

An approval is valid only for one action, canonical payload, case, run,
checkpoint, user session, and expiry window. Tokens are single-use.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import uuid4

from supershield.models import ApprovalAction, HumanCheckpoint, utc_now


class ApprovalError(ValueError):
    """Raised when an approval challenge is invalid or no longer usable."""


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    raise TypeError(f"Unsupported payload value: {type(value).__name__}")


def canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    ).encode("utf-8")


def payload_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except Exception as exc:  # binascii differs across Python versions
        raise ApprovalError("Malformed approval token") from exc


class ApprovalTokenService:
    def __init__(self, secret: str | bytes, *, ttl_seconds: int = 600) -> None:
        secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
        if len(secret_bytes) < 32:
            raise ValueError("approval secret must contain at least 32 bytes")
        if not 30 <= ttl_seconds <= 3_600:
            raise ValueError("approval token TTL must be between 30 and 3600 seconds")
        self._secret = secret_bytes
        self._ttl = ttl_seconds
        self._consumed: set[str] = set()
        self._lock = threading.RLock()

    def issue(
        self,
        *,
        action: ApprovalAction,
        payload: Any,
        case_id: str,
        run_id: str,
        session_id: str,
        description: str,
        now: datetime | None = None,
    ) -> HumanCheckpoint:
        issued = (now or utc_now()).astimezone(UTC)
        expiry = issued + timedelta(seconds=self._ttl)
        checkpoint_id = f"checkpoint_{uuid4().hex}"
        claims = {
            "v": 1,
            "jti": uuid4().hex,
            "checkpoint_id": checkpoint_id,
            "action": action.value,
            "payload_hash": payload_hash(payload),
            "case_id": case_id,
            "run_id": run_id,
            "session_id": session_id,
            "iat": int(issued.timestamp()),
            "exp": int(expiry.timestamp()),
        }
        encoded_claims = _encode(canonical_json(claims))
        signature = _encode(
            hmac.new(self._secret, encoded_claims.encode("ascii"), hashlib.sha256).digest()
        )
        return HumanCheckpoint(
            checkpoint_id=checkpoint_id,
            action=action,
            description=description,
            payload_hash=claims["payload_hash"],
            session_id=session_id,
            expires_at=expiry,
            token=f"{encoded_claims}.{signature}",
        )

    def verify_and_consume(
        self,
        token: str,
        *,
        action: ApprovalAction,
        payload: Any,
        case_id: str,
        run_id: str,
        session_id: str,
        checkpoint_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        try:
            encoded_claims, supplied_signature = token.split(".", 1)
        except ValueError as exc:
            raise ApprovalError("Malformed approval token") from exc
        expected_signature = _encode(
            hmac.new(self._secret, encoded_claims.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ApprovalError("Invalid approval token")
        try:
            claims = json.loads(_decode(encoded_claims))
        except (json.JSONDecodeError, UnicodeDecodeError, ApprovalError) as exc:
            raise ApprovalError("Malformed approval token") from exc
        required = {
            "v",
            "jti",
            "checkpoint_id",
            "action",
            "payload_hash",
            "case_id",
            "run_id",
            "session_id",
            "iat",
            "exp",
        }
        if set(claims) != required or claims.get("v") != 1:
            raise ApprovalError("Unsupported approval token")
        timestamp = int((now or utc_now()).astimezone(UTC).timestamp())
        if not isinstance(claims["iat"], int) or not isinstance(claims["exp"], int):
            raise ApprovalError("Malformed approval token")
        if claims["iat"] > timestamp + 30 or claims["exp"] <= timestamp:
            raise ApprovalError("Approval token has expired or is not yet valid")
        expected = {
            "checkpoint_id": checkpoint_id,
            "action": action.value,
            "payload_hash": payload_hash(payload),
            "case_id": case_id,
            "run_id": run_id,
            "session_id": session_id,
        }
        if any(not hmac.compare_digest(str(claims[key]), str(value)) for key, value in expected.items()):
            raise ApprovalError("Approval token is not bound to this request")
        jti = str(claims["jti"])
        with self._lock:
            if jti in self._consumed:
                raise ApprovalError("Approval token has already been used")
            self._consumed.add(jti)
        return claims
