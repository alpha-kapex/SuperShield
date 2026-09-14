from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import run_demo

from supershield.models import ApprovalAction
from supershield.tools.approval import ApprovalError, ApprovalTokenService


def test_approval_is_bound_to_payload_session_and_single_use(client) -> None:
    case, run = run_demo(client, "clean-bloom-cycle")
    checkpoint = next(
        item for item in run["packet"]["checkpoints"] if item["action"] == "EXPORT_REPORT"
    )
    payload = {
        "caseId": case["caseId"],
        "runId": run["runId"],
        "packetRevision": run["packet"]["revision"],
        "format": "json",
    }
    request = {
        "checkpointId": checkpoint["checkpointId"],
        "token": checkpoint["token"],
        "sessionId": "pytest-session-001",
        "action": "EXPORT_REPORT",
        "payload": {**payload, "format": "pdf"},
        "approve": True,
    }
    assert client.post(f"/runs/{run['runId']}/approvals", json=request).status_code == 403

    request["payload"] = payload
    approved = client.post(f"/runs/{run['runId']}/approvals", json=request)
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    replay = client.post(f"/runs/{run['runId']}/approvals", json=request)
    assert replay.status_code == 403


def test_wrong_session_cannot_approve(client) -> None:
    _, run = run_demo(client, "clean-bloom-cycle")
    checkpoint = next(
        item for item in run["packet"]["checkpoints"] if item["action"] == "EXPORT_REPORT"
    )
    payload = {
        "caseId": run["caseId"],
        "runId": run["runId"],
        "packetRevision": run["packet"]["revision"],
        "format": "json",
    }
    response = client.post(
        f"/runs/{run['runId']}/approvals",
        json={
            "checkpointId": checkpoint["checkpointId"],
            "token": checkpoint["token"],
            "sessionId": "another-session-999",
            "action": "EXPORT_REPORT",
            "payload": payload,
            "approve": True,
        },
    )
    assert response.status_code == 403

def test_token_rejects_cross_case_use_and_expiry() -> None:
    service = ApprovalTokenService(
        "unit-test-secret-at-least-thirty-two-bytes",  # pragma: allowlist secret
        ttl_seconds=30,
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    payload = {"format": "json"}
    checkpoint = service.issue(
        action=ApprovalAction.EXPORT_REPORT,
        payload=payload,
        case_id="case-a",
        run_id="run-a",
        session_id="session-a",
        description="Test export",
        now=now,
    )
    with pytest.raises(ApprovalError, match="not bound"):
        service.verify_and_consume(
            checkpoint.token or "",
            action=ApprovalAction.EXPORT_REPORT,
            payload=payload,
            case_id="case-b",
            run_id="run-a",
            session_id="session-a",
            checkpoint_id=checkpoint.checkpoint_id,
            now=now,
        )
    with pytest.raises(ApprovalError, match="expired"):
        service.verify_and_consume(
            checkpoint.token or "",
            action=ApprovalAction.EXPORT_REPORT,
            payload=payload,
            case_id="case-a",
            run_id="run-a",
            session_id="session-a",
            checkpoint_id=checkpoint.checkpoint_id,
            now=now + timedelta(seconds=31),
        )
