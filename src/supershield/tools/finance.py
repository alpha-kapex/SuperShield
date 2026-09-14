"""Auditable financial calculations.

All arithmetic uses ``Decimal`` and standard formulae.  No model performs or
edits these calculations.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from supershield.models import (
    CaseInput,
    DocumentKind,
    ExtractedClaim,
    FinancialAssumptions,
    FinancialImpact,
    FinancialScenario,
    FindingCategory,
    RiskFinding,
    Severity,
)
from supershield.tools.evidence import facts_by_topic

CENT = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")
SOURCE_WEIGHT = {
    DocumentKind.DISCLOSURE: 6,
    DocumentKind.LEASE: 6,
    DocumentKind.FINANCIAL: 5,
    DocumentKind.LOCATION: 4,
    DocumentKind.CORRESPONDENCE: 3,
    DocumentKind.OTHER: 2,
    DocumentKind.BROCHURE: 1,
}

FIELD_BY_TOPIC = {
    "projected_monthly_revenue": "projected_monthly_revenue",
    "annual_revenue": "projected_monthly_revenue",
    "initial_fee": "initial_fee",
    "buildout_cost": "buildout_cost",
    "equipment_cost": "equipment_cost",
    "opening_inventory": "opening_inventory",
    "working_capital": "working_capital",
    "gross_margin_rate": "gross_margin_rate",
    "royalty_rate": "royalty_rate",
    "marketing_rate": "marketing_rate",
    "other_revenue_fee_rate": "other_revenue_fee_rate",
    "recurring_monthly_fees": "recurring_monthly_fees",
    "fixed_monthly_costs": "fixed_monthly_costs",
    "lease_monthly_cost": "lease_monthly_cost",
    "lease_escalation_rate": "lease_escalation_rate",
    "personal_guarantee_months": "personal_guarantee_months",
}


@dataclass(slots=True)
class FinanceResult:
    assumptions: FinancialAssumptions
    scenarios: list[FinancialScenario] = field(default_factory=list)
    findings: list[RiskFinding] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def ratio(value: Decimal) -> Decimal:
    return value.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def assumptions_from_claims(claims: list[ExtractedClaim]) -> FinancialAssumptions:
    """Choose the highest-authority cited value for each financial field."""

    values: dict[str, object] = {}
    source_evidence = []
    topics = facts_by_topic(claims)
    for topic, field_name in FIELD_BY_TOPIC.items():
        candidates = [
            claim
            for claim in topics.get(topic, [])
            if isinstance(claim.normalized_value, Decimal)
        ]
        if not candidates:
            continue
        candidate = max(candidates, key=lambda item: SOURCE_WEIGHT[item.evidence.document_kind])
        if field_name == "personal_guarantee_months":
            values[field_name] = max(0, int(candidate.normalized_value))
        elif field_name not in values or topic != "annual_revenue":
            values[field_name] = candidate.normalized_value
        source_evidence.append(candidate.evidence)

    # A disclosed total investment is useful when no component breakdown exists.
    startup_fields = {
        "initial_fee",
        "buildout_cost",
        "equipment_cost",
        "opening_inventory",
        "working_capital",
        "other_startup_costs",
    }
    if not startup_fields.intersection(values):
        totals = [
            claim
            for claim in topics.get("investment_range", [])
            if isinstance(claim.normalized_value, Decimal)
        ]
        if totals:
            total = max(totals, key=lambda item: SOURCE_WEIGHT[item.evidence.document_kind])
            values["other_startup_costs"] = total.normalized_value
            source_evidence.append(total.evidence)

    unresolved: list[str] = []
    if Decimal(values.get("projected_monthly_revenue", 0)) <= 0:
        unresolved.append("projected_monthly_revenue")
    if not startup_fields.intersection(values):
        unresolved.append("startup_investment")
    if not {"gross_margin_rate"}.intersection(values):
        unresolved.append("gross_margin_rate")
    if not {
        "fixed_monthly_costs",
        "lease_monthly_cost",
        "recurring_monthly_fees",
        "royalty_rate",
        "marketing_rate",
    }.intersection(values):
        unresolved.append("operating_costs_and_fees")

    # De-duplicate evidence by stable citation coordinates.
    unique_evidence = {
        (item.document_id, item.page, item.excerpt): item for item in source_evidence
    }
    values["source_evidence"] = list(unique_evidence.values())
    values["unresolved_fields"] = unresolved
    return FinancialAssumptions(**values)


def seeded_revenue_factors(seed: int = 17, samples: int = 2_000) -> list[Decimal]:
    """Return a reproducible bounded sample for downside sensitivity analysis."""

    if samples < 10:
        raise ValueError("samples must be at least 10")
    generator = random.Random(seed)
    return [
        ratio(Decimal(str(min(Decimal("1.20"), max(Decimal("0.45"), Decimal(str(generator.gauss(0.84, 0.12))))))))
        for _ in range(samples)
    ]


def _percentile(values: list[Decimal], percentile: Decimal) -> Decimal:
    ordered = sorted(values)
    index = int((len(ordered) - 1) * percentile)
    return ordered[index]


def investment_required(assumptions: FinancialAssumptions) -> Decimal:
    return money(
        assumptions.initial_fee
        + assumptions.buildout_cost
        + assumptions.equipment_cost
        + assumptions.opening_inventory
        + assumptions.working_capital
        + assumptions.other_startup_costs
    )


def guarantee_exposure(assumptions: FinancialAssumptions) -> Decimal:
    """Sum guaranteed lease payments with annual contractual escalation."""

    exposure = Decimal("0")
    for month in range(assumptions.personal_guarantee_months):
        year = month // 12
        exposure += assumptions.lease_monthly_cost * (
            Decimal("1") + assumptions.lease_escalation_rate
        ) ** year
    return money(exposure)


def calculate_scenario(
    case_input: CaseInput,
    assumptions: FinancialAssumptions,
    *,
    name: str,
    revenue_factor: Decimal,
) -> FinancialScenario:
    revenue = money(assumptions.projected_monthly_revenue * revenue_factor)
    total_investment = investment_required(assumptions)
    investable_cash = (
        case_input.cash_available - case_input.emergency_reserve
        if case_input.cash_available is not None
        else case_input.maximum_investment
    )
    percentage_rate = (
        assumptions.royalty_rate
        + assumptions.marketing_rate
        + assumptions.other_revenue_fee_rate
    )
    percentage_fees = money(revenue * percentage_rate)
    fixed = money(
        assumptions.fixed_monthly_costs
        + assumptions.lease_monthly_cost
        + assumptions.recurring_monthly_fees
    )
    operating_profit = money(
        revenue * assumptions.gross_margin_rate - percentage_fees - fixed
    )
    income_gap = money(
        max(Decimal("0"), case_input.required_monthly_household_income - operating_profit)
    )
    contribution_margin = assumptions.gross_margin_rate - percentage_rate
    break_even = (
        money(fixed / contribution_margin)
        if contribution_margin > 0
        else None
    )
    runway = (
        (case_input.emergency_reserve / income_gap).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if income_gap > 0
        else None
    )
    return FinancialScenario(
        name=name,
        revenue_factor=ratio(revenue_factor),
        monthly_revenue=revenue,
        investment_required=total_investment,
        cash_after_investment=money(investable_cash - total_investment),
        monthly_percentage_fees=percentage_fees,
        monthly_fixed_and_recurring_costs=fixed,
        monthly_operating_profit=operating_profit,
        monthly_household_income_gap=income_gap,
        break_even_monthly_revenue=break_even,
        runway_months=runway,
        guarantee_exposure=guarantee_exposure(assumptions),
        formulae={
            "investmentRequired": "initial fee + build-out + equipment + opening inventory + working capital + other startup costs",
            "monthlyPercentageFees": "monthly revenue × (royalty rate + marketing rate + other revenue fee rate)",
            "monthlyOperatingProfit": "monthly revenue × gross margin - percentage fees - fixed, lease, and recurring costs",
            "breakEvenMonthlyRevenue": "fixed, lease, and recurring costs ÷ contribution margin",
            "runwayMonths": "emergency reserve ÷ monthly household income gap",
            "guaranteeExposure": "sum of guaranteed monthly lease payments after annual escalation",
        },
        evidence=assumptions.source_evidence,
    )


def _financial_findings(
    case_input: CaseInput,
    assumptions: FinancialAssumptions,
    scenarios: list[FinancialScenario],
) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    base = next(item for item in scenarios if item.name == "base")
    downside = next(item for item in scenarios if item.name == "downside_20_percent")
    if base.investment_required > case_input.maximum_investment:
        shortfall = base.investment_required - case_input.maximum_investment
        findings.append(
            RiskFinding(
                category=FindingCategory.FINANCIAL,
                title="Investment requirement exceeds the stated ceiling",
                description=(
                    "The cited startup amounts total more than the maximum investment constraint."
                ),
                severity=Severity.CRITICAL,
                material=True,
                evidence=assumptions.source_evidence,
                financial_impact=FinancialImpact(
                    amount=money(shortfall),
                    period="one_time",
                    description="Amount above the maximum investment constraint.",
                    formula="investment required - maximum investment",
                ),
            )
        )
    if downside.monthly_household_income_gap > 0:
        material_gap = downside.monthly_household_income_gap >= max(
            Decimal("3000"),
            case_input.required_monthly_household_income * Decimal("0.50"),
        )
        findings.append(
            RiskFinding(
                category=FindingCategory.FINANCIAL,
                title="Downside case does not meet the household income requirement",
                description=(
                    "At twenty percent below the cited revenue projection, calculated operating "
                    "profit is below the required monthly household income."
                ),
                severity=Severity.HIGH if material_gap else Severity.MEDIUM,
                material=material_gap,
                evidence=assumptions.source_evidence,
                financial_impact=FinancialImpact(
                    amount=downside.monthly_household_income_gap,
                    period="monthly",
                    description="Monthly gap in the twenty-percent downside scenario.",
                    formula="required monthly household income - downside operating profit",
                ),
            )
        )
    if base.guarantee_exposure > 0:
        guarantee_evidence = [
            reference
            for reference in assumptions.source_evidence
            if reference.document_kind == DocumentKind.LEASE
            and "guarant" in reference.excerpt.lower()
        ]
        findings.append(
            RiskFinding(
                category=FindingCategory.LEASE,
                title="Personal lease guarantee creates continuing exposure",
                description=(
                    "The cited guarantee term can leave the human responsible for lease payments "
                    "even if operations stop. Expert lease review is appropriate."
                ),
                severity=Severity.HIGH if assumptions.personal_guarantee_months >= 36 else Severity.MEDIUM,
                material=True,
                evidence=guarantee_evidence or assumptions.source_evidence,
                financial_impact=FinancialImpact(
                    amount=base.guarantee_exposure,
                    period="total_term",
                    description="Nominal lease payments across the cited guarantee term.",
                    formula="sum of monthly lease payments after annual escalation",
                ),
            )
        )
    return findings


def calculate_financial_scenarios(
    case_input: CaseInput,
    claims: list[ExtractedClaim],
    *,
    seed: int = 17,
) -> FinanceResult:
    assumptions = assumptions_from_claims(claims)
    sampled_p10 = _percentile(seeded_revenue_factors(seed), Decimal("0.10"))
    scenario_specs = (
        ("base", Decimal("1.00")),
        ("downside_20_percent", Decimal("0.80")),
        ("severe_downside_40_percent", Decimal("0.60")),
        ("seeded_p10", sampled_p10),
    )
    scenarios = [
        calculate_scenario(
            case_input,
            assumptions,
            name=name,
            revenue_factor=factor,
        )
        for name, factor in scenario_specs
    ]
    missing_labels = {
        "projected_monthly_revenue": "A sourced monthly revenue projection is required.",
        "startup_investment": "A current, itemized startup-investment schedule is required.",
        "gross_margin_rate": "A sourced gross-margin assumption is required.",
        "operating_costs_and_fees": "Current fixed costs and all recurring fee terms are required.",
    }
    missing = [
        missing_labels[field_name] for field_name in assumptions.unresolved_fields
    ]
    findings = _financial_findings(case_input, assumptions, scenarios)
    for field_name, request in zip(assumptions.unresolved_fields, missing, strict=True):
        findings.append(
            RiskFinding(
                category=FindingCategory.MISSING_EVIDENCE,
                title=f"Financial input unresolved: {field_name.replace('_', ' ')}",
                description="A material financial input is absent, so the scenario is provisional.",
                severity=Severity.HIGH,
                material=True,
                unresolved=True,
                requested_evidence=request,
            )
        )
    return FinanceResult(
        assumptions=assumptions,
        scenarios=scenarios,
        findings=findings,
        missing_evidence=missing,
    )
