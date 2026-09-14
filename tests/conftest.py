from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from supershield.api import create_app
from supershield.settings import Settings
from supershield.storage import InMemoryStateStore

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPOSITORY_ROOT / "fixtures"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        approval_secret="test-approval-secret-that-is-at-least-32-characters",  # pragma: allowlist secret
        fixture_root=FIXTURE_ROOT,
        cors_origins=["http://localhost:5173"],
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings, store=InMemoryStateStore()))


def run_demo(client: TestClient, demo_case_id: str, session_id: str = "pytest-session-001") -> tuple[dict, dict]:
    created = client.post("/cases", json={"demoCaseId": demo_case_id})
    assert created.status_code == 201, created.text
    case = created.json()
    started = client.post(
        f"/cases/{case['caseId']}/runs",
        json={"sessionId": session_id},
    )
    assert started.status_code == 201, started.text
    return case, started.json()
