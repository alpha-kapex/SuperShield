"""Evidence-bound contradiction and missing-support analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from supershield.models import (
    ClaimAssessment,
    ClaimStatus,
    DocumentKind,
    ExtractedClaim,
    FinancialImpact,
    FindingCategory,
    RiskFinding,
    Severity,
)
from supershield.tools.evidence import facts_by_topic

AUTHORITATIVE_WEIGHT = {
    DocumentKind.DISCLOSURE: 6,
    DocumentKind.LEASE: 6,
    DocumentKind.FINANCIAL: 5,
    DocumentKind.LOCATION: 5,
    DocumentKind.CORRESPONDENCE: 3,
    DocumentKind.OTHER: 2,
    DocumentKind.BROCHURE: 1,
}

TOPIC_LABELS = {
    "projected_monthly_revenue": "monthly revenue projection",
    "annual_revenue": "revenue projection",
    "initial_fee": "initial franchise fee",
    "buildout_cost": "build-out cost",
    "equipment_cost": "equipment cost",
    "opening_inventory": "opening inventory",
    "working_capital": "working capital",
    "gross_margin_rate": "gross margin",
    "royalty_rate": "royalty rate",
    "marketing_rate": "marketing contribution",
    "other_revenue_fee_rate": "revenue-based system fee",
    "recurring_monthly_fees": "recurring monthly fee",
    "lease_escalation_rate": "lease escalation",
    "lease_monthly_cost": "monthly lease cost",
    "personal_guarantee_months": "personal guarantee term",
    "fixed_monthly_costs": "fixed operating costs",
    "break_even": "break-even timeline",
    "protected_territory": "territory protection",
    "investment_range": "total investment",
    "competitor_count": "competitor count",
    "same_brand_units": "same-brand unit count",
    "population": "local population",
    "outlet_survival_rate": "outlet survival rate",
    "earnings_support": "earnings support",
}


@dataclass(slots=True)
class SkepticResult:
    assessments: list[ClaimAssessment] = field(default_factory=list)
    findings: list[RiskFinding] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)


def _weight(claim: ExtractedClaim) -> int:
    return AUTHORITATIVE_WEIGHT[claim.evidence.document_kind]


def _comparable(value: Decimal | str | bool | None) -> Any:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        return " ".join(value.lower().split())
    return value


def _different(left: Any, right: Any, topic: str) -> bool:
    left, right = _comparable(left), _comparable(right)
    if left is None or right is None:
        return left is not right
    if isinstance(left, Decimal) and isinstance(right, Decimal):
        if topic.endswith("_rate"):
            return abs(left - right) > Decimal("0.0001")
        tolerance = max(Decimal("1"), max(abs(left), abs(right)) * Decimal("0.005"))
        return abs(left - right) > tolerance
    return left != right


def _severity(topic: str) -> Severity:
    if topic in {
        "projected_monthly_revenue",
        "annual_revenue",
        "investment_range",
        "protected_territory",
        "personal_guarantee_months",
        "royalty_rate",
        "marketing_rate",
        "other_revenue_fee_rate",
        "recurring_monthly_fees",
        "lease_escalation_rate",
        "outlet_survival_rate",
        "earnings_support",
    }:
        return Severity.HIGH
    if topic in {
        "initial_fee",
        "buildout_cost",
        "equipment_cost",
        "working_capital",
        "lease_monthly_cost",
        "gross_margin_rate",
        "break_even",
    }:
        return Severity.MEDIUM
    return Severity.LOW


def _impact(topic: str, left: ExtractedClaim, right: ExtractedClaim) -> FinancialImpact | None:
    if not isinstance(left.normalized_value, Decimal) or not isinstance(
        right.normalized_value, Decimal
    ):
        return None
    difference = abs(left.normalized_value - right.normalized_value)
    if topic.endswith("_rate") or topic in {"personal_guarantee_months", "break_even"}:
        return None
    if topic in {"recurring_monthly_fees", "lease_monthly_cost", "fixed_monthly_costs"}:
        return FinancialImpact(
            amount=difference,
            period="monthly",
            description="Difference between the two cited monthly amounts.",
            formula="absolute(cited amount A - cited amount B)",
        )
    return FinancialImpact(
        amount=difference,
        period="one_time",
        description="Difference between the two cited one-time amounts.",
        formula="absolute(cited amount A - cited amount B)",
    )


def _contradiction(
    topic: str, anchor: ExtractedClaim, conflict: ExtractedClaim
) -> tuple[ClaimAssessment, RiskFinding]:
    label = TOPIC_LABELS.get(topic, topic.replace("_", " "))
    assessment = ClaimAssessment(
        claim_text=anchor.text,
        topic=topic,
        status=ClaimStatus.CONTRADICTED,
        rationale=(
            f"The cited sources report materially different values for the {label}. "
            "The higher-authority source is used for calculations, but expert review is required."
        ),
        material=anchor.material or conflict.material,
        evidence=[anchor.evidence],
        conflicting_evidence=[conflict.evidence],
    )
    finding = RiskFinding(
        category=FindingCategory.CONTRADICTION,
        title=f"Conflicting {label}",
        description=(
            f"Two cited sources disagree about the {label}. The discrepancy can materially "
            "change the affordability or risk assessment."
        ),
        severity=_severity(topic),
        material=anchor.material or conflict.material,
        evidence=[anchor.evidence, conflict.evidence],
        financial_impact=_impact(topic, anchor, conflict),
    )
    return assessment, finding


def assess_claims(claims: list[ExtractedClaim]) -> SkepticResult:
    """Try to disprove each material statement using higher-authority sources."""

    result = SkepticResult()
    for topic, topic_claims in facts_by_topic(claims).items():
        ordered = sorted(topic_claims, key=lambda claim: (_weight(claim), not claim.promotional), reverse=True)
        known = [claim for claim in ordered if claim.normalized_value is not None]
        unknown = [claim for claim in ordered if claim.normalized_value is None]
        label = TOPIC_LABELS.get(topic, topic.replace("_", " "))

        if unknown and any(claim.material for claim in unknown):
            reference = unknown[0].evidence
            request = f"Obtain a current, signed source that states the {label}."
            result.missing_evidence.append(request)
            result.assessments.append(
                ClaimAssessment(
                    claim_text=unknown[0].text,
                    topic=topic,
                    status=ClaimStatus.UNRESOLVED,
                    rationale=f"The cited source explicitly leaves the {label} unresolved.",
                    material=True,
                    evidence=[reference],
                )
            )
            result.findings.append(
                RiskFinding(
                    category=FindingCategory.MISSING_EVIDENCE,
                    title=f"Missing support for {label}",
                    description=f"A material value for the {label} is not established by the evidence.",
                    severity=Severity.HIGH,
                    material=True,
                    unresolved=True,
                    evidence=[reference],
                    requested_evidence=request,
                )
            )
            if not known:
                continue

        if not known:
            continue

        authoritative = known[0]
        conflict = next(
            (
                candidate
                for candidate in known[1:]
                if _different(authoritative.normalized_value, candidate.normalized_value, topic)
            ),
            None,
        )
        if conflict is not None:
            assessment, finding = _contradiction(topic, authoritative, conflict)
            result.assessments.append(assessment)
            result.findings.append(finding)
            continue

        promotional_only = all(_weight(claim) <= AUTHORITATIVE_WEIGHT[DocumentKind.BROCHURE] for claim in known)
        if promotional_only and any(claim.material for claim in known):
            request = f"Obtain authoritative documentation supporting the {label}."
            result.missing_evidence.append(request)
            result.assessments.append(
                ClaimAssessment(
                    claim_text=authoritative.text,
                    topic=topic,
                    status=ClaimStatus.UNRESOLVED,
                    rationale=(
                        f"The {label} appears only in promotional material and lacks independent "
                        "or disclosure-level support."
                    ),
                    material=True,
                    evidence=[authoritative.evidence],
                )
            )
            result.findings.append(
                RiskFinding(
                    category=FindingCategory.MISSING_EVIDENCE,
                    title=f"Promotional {label} is not independently supported",
                    description=(
                        f"The material {label} has only a promotional source and remains unresolved."
                    ),
                    severity=Severity.HIGH,
                    material=True,
                    unresolved=True,
                    evidence=[authoritative.evidence],
                    requested_evidence=request,
                )
            )
            continue

        result.assessments.append(
            ClaimAssessment(
                claim_text=authoritative.text,
                topic=topic,
                status=ClaimStatus.SUPPORTED,
                rationale=f"The {label} is supported by the cited source set.",
                material=authoritative.material,
                evidence=[claim.evidence for claim in known],
            )
        )

    # Preserve order while removing duplicate evidence requests.
    result.missing_evidence = list(dict.fromkeys(result.missing_evidence))
    return result
