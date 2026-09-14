from __future__ import annotations

from conftest import FIXTURE_ROOT, run_demo
from fastapi.testclient import TestClient

from supershield.api import create_app
from supershield.settings import Settings
from supershield.storage import InMemoryStateStore


def test_health_demo_lifecycle_and_sse(client) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.headers["content-type"].startswith("application/json")
    assert health.json()["status"] == "ok"

    demos = client.get("/demo-cases")
    assert demos.status_code == 200
    assert len(demos.json()) == 12

    case, run = run_demo(client, "clean-bloom-cycle")
    events = client.get(f"/runs/{run['runId']}/events")
    assert events.status_code == 200
    assert "event: run_event" in events.text
    assert "event: done" in events.text

    packet = client.get(f"/cases/{case['caseId']}/decision-packet")
    assert packet.status_code == 200
    assert packet.json()["caseId"] == case["caseId"]

    deleted = client.delete(f"/cases/{case['caseId']}")
    assert deleted.status_code == 204
    assert client.get(f"/cases/{case['caseId']}/decision-packet").status_code == 404


def test_inline_documents_can_be_disabled() -> None:
    settings = Settings(
        approval_secret="test-approval-secret-that-is-at-least-32-characters",  # pragma: allowlist secret
        fixture_root=FIXTURE_ROOT,
        allow_inline_documents=False,
    )
    client = TestClient(create_app(settings, store=InMemoryStateStore()))
    response = client.post(
        "/cases",
        json={
            "title": "Blocked upload",
            "input": {
                "maximumInvestment": 100000,
                "emergencyReserve": 20000,
                "requiredMonthlyHouseholdIncome": 4000,
                "preferredLocation": "Synthetic district",
            },
            "documents": [
                {
                    "documentId": "inline-doc",
                    "title": "Inline evidence",
                    "kind": "other",
                    "content": "Page 1\nThis upload should be refused by configuration.",
                }
            ],
        },
    )
    assert response.status_code == 403

def test_new_consent_evidence_selectively_reruns_and_unblocks_gap(client) -> None:
    _, run = run_demo(client, "priya-saffron-route")
    response = client.post(
        f"/runs/{run['runId']}/evidence",
        json={
            "sessionId": "pytest-session-001",
            "documents": [
                {
                    "documentId": "signed-landlord-consent",
                    "title": "Signed landlord consent",
                    "kind": "correspondence",
                    "content": (
                        "## Page 1\nThe landlord has signed and granted consent for the "
                        "restaurant use, signage, ventilation work, and assignment."
                    ),
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["packet"]["missingEvidence"] == []
    assert updated["packet"]["decisionState"] == "MATERIAL_RISK_IDENTIFIED"
    assert updated["packet"]["whyThisChanged"]
    assert "calculate_finance" not in updated["affectedTasks"]
