from __future__ import annotations

import json

import pytest
from conftest import FIXTURE_ROOT, run_demo

FIXTURE_IDS = sorted(path.name for path in FIXTURE_ROOT.iterdir() if path.is_dir())


@pytest.mark.parametrize("fixture_id", FIXTURE_IDS)
def test_curated_fixture_reaches_expected_decision_state(client, fixture_id: str) -> None:
    expected = json.loads((FIXTURE_ROOT / fixture_id / "expected.json").read_text(encoding="utf-8"))
    _, run = run_demo(client, fixture_id, session_id=f"pytest-{fixture_id}")

    packet = run["packet"]
    assert packet["decisionState"] == expected["decision_state"]
    assert packet["validation"]["valid"] is True
    assert run["status"] in {"COMPLETED", "WAITING_FOR_EVIDENCE"}
    assert all(
        finding["evidence"] or finding["unresolved"]
        for finding in packet["riskFindings"]
        if finding["material"]
    )


def test_flagship_financials_are_deterministic(client) -> None:
    _, run = run_demo(client, "priya-saffron-route")
    packet = run["packet"]
    base = next(item for item in packet["financialScenarios"] if item["name"] == "base")

    assert base["investmentRequired"] == 205000.0
    assert base["monthlyPercentageFees"] == 7200.0
    assert base["monthlyFixedAndRecurringCosts"] == 33350.0
    assert base["monthlyOperatingProfit"] == 1450.0
    assert base["monthlyHouseholdIncomeGap"] == 4550.0
    assert base["breakEvenMonthlyRevenue"] == 57500.0
    assert base["cashAfterInvestment"] == 30000.0
    assert len(packet["missingEvidence"]) == 1
    assert "landlord's signed consent" in packet["missingEvidence"][0]
