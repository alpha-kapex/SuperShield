from __future__ import annotations

import pytest
from conftest import run_demo


@pytest.mark.parametrize(
    ("fixture_id", "document_id"),
    [
        ("adversarial-copper-kite", "kite-market"),
        ("adversarial-quiet-quill", "quill-addendum"),
    ],
)
def test_document_instructions_are_quarantined(client, fixture_id: str, document_id: str) -> None:
    _, run = run_demo(client, fixture_id)
    packet = run["packet"]
    findings = [
        finding
        for finding in packet["riskFindings"]
        if finding["category"] == "prompt_injection"
    ]
    assert findings
    assert any(
        reference["documentId"] == document_id
        for finding in findings
        for reference in finding["evidence"]
    )
    assert packet["decisionState"] == "READY_FOR_EXPERT_REVIEW"
    assert {event.tool for event in client.app.state.services.store.list_events(run["runId"])} <= {
        "supervisor",
        "strands",
        "evidence_collector",
        "skeptic",
        "deterministic_finance",
        "location_risk",
        "evidence_validator",
        "approval",
        "human_approval",
        "evidence_ingest",
    }
