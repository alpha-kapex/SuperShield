"""Policy, citation, and deterministic-calculation validation."""

from __future__ import annotations

import re
from collections.abc import Iterable

from supershield.models import (
    CaseInput,
    ClaimAssessment,
    ClaimStatus,
    EvidenceDocument,
    EvidenceReference,
    FinancialAssumptions,
    FinancialScenario,
    LocationAssessment,
    RiskFinding,
    Severity,
    ValidationIssue,
    ValidationReport,
)
from supershield.tools.finance import calculate_scenario

FORBIDDEN_CONCLUSION_LANGUAGE = (
    re.compile(r"\bbuy\b", re.I),
    re.compile(r"\bguaranteed\b", re.I),
    re.compile(r"\b(?:definitive|final)\s+(?:legal|investment)\s+advice\b", re.I),
    re.compile(r"\byou\s+(?:must|should)\s+(?:purchase|invest|sign)\b", re.I),
)


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _all_references(
    assessments: list[ClaimAssessment],
    findings: list[RiskFinding],
    scenarios: list[FinancialScenario],
    location: LocationAssessment | None,
) -> list[EvidenceReference]:
    references: list[EvidenceReference] = []
    for assessment in assessments:
        references.extend(assessment.evidence)
        references.extend(assessment.conflicting_evidence)
    for finding in findings:
        references.extend(finding.evidence)
    for scenario in scenarios:
        references.extend(scenario.evidence)
    if location:
        references.extend(location.evidence)
    unique = {
        (
            reference.document_id,
            reference.page,
            reference.excerpt,
            reference.content_hash,
        ): reference
        for reference in references
    }
    return list(unique.values())


def _citation_issues(
    documents: list[EvidenceDocument], references: list[EvidenceReference]
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    by_id = {document.document_id: document for document in documents}
    for reference in references:
        document = by_id.get(reference.document_id)
        if document is None:
            issues.append(
                ValidationIssue(
                    code="citation.document_missing",
                    message="A citation points to a document not present in this case.",
                    record_id=reference.reference_id,
                )
            )
            continue
        if reference.content_hash != document.content_hash:
            issues.append(
                ValidationIssue(
                    code="citation.hash_mismatch",
                    message="A citation hash does not match the current document content.",
                    record_id=reference.reference_id,
                )
            )
        if _normalized(reference.excerpt) not in _normalized(document.content):
            issues.append(
                ValidationIssue(
                    code="citation.excerpt_missing",
                    message="A cited excerpt cannot be found in the referenced document.",
                    record_id=reference.reference_id,
                )
            )
    return issues


def _evidence_policy_issues(
    assessments: list[ClaimAssessment], findings: list[RiskFinding]
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for assessment in assessments:
        if assessment.status == ClaimStatus.SUPPORTED and not assessment.evidence:
            issues.append(
                ValidationIssue(
                    code="claim.unsupported",
                    message="A supported claim has no citation.",
                    record_id=assessment.claim_id,
                )
            )
        if assessment.status == ClaimStatus.CONTRADICTED and (
            not assessment.evidence or not assessment.conflicting_evidence
        ):
            issues.append(
                ValidationIssue(
                    code="claim.contradiction_missing_side",
                    message="A contradiction must cite both source positions.",
                    record_id=assessment.claim_id,
                )
            )
    for finding in findings:
        if finding.material and not finding.unresolved and not finding.evidence:
            issues.append(
                ValidationIssue(
                    code="finding.no_evidence",
                    message="A resolved material finding has no supporting evidence.",
                    record_id=finding.finding_id,
                )
            )
        if finding.unresolved and not finding.requested_evidence:
            issues.append(
                ValidationIssue(
                    code="finding.no_evidence_request",
                    message="An unresolved finding must state the evidence needed to resolve it.",
                    record_id=finding.finding_id,
                )
            )
    return issues


def _calculation_issues(
    case_input: CaseInput,
    assumptions: FinancialAssumptions,
    scenarios: list[FinancialScenario],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    fields: tuple[str, ...] = (
        "monthly_revenue",
        "investment_required",
        "cash_after_investment",
        "monthly_percentage_fees",
        "monthly_fixed_and_recurring_costs",
        "monthly_operating_profit",
        "monthly_household_income_gap",
        "break_even_monthly_revenue",
        "runway_months",
        "guarantee_exposure",
    )
    for scenario in scenarios:
        expected = calculate_scenario(
            case_input,
            assumptions,
            name=scenario.name,
            revenue_factor=scenario.revenue_factor,
        )
        for field_name in fields:
            actual_value = getattr(scenario, field_name)
            expected_value = getattr(expected, field_name)
            if actual_value != expected_value:
                issues.append(
                    ValidationIssue(
                        code="calculation.mismatch",
                        message=f"Scenario field {field_name} does not match its deterministic formula.",
                        record_id=scenario.scenario_id,
                        severity=Severity.CRITICAL,
                    )
                )
    return issues


def _generated_text(
    summary: str,
    assessments: list[ClaimAssessment],
    findings: list[RiskFinding],
    location: LocationAssessment | None,
) -> Iterable[tuple[str, str | None]]:
    yield summary, None
    for assessment in assessments:
        # Claim text and evidence excerpts are verbatim data; rationale is generated output.
        yield assessment.rationale, assessment.claim_id
    for finding in findings:
        yield finding.title, finding.finding_id
        yield finding.description, finding.finding_id
    if location:
        yield location.rationale, None
        yield location.limitations, None


def _language_issues(
    summary: str,
    assessments: list[ClaimAssessment],
    findings: list[RiskFinding],
    location: LocationAssessment | None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for text, record_id in _generated_text(summary, assessments, findings, location):
        if any(pattern.search(text) for pattern in FORBIDDEN_CONCLUSION_LANGUAGE):
            issues.append(
                ValidationIssue(
                    code="policy.prohibited_language",
                    message="Generated output contains prohibited consequential recommendation language.",
                    record_id=record_id,
                    severity=Severity.CRITICAL,
                )
            )
    return issues


def validate_analysis(
    *,
    documents: list[EvidenceDocument],
    case_input: CaseInput,
    assumptions: FinancialAssumptions,
    assessments: list[ClaimAssessment],
    findings: list[RiskFinding],
    scenarios: list[FinancialScenario],
    location: LocationAssessment | None,
    summary: str,
) -> ValidationReport:
    references = _all_references(assessments, findings, scenarios, location)
    issues = [
        *_citation_issues(documents, references),
        *_evidence_policy_issues(assessments, findings),
        *_calculation_issues(case_input, assumptions, scenarios),
        *_language_issues(summary, assessments, findings, location),
    ]
    return ValidationReport(
        valid=not issues,
        issues=issues,
        checked_references=len(references),
        checked_calculations=len(scenarios) * 10,
    )


def materially_valid(report: ValidationReport) -> bool:
    return not any(issue.severity.rank >= Severity.HIGH.rank for issue in report.issues)
