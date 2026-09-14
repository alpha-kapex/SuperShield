"""Typed public and internal records used by the SuperShield workflow.

The models deliberately keep evidence, calculations, approvals, and audit events
explicit.  Model-generated prose is never accepted as a substitute for one of
these records.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ShieldModel(BaseModel):
    """Strict base model with a browser-friendly JSON representation."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        json_encoders={Decimal: lambda value: float(value)},
    )


class RiskTolerance(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class DecisionState(StrEnum):
    READY_FOR_EXPERT_REVIEW = "READY_FOR_EXPERT_REVIEW"
    MORE_EVIDENCE_REQUIRED = "MORE_EVIDENCE_REQUIRED"
    MATERIAL_RISK_IDENTIFIED = "MATERIAL_RISK_IDENTIFIED"


class Severity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}[self.value]


class DocumentKind(StrEnum):
    BROCHURE = "brochure"
    DISCLOSURE = "disclosure"
    FINANCIAL = "financial"
    LEASE = "lease"
    LOCATION = "location"
    CORRESPONDENCE = "correspondence"
    OTHER = "other"


class ClaimStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"


class FindingCategory(StrEnum):
    CONTRADICTION = "contradiction"
    FINANCIAL = "financial"
    LEASE = "lease"
    LOCATION = "location"
    MISSING_EVIDENCE = "missing_evidence"
    PROMPT_INJECTION = "prompt_injection"
    VALIDATION = "validation"


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_FOR_EVIDENCE = "WAITING_FOR_EVIDENCE"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    @property
    def terminal(self) -> bool:
        return self in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.WAITING_FOR_EVIDENCE}


class EventStatus(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    INFO = "INFO"


class ApprovalAction(StrEnum):
    EXPORT_REPORT = "EXPORT_REPORT"
    SEND_TEST_EVIDENCE_REQUEST = "SEND_TEST_EVIDENCE_REQUEST"


class CheckpointStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


class CaseInput(ShieldModel):
    buyer_name: str = Field(default="Priya", min_length=1, max_length=100)
    cash_available: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    maximum_investment: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    emergency_reserve: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    required_monthly_household_income: Decimal = Field(
        ge=0, max_digits=14, decimal_places=2
    )
    preferred_location: str = Field(min_length=1, max_length=200)
    risk_tolerance: RiskTolerance = RiskTolerance.LOW
    currency: str = Field(default="USD", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")

    @field_validator("risk_tolerance", mode="before")
    @classmethod
    def normalize_risk_tolerance(cls, value: Any) -> Any:
        aliases = {
            "conservative": RiskTolerance.LOW,
            "balanced": RiskTolerance.MODERATE,
            "medium": RiskTolerance.MODERATE,
            "growth": RiskTolerance.HIGH,
        }
        return aliases.get(str(value).lower(), value)


class EvidenceDocument(ShieldModel):
    document_id: str = Field(default_factory=lambda: new_id("doc"), min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    kind: DocumentKind = DocumentKind.OTHER
    content: str = Field(min_length=1, max_length=250_000)
    source: str = Field(default="curated-demo", min_length=1, max_length=240)
    received_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return sha256(self.content.encode("utf-8")).hexdigest()


class EvidenceReference(ShieldModel):
    reference_id: str = Field(default_factory=lambda: new_id("ev"))
    document_id: str
    document_title: str
    document_kind: DocumentKind = DocumentKind.OTHER
    page: int = Field(default=1, ge=1)
    excerpt: str = Field(min_length=1, max_length=2_000)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    locator: str | None = Field(default=None, max_length=240)


class ExtractedClaim(ShieldModel):
    claim_id: str = Field(default_factory=lambda: new_id("claim"))
    text: str = Field(min_length=1, max_length=2_000)
    topic: str = Field(min_length=1, max_length=120)
    normalized_value: Decimal | str | bool | None = None
    unit: str | None = Field(default=None, max_length=40)
    material: bool = False
    promotional: bool = False
    evidence: EvidenceReference


class ClaimAssessment(ShieldModel):
    claim_id: str = Field(default_factory=lambda: new_id("assessment"))
    claim_text: str = Field(min_length=1, max_length=2_000)
    topic: str = Field(min_length=1, max_length=120)
    status: ClaimStatus
    rationale: str = Field(min_length=1, max_length=4_000)
    material: bool = False
    evidence: list[EvidenceReference] = Field(default_factory=list)
    conflicting_evidence: list[EvidenceReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_matches_status(self) -> ClaimAssessment:
        if self.status == ClaimStatus.SUPPORTED and not self.evidence:
            raise ValueError("supported claims require evidence")
        if self.status == ClaimStatus.CONTRADICTED and (
            not self.evidence or not self.conflicting_evidence
        ):
            raise ValueError("contradicted claims require both sides of the contradiction")
        return self


class FinancialImpact(ShieldModel):
    amount: Decimal
    period: Literal["one_time", "monthly", "annual", "total_term"]
    description: str = Field(min_length=1, max_length=500)
    formula: str = Field(min_length=1, max_length=1_000)


class RiskFinding(ShieldModel):
    finding_id: str = Field(default_factory=lambda: new_id("risk"))
    category: FindingCategory
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=4_000)
    severity: Severity
    material: bool = False
    unresolved: bool = False
    evidence: list[EvidenceReference] = Field(default_factory=list)
    financial_impact: FinancialImpact | None = None
    requested_evidence: str | None = Field(default=None, max_length=1_000)


class FinancialAssumptions(ShieldModel):
    initial_fee: Decimal = Field(default=Decimal("0"), ge=0)
    buildout_cost: Decimal = Field(default=Decimal("0"), ge=0)
    equipment_cost: Decimal = Field(default=Decimal("0"), ge=0)
    opening_inventory: Decimal = Field(default=Decimal("0"), ge=0)
    working_capital: Decimal = Field(default=Decimal("0"), ge=0)
    other_startup_costs: Decimal = Field(default=Decimal("0"), ge=0)
    projected_monthly_revenue: Decimal = Field(default=Decimal("0"), ge=0)
    gross_margin_rate: Decimal = Field(default=Decimal("0.65"), ge=0, le=1)
    royalty_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    marketing_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    other_revenue_fee_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    recurring_monthly_fees: Decimal = Field(default=Decimal("0"), ge=0)
    fixed_monthly_costs: Decimal = Field(default=Decimal("0"), ge=0)
    lease_monthly_cost: Decimal = Field(default=Decimal("0"), ge=0)
    lease_escalation_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    personal_guarantee_months: int = Field(default=0, ge=0, le=600)
    source_evidence: list[EvidenceReference] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)


class FinancialScenario(ShieldModel):
    scenario_id: str = Field(default_factory=lambda: new_id("scenario"))
    name: str = Field(min_length=1, max_length=120)
    revenue_factor: Decimal = Field(gt=0, le=2)
    monthly_revenue: Decimal
    investment_required: Decimal
    cash_after_investment: Decimal
    monthly_percentage_fees: Decimal
    monthly_fixed_and_recurring_costs: Decimal
    monthly_operating_profit: Decimal
    monthly_household_income_gap: Decimal
    break_even_monthly_revenue: Decimal | None
    runway_months: Decimal | None
    guarantee_exposure: Decimal
    formulae: dict[str, str] = Field(default_factory=dict)
    evidence: list[EvidenceReference] = Field(default_factory=list)


class CompetitorLocation(ShieldModel):
    name: str = Field(min_length=1, max_length=200)
    distance_km: Decimal = Field(ge=0)
    category: str = Field(default="direct", max_length=80)


class LocationData(ShieldModel):
    location_name: str | None = Field(default=None, max_length=200)
    population: int | None = Field(default=None, ge=0)
    radius_km: Decimal = Field(default=Decimal("5"), gt=0, le=100)
    competitors: list[CompetitorLocation] = Field(default_factory=list)
    same_brand_units: int = Field(default=0, ge=0)
    protected_territory: bool | None = None
    source: str = Field(default="synthetic", max_length=120)


class LocationAssessment(ShieldModel):
    location_name: str
    radius_km: Decimal
    direct_competitors: int
    same_brand_units: int
    competitor_density_per_10k: Decimal | None
    saturation_score: Decimal = Field(ge=0, le=100)
    severity: Severity
    rationale: str
    limitations: str = (
        "Synthetic screening result only; it is not professional site-selection advice."
    )
    evidence: list[EvidenceReference] = Field(default_factory=list)


class InvestigationTask(ShieldModel):
    task_id: str
    tool: str
    purpose: str
    depends_on: list[str] = Field(default_factory=list)
    required: bool = True


class InvestigationPlan(ShieldModel):
    plan_id: str = Field(default_factory=lambda: new_id("plan"))
    case_id: str
    constraints_summary: str
    tasks: list[InvestigationTask]
    created_at: datetime = Field(default_factory=utc_now)


class HumanCheckpoint(ShieldModel):
    checkpoint_id: str = Field(default_factory=lambda: new_id("checkpoint"))
    action: ApprovalAction
    description: str
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    session_id: str
    expires_at: datetime
    status: CheckpointStatus = CheckpointStatus.PENDING
    token: str | None = Field(default=None, repr=False)
    approved_at: datetime | None = None


class ValidationIssue(ShieldModel):
    code: str
    message: str
    record_id: str | None = None
    severity: Severity = Severity.HIGH


class ValidationReport(ShieldModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    checked_references: int = 0
    checked_calculations: int = 0


class ProvenanceRecord(ShieldModel):
    component: str
    version: str = "deterministic-v1"
    input_hash: str
    executed_at: datetime = Field(default_factory=utc_now)
    duration_ms: int = Field(default=0, ge=0)


class DecisionPacket(ShieldModel):
    packet_id: str = Field(default_factory=lambda: new_id("packet"))
    case_id: str
    run_id: str
    revision: int = Field(default=1, ge=1)
    decision_state: DecisionState
    plain_language_summary: str = Field(min_length=1, max_length=4_000)
    scope_notice: str = (
        "SuperShield supports investigation and human review; it does not provide legal, "
        "investment, or site-selection advice and does not make the final decision."
    )
    investigation_plan: InvestigationPlan
    claim_assessments: list[ClaimAssessment] = Field(default_factory=list)
    risk_findings: list[RiskFinding] = Field(default_factory=list)
    financial_scenarios: list[FinancialScenario] = Field(default_factory=list)
    location_assessment: LocationAssessment | None = None
    missing_evidence: list[str] = Field(default_factory=list)
    evidence_index: list[EvidenceReference] = Field(default_factory=list)
    why_this_changed: list[str] = Field(default_factory=list)
    validation: ValidationReport
    checkpoints: list[HumanCheckpoint] = Field(default_factory=list)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)


class RunEvent(ShieldModel):
    event_id: str = Field(default_factory=lambda: new_id("event"))
    run_id: str
    sequence: int = Field(ge=1)
    timestamp: datetime = Field(default_factory=utc_now)
    tool: str
    status: EventStatus
    message: str = Field(min_length=1, max_length=1_000)
    duration_ms: int | None = Field(default=None, ge=0)
    citations: list[EvidenceReference] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class CaseRecord(ShieldModel):
    case_id: str = Field(default_factory=lambda: new_id("case"))
    demo_case_id: str | None = None
    title: str = Field(default="Franchise investigation", max_length=240)
    summary: str = Field(default="Curated SuperShield investigation", max_length=1_000)
    input: CaseInput
    documents: list[EvidenceDocument] = Field(default_factory=list)
    location_data: LocationData | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    version: int = Field(default=1, ge=1)


class RunRecord(ShieldModel):
    run_id: str = Field(default_factory=lambda: new_id("run"))
    case_id: str
    session_id: str
    status: RunStatus = RunStatus.PENDING
    mode: Literal["local", "strands"] = "local"
    plan: InvestigationPlan | None = None
    packet: DecisionPacket | None = None
    revision: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    affected_tasks: list[str] = Field(default_factory=list)


class DemoCaseSummary(ShieldModel):
    id: str
    title: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    document_count: int = 0


class CreateCaseRequest(ShieldModel):
    demo_case_id: str | None = None
    title: str | None = Field(default=None, max_length=240)
    summary: str | None = Field(default=None, max_length=1_000)
    input: CaseInput | None = None
    documents: list[EvidenceDocument] = Field(default_factory=list)
    location_data: LocationData | None = None

    @model_validator(mode="after")
    def has_source(self) -> CreateCaseRequest:
        if not self.demo_case_id and not self.input:
            raise ValueError("either demoCaseId or input is required")
        return self


class CreateRunRequest(ShieldModel):
    session_id: str = Field(min_length=8, max_length=200)


class EvidenceIngestRequest(ShieldModel):
    session_id: str = Field(min_length=8, max_length=200)
    documents: list[EvidenceDocument] = Field(min_length=1, max_length=10)


class ApprovalRequest(ShieldModel):
    checkpoint_id: str
    token: str
    session_id: str = Field(min_length=8, max_length=200)
    action: ApprovalAction
    payload: dict[str, Any] = Field(default_factory=dict)
    approve: bool = True


class ApprovalResult(ShieldModel):
    checkpoint_id: str
    status: CheckpointStatus
    action: ApprovalAction
    approved_at: datetime | None = None


class HealthResponse(ShieldModel):
    status: Literal["ok", "degraded"]
    mode: str
    storage: str
    optional_integrations: dict[str, str] = Field(default_factory=dict)
