"""Deterministic synthetic location-risk screening."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from supershield.models import (
    CaseInput,
    ExtractedClaim,
    FindingCategory,
    LocationAssessment,
    LocationData,
    RiskFinding,
    Severity,
)
from supershield.tools.evidence import facts_by_topic


@dataclass(slots=True)
class LocationResult:
    assessment: LocationAssessment | None
    findings: list[RiskFinding] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)


def _data_from_claims(
    case_input: CaseInput, claims: list[ExtractedClaim]
) -> tuple[LocationData | None, list]:
    topics = facts_by_topic(claims)
    population_claim = next(
        (
            claim
            for claim in topics.get("population", [])
            if isinstance(claim.normalized_value, Decimal)
        ),
        None,
    )
    competitor_claim = next(
        (
            claim
            for claim in topics.get("competitor_count", [])
            if isinstance(claim.normalized_value, Decimal)
        ),
        None,
    )
    brand_claim = next(
        (
            claim
            for claim in topics.get("same_brand_units", [])
            if isinstance(claim.normalized_value, Decimal)
        ),
        None,
    )
    territory_claim = next(
        (
            claim
            for claim in topics.get("protected_territory", [])
            if isinstance(claim.normalized_value, bool)
        ),
        None,
    )
    if not any((population_claim, competitor_claim, brand_claim, territory_claim)):
        return None, []
    # Unnamed competitors preserve the cited count without inventing real businesses.
    competitor_count = int(competitor_claim.normalized_value) if competitor_claim else 0
    from supershield.models import CompetitorLocation

    data = LocationData(
        location_name=case_input.preferred_location,
        population=int(population_claim.normalized_value) if population_claim else None,
        competitors=[
            CompetitorLocation(name=f"Synthetic competitor {index + 1}", distance_km=Decimal("5"))
            for index in range(competitor_count)
        ],
        same_brand_units=int(brand_claim.normalized_value) if brand_claim else 0,
        protected_territory=bool(territory_claim.normalized_value) if territory_claim else None,
        source="document-derived synthetic data",
    )
    evidence = [
        claim.evidence
        for claim in (population_claim, competitor_claim, brand_claim, territory_claim)
        if claim is not None
    ]
    return data, evidence


def assess_location(
    case_input: CaseInput,
    location_data: LocationData | None,
    claims: list[ExtractedClaim],
) -> LocationResult:
    evidence = []
    if location_data is None:
        location_data, evidence = _data_from_claims(case_input, claims)
    else:
        location_topics = {
            "population",
            "competitor_count",
            "same_brand_units",
            "protected_territory",
        }
        relevant_claims = [claim for claim in claims if claim.topic in location_topics]
        evidence = [claim.evidence for claim in relevant_claims]
        territory_claim = next(
            (
                claim
                for claim in relevant_claims
                if claim.topic == "protected_territory"
                and isinstance(claim.normalized_value, bool)
            ),
            None,
        )
        if location_data.protected_territory is None and territory_claim is not None:
            location_data = location_data.model_copy(
                update={"protected_territory": territory_claim.normalized_value}
            )

    if location_data is None:
        request = (
            "Provide the curated synthetic population, competitor-distance, same-brand unit, "
            "and territory dataset for the preferred location."
        )
        return LocationResult(
            assessment=None,
            findings=[
                RiskFinding(
                    category=FindingCategory.MISSING_EVIDENCE,
                    title="Location screening data is missing",
                    description="Indicative saturation cannot be screened without the synthetic location dataset.",
                    severity=Severity.MEDIUM,
                    material=True,
                    unresolved=True,
                    requested_evidence=request,
                )
            ],
            missing_evidence=[request],
        )

    direct = sum(
        1
        for competitor in location_data.competitors
        if competitor.distance_km <= location_data.radius_km
        and competitor.category.lower() == "direct"
    )
    density = (
        (Decimal(direct) / Decimal(location_data.population) * Decimal("10000")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if location_data.population
        else None
    )
    score = min(Decimal("45"), Decimal(direct) * Decimal("9"))
    if density is not None:
        score += min(Decimal("20"), density * Decimal("4"))
    else:
        score += Decimal("5")
    score += min(Decimal("20"), Decimal(location_data.same_brand_units) * Decimal("10"))
    if location_data.protected_territory is False:
        score += Decimal("20")
    score = min(Decimal("100"), score).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    severity = Severity.HIGH if score >= 65 else Severity.MEDIUM if score >= 40 else Severity.LOW
    assessment = LocationAssessment(
        location_name=location_data.location_name or case_input.preferred_location,
        radius_km=location_data.radius_km,
        direct_competitors=direct,
        same_brand_units=location_data.same_brand_units,
        competitor_density_per_10k=density,
        saturation_score=score,
        severity=severity,
        rationale=(
            f"The synthetic dataset shows {direct} direct competitors and "
            f"{location_data.same_brand_units} same-brand units within the screening radius."
        ),
        evidence=evidence,
    )
    findings: list[RiskFinding] = []
    if severity.rank >= Severity.MEDIUM.rank:
        findings.append(
            RiskFinding(
                category=FindingCategory.LOCATION,
                title="Indicative location saturation requires review",
                description=(
                    "Synthetic competitor density, same-brand presence, or territory terms produce "
                    "an elevated screening score. A qualified site-selection review is appropriate."
                ),
                severity=severity,
                material=severity == Severity.HIGH,
                evidence=evidence,
            )
        )
    missing: list[str] = []
    if location_data.population is None:
        missing.append("Provide the synthetic population denominator for the screening radius.")

    for request in missing:
        findings.append(
            RiskFinding(
                category=FindingCategory.MISSING_EVIDENCE,
                title="Location input remains unresolved",
                description="A location-risk input is not established by the available evidence.",
                severity=Severity.MEDIUM,
                material=True,
                unresolved=True,
                evidence=evidence,
                requested_evidence=request,
            )
        )
    return LocationResult(assessment=assessment, findings=findings, missing_evidence=missing)
