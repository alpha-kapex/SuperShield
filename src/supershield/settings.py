"""Environment configuration without import-time AWS or filesystem side effects."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from supershield.models import ShieldModel


class Settings(ShieldModel):
    app_name: str = "SuperShield"
    environment: str = "development"
    execution_mode: Literal["local", "strands"] = "local"
    storage_backend: Literal["memory", "dynamodb"] = "memory"
    public_demo: bool = False
    allow_inline_documents: bool = True
    case_ttl_seconds: int = Field(default=86_400, ge=300, le=604_800)
    approval_ttl_seconds: int = Field(default=600, ge=30, le=3_600)
    approval_secret: str = Field(min_length=32, repr=False)
    approval_secret_ephemeral: bool = False
    max_documents_per_case: int = Field(default=12, ge=1, le=50)
    max_document_bytes: int = Field(default=250_000, ge=1_000, le=2_000_000)
    fixture_root: Path
    aws_region: str = "us-east-1"
    dynamodb_table: str = "supershield-state"
    s3_bucket: str | None = None
    s3_kms_key_id: str | None = None
    bedrock_model_id: str = "amazon.nova-pro-v1:0"
    bedrock_extraction_model_id: str = "amazon.nova-lite-v1:0"
    strands_provider: Literal["bedrock", "ollama"] = "bedrock"
    ollama_model: str = "qwen3:0.6b"
    ollama_host: str = "http://localhost:11434"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("fixture_root")
    @classmethod
    def fixture_root_is_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("fixture_root must be absolute")
        return value

    @classmethod
    def from_env(cls) -> Settings:
        source_root = Path(__file__).resolve().parents[2]
        working_root = Path.cwd().resolve()
        default_fixture_root = (
            working_root / "fixtures"
            if (working_root / "fixtures").is_dir()
            else source_root / "fixtures"
        )
        configured_fixture_root = Path(
            os.getenv("SUPERSHIELD_FIXTURE_ROOT", str(default_fixture_root))
        ).resolve()
        # Permit packaged/container fixtures under the process working directory,
        # while refusing arbitrary paths outside the application roots.
        allowed_roots = (working_root, source_root)
        if not any(configured_fixture_root.is_relative_to(root) for root in allowed_roots):
            configured_fixture_root = default_fixture_root
        secret = os.getenv("SUPERSHIELD_APPROVAL_SECRET") or os.getenv(
            "SUPERSHIELD_SESSION_SECRET"
        )
        ephemeral = not bool(secret)
        if not secret:
            secret = secrets.token_urlsafe(48)
        public_demo = _bool("SUPERSHIELD_PUBLIC_DEMO", False)
        origins_value = os.getenv(
            "SUPERSHIELD_CORS_ORIGINS",
            os.getenv("SUPERSHIELD_ALLOWED_ORIGINS", "http://localhost:5173"),
        )
        origins = [
            item.strip()
            for item in origins_value.split(",")
            if item.strip()
        ]
        ttl_seconds = (
            _int("SUPERSHIELD_CASE_TTL_SECONDS", 86_400)
            if os.getenv("SUPERSHIELD_CASE_TTL_SECONDS") is not None
            else _int("SUPERSHIELD_CASE_TTL_HOURS", 24) * 3_600
        )
        return cls(
            environment=os.getenv("SUPERSHIELD_ENVIRONMENT", "development"),
            execution_mode=_choice(
                (
                    "SUPERSHIELD_MODE"
                    if os.getenv("SUPERSHIELD_MODE") is not None
                    else "SUPERSHIELD_RUNTIME_MODE"
                ),
                {"local", "strands"},
                "local",
            ),
            storage_backend=_choice(
                "SUPERSHIELD_STORAGE_BACKEND", {"memory", "dynamodb"}, "memory"
            ),
            public_demo=public_demo,
            allow_inline_documents=_bool(
                "SUPERSHIELD_ALLOW_INLINE_DOCUMENTS", not public_demo
            ),
            case_ttl_seconds=ttl_seconds,
            approval_ttl_seconds=_int("SUPERSHIELD_APPROVAL_TTL_SECONDS", 600),
            approval_secret=secret,
            approval_secret_ephemeral=ephemeral,
            max_documents_per_case=_int("SUPERSHIELD_MAX_DOCUMENTS", 12),
            max_document_bytes=_int("SUPERSHIELD_MAX_DOCUMENT_BYTES", 250_000),
            fixture_root=configured_fixture_root,
            aws_region=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
            dynamodb_table=os.getenv(
                "SUPERSHIELD_DYNAMODB_TABLE",
                os.getenv("SUPERSHIELD_CASES_TABLE", "supershield-state"),
            ),
            s3_bucket=(
                os.getenv("SUPERSHIELD_S3_BUCKET")
                or os.getenv("SUPERSHIELD_EVIDENCE_BUCKET")
                or None
            ),
            s3_kms_key_id=(
                os.getenv("SUPERSHIELD_S3_KMS_KEY_ID")
                or os.getenv("SUPERSHIELD_KMS_KEY_ARN")
                or None
            ),
            bedrock_model_id=os.getenv(
                "SUPERSHIELD_BEDROCK_MODEL_ID",
                os.getenv("BEDROCK_PRIMARY_MODEL_ID", "amazon.nova-pro-v1:0"),
            ),
            bedrock_extraction_model_id=os.getenv(
                "SUPERSHIELD_BEDROCK_EXTRACTION_MODEL_ID",
                os.getenv("BEDROCK_EXTRACTION_MODEL_ID", "amazon.nova-lite-v1:0"),
            ),
            strands_provider=_choice(
                "SUPERSHIELD_STRANDS_PROVIDER", {"bedrock", "ollama"}, "bedrock"
            ),
            ollama_model=os.getenv("SUPERSHIELD_OLLAMA_MODEL", "qwen3:0.6b"),
            ollama_host=os.getenv("SUPERSHIELD_OLLAMA_HOST", "http://localhost:11434"),
            cors_origins=origins,
        )


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw is not None else default


def _choice(name: str, choices: set[str], default: str) -> str:
    value = os.getenv(name, default).strip().lower()
    return value if value in choices else default
