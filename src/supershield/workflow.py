"""Evidence-bound supervisor shared by the local API and cloud adapters."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter
from typing import Any, TypeVar

from supershield.models import (
    ApprovalAction,
    ApprovalRequest,
    ApprovalResult,
    CaseRecord,
    CheckpointStatus,
    ClaimStatus,
    DecisionPacket,
    DecisionState,
    EventStatus,
    EvidenceDocument,
    EvidenceReference,
    FindingCategory,
    HumanCheckpoint,
    InvestigationPlan,
    InvestigationTask,
    LocationData,
    ProvenanceRecord,
    RiskFinding,
    RunEvent,
    RunRecord,
    RunStatus,
    Severity,
    utc_now,
)
from supershield.storage import StateStore
from supershield.tools.approval import ApprovalError, ApprovalTokenService, canonical_json
from supershield.tools.evidence import EvidenceCollection, collect_evidence, facts_by_topic
from supershield.tools.finance import FinanceResult, calculate_financial_scenarios
from supershield.tools.location import LocationResult, assess_location
from supershield.tools.skepticism import TOPIC_LABELS, SkepticResult, assess_claims
from supershield.tools.validation import materially_valid, validate_analysis

T = TypeVar("T")

FINANCIAL_TOPICS = {
    "projected_monthly_revenue",
    "annual_revenue",
    "initial_fee",
    "buildout_cost",
    "equipment_cost",
    "opening_inventory",
    "working_capital",
    "gross_margin_rate",
    "royalty_rate",
    "marketing_rate",
    "other_revenue_fee_rate",
    "recurring_monthly_fees",
    "lease_escalation_rate",
    "lease_monthly_cost",
    "personal_guarantee_months",
    "fixed_monthly_costs",
    "investment_range",
}
LOCATION_TOPICS = {
    "population",
    "competitor_count",
    "same_brand_units",
    "protected_territory",
}


@dataclass(slots=True)
class _AnalysisSnapshot:
    evidence: EvidenceCollection
    skeptic: SkepticResult
    finance: FinanceResult
    location: LocationResult
    explicit_gap_findings: list[RiskFinding]
    explicit_missing: list[str]


class WorkflowConflict(RuntimeError):
    """Raised when a state transition is unsafe or no longer valid."""


class SupervisorWorkflow:
    """Run the bounded specialist graph and persist its auditable outputs."""

    def __init__(
        self,
        store: StateStore,
        approvals: ApprovalTokenService,
        *,
        execution_mode: str = "local",
        strands_adapter: Any | None = None,
    ) -> None:
        self.store = store
        self.approvals = approvals
        self.execution_mode = execution_mode
        self.strands_adapter = strands_adapter
        self._snapshots: dict[str, _AnalysisSnapshot] = {}
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.RLock()

    def create_plan(self, case: CaseRecord) -> InvestigationPlan:
        input_ = case.input
        return InvestigationPlan(
            case_id=case.case_id,
            constraints_summary=(
                f"{input_.buyer_name}'s ceiling is {input_.currency} "
                f"{input_.maximum_investment}; preserve an emergency reserve of "
                f"{input_.emergency_reserve} and test monthly household income of "
                f"{input_.required_monthly_household_income} for "
                f"{input_.preferred_location} at {input_.risk_tolerance.value} risk tolerance."
            ),
            tasks=[
                InvestigationTask(
                    task_id="collect_evidence",
                    tool="evidence_collector",
                    purpose="Extract citable claims while isolating instruction-like text.",
                ),
                InvestigationTask(
                    task_id="challenge_claims",
                    tool="skeptic",
                    purpose="Seek contradictions and unsupported material claims.",
                    depends_on=["collect_evidence"],
                ),
                InvestigationTask(
                    task_id="calculate_finance",
                    tool="deterministic_finance",
                    purpose="Calculate affordability, downside, break-even, and guarantee exposure.",
                    depends_on=["collect_evidence"],
                ),
                InvestigationTask(
                    task_id="screen_location",
                    tool="location_risk",
                    purpose="Screen synthetic density, territory, and saturation inputs.",
                    depends_on=["collect_evidence"],
                ),
                InvestigationTask(
                    task_id="validate",
                    tool="evidence_validator",
                    purpose="Enforce citations, deterministic arithmetic, and safe language.",
                    depends_on=["challenge_claims", "calculate_finance", "screen_location"],
                ),
                InvestigationTask(
                    task_id="assemble_packet",
                    tool="supervisor",
                    purpose="Assemble a human-review packet without making the final decision.",
                    depends_on=["validate"],
                ),
            ],
        )

    def start_run(self, case_id: str, session_id: str) -> RunRecord:
        case = self.store.get_case(case_id)
        run = RunRecord(
            case_id=case_id,
            session_id=session_id,
            mode="strands" if self.execution_mode == "strands" else "local",
            plan=self.create_plan(case),
        )
        self.store.put_run(run, create_only=True)
        return self._execute(run.run_id, changed_documents=None)

    def ingest_evidence(
        self,
        run_id: str,
        *,
        session_id: str,
        documents: list[EvidenceDocument],
    ) -> RunRecord:
        if not documents:
            raise ValueError("at least one evidence document is required")
        lock = self._run_lock(run_id)
        with lock:
            run = self.store.get_run(run_id)
            if run.session_id != session_id:
                raise WorkflowConflict("session does not own this run")
            if run.status == RunStatus.RUNNING:
                raise WorkflowConflict("run is already in progress")
            case = self.store.get_case(run.case_id)
            replacements = {document.document_id: document for document in documents}
            merged = [
                document
                for document in case.documents
                if document.document_id not in replacements
            ]
            merged.extend(documents)
            case.documents = merged
            case.version += 1
            case.updated_at = utc_now()
            self.store.put_case(case)
            self._emit(
                run_id,
                "evidence_ingest",
                EventStatus.COMPLETED,
                f"Ingested {len(documents)} evidence document(s); affected analyses will rerun.",
                details={
                    "documentIds": [document.document_id for document in documents],
                    "caseVersion": case.version,
                },
            )
        return self._execute(run_id, changed_documents=documents)

    def approve(self, run_id: str, request: ApprovalRequest) -> ApprovalResult:
        lock = self._run_lock(run_id)
        with lock:
            run = self.store.get_run(run_id)
            if run.packet is None:
                raise WorkflowConflict("the run has no decision packet")
            if run.session_id != request.session_id:
                raise ApprovalError("Approval session does not own this run")
            checkpoint = next(
                (
                    item
                    for item in run.packet.checkpoints
                    if item.checkpoint_id == request.checkpoint_id
                ),
                None,
            )
            if checkpoint is None:
                raise ApprovalError("Unknown approval checkpoint")
            if checkpoint.status != CheckpointStatus.PENDING:
                raise ApprovalError("Approval checkpoint is no longer pending")
            if checkpoint.action != request.action:
                raise ApprovalError("Approval action does not match the checkpoint")
            expected_payload = self.action_payload(run, checkpoint.action)
            if request.payload != expected_payload:
                raise ApprovalError("Approval payload does not match the checkpoint")
            self.approvals.verify_and_consume(
                request.token,
                action=request.action,
                payload=expected_payload,
                case_id=run.case_id,
                run_id=run.run_id,
                session_id=run.session_id,
                checkpoint_id=checkpoint.checkpoint_id,
            )
            checkpoint.status = (
                CheckpointStatus.APPROVED if request.approve else CheckpointStatus.REJECTED
            )
            checkpoint.approved_at = utc_now() if request.approve else None
            checkpoint.token = None
            run.updated_at = utc_now()
            self.store.put_run(run)
            self._emit(
                run_id,
                "human_approval",
                EventStatus.COMPLETED,
                (
                    f"Human approved {request.action.value}."
                    if request.approve
                    else f"Human rejected {request.action.value}; no action was taken."
                ),
                details={
                    "checkpointId": checkpoint.checkpoint_id,
                    "action": request.action.value,
                    "approved": request.approve,
                },
            )
            return ApprovalResult(
                checkpoint_id=checkpoint.checkpoint_id,
                status=checkpoint.status,
                action=checkpoint.action,
                approved_at=checkpoint.approved_at,
            )

    def action_payload(
        self, run: RunRecord, action: ApprovalAction
    ) -> dict[str, Any]:
        if run.packet is None:
            raise WorkflowConflict("the run has no decision packet")
        common = {
            "caseId": run.case_id,
            "runId": run.run_id,
            "packetRevision": run.packet.revision,
        }
        if action == ApprovalAction.EXPORT_REPORT:
            return {**common, "format": "json"}
        if action == ApprovalAction.SEND_TEST_EVIDENCE_REQUEST:
            return {**common, "requests": run.packet.missing_evidence}
        raise ApprovalError("Unsupported approval action")

    def _execute(
        self,
        run_id: str,
        *,
        changed_documents: list[EvidenceDocument] | None,
    ) -> RunRecord:
        lock = self._run_lock(run_id)
        with lock:
            run = self.store.get_run(run_id)
            case = self.store.get_case(run.case_id)
            previous_packet = run.packet
            previous_snapshot = self._snapshots.get(run_id)
            affected = self._affected_tasks(changed_documents, previous_snapshot)
            run.status = RunStatus.RUNNING
            run.started_at = run.started_at or utc_now()
            run.updated_at = utc_now()
            run.error = None
            run.affected_tasks = sorted(affected)
            self.store.put_run(run)
            self._emit(
                run_id,
                "supervisor",
                EventStatus.STARTED,
                "Supervisor started the bounded investigation plan.",
                details={"revision": run.revision + 1, "affectedTasks": sorted(affected)},
            )
            try:
                self._attempt_strands(run, case)
                durations: dict[str, int] = {}
                evidence = self._run_task(
                    run_id,
                    "evidence_collector",
                    "Extracting citable claims from untrusted documents.",
                    lambda: collect_evidence(case.documents),
                    durations,
                )
                assert isinstance(evidence, EvidenceCollection)

                if previous_snapshot is None or "challenge_claims" in affected:
                    skeptic = self._run_task(
                        run_id,
                        "skeptic",
                        "Testing material claims for contradiction and missing support.",
                        lambda: _settle_superseded_unknowns(
                            assess_claims(evidence.claims), evidence.claims
                        ),
                        durations,
                    )
                    explicit_findings, explicit_missing = _explicit_evidence_gaps(
                        case.documents
                    )
                else:
                    skeptic = previous_snapshot.skeptic
                    explicit_findings = previous_snapshot.explicit_gap_findings
                    explicit_missing = previous_snapshot.explicit_missing
                    self._skip(run_id, "skeptic")

                if previous_snapshot is None or "calculate_finance" in affected:
                    finance = self._run_task(
                        run_id,
                        "deterministic_finance",
                        "Calculating reproducible financial scenarios.",
                        lambda: calculate_financial_scenarios(case.input, evidence.claims),
                        durations,
                    )
                else:
                    finance = previous_snapshot.finance
                    self._skip(run_id, "deterministic_finance")

                if previous_snapshot is None or "screen_location" in affected:
                    resolved_location = _resolved_location_data(
                        case.location_data, evidence
                    )
                    location = self._run_task(
                        run_id,
                        "location_risk",
                        "Screening the synthetic location data.",
                        lambda: assess_location(
                            case.input, resolved_location, evidence.claims
                        ),
                        durations,
                    )
                else:
                    location = previous_snapshot.location
                    self._skip(run_id, "location_risk")

                assert isinstance(skeptic, SkepticResult)
                assert isinstance(finance, FinanceResult)
                assert isinstance(location, LocationResult)
                findings = _unique_findings(
                    [
                        *evidence.security_findings,
                        *skeptic.findings,
                        *finance.findings,
                        *location.findings,
                        *explicit_findings,
                    ]
                )
                missing = list(
                    dict.fromkeys(
                        [
                            *skeptic.missing_evidence,
                            *finance.missing_evidence,
                            *location.missing_evidence,
                            *explicit_missing,
                        ]
                    )
                )
                state = _decision_state(findings, missing)
                summary = _summary(state, findings, missing)
                validation = self._run_task(
                    run_id,
                    "evidence_validator",
                    "Validating citations, calculations, and decision language.",
                    lambda: validate_analysis(
                        documents=case.documents,
                        case_input=case.input,
                        assumptions=finance.assumptions,
                        assessments=skeptic.assessments,
                        findings=findings,
                        scenarios=finance.scenarios,
                        location=location.assessment,
                        summary=summary,
                    ),
                    durations,
                )
                if not materially_valid(validation):
                    state = DecisionState.MORE_EVIDENCE_REQUIRED
                    summary = (
                        "The investigation is paused because evidence or calculation "
                        "validation did not pass. The listed validation issues require review."
                    )
                revision = run.revision + 1
                packet = DecisionPacket(
                    case_id=case.case_id,
                    run_id=run.run_id,
                    revision=revision,
                    decision_state=state,
                    plain_language_summary=summary,
                    investigation_plan=run.plan or self.create_plan(case),
                    claim_assessments=skeptic.assessments,
                    risk_findings=findings,
                    financial_scenarios=finance.scenarios,
                    location_assessment=location.assessment,
                    missing_evidence=missing,
                    evidence_index=_unique_references(evidence.references),
                    why_this_changed=_change_explanations(
                        changed_documents, affected, previous_packet
                    ),
                    validation=validation,
                    provenance=_provenance(
                        case,
                        affected,
                        durations,
                        previous_packet.provenance if previous_packet else [],
                    ),
                )
                packet.checkpoints = self._issue_checkpoints(run, packet)
                run.packet = packet
                run.plan = packet.investigation_plan
                run.revision = revision
                run.status = (
                    RunStatus.WAITING_FOR_EVIDENCE
                    if missing
                    else RunStatus.COMPLETED
                )
                run.updated_at = utc_now()
                run.completed_at = utc_now() if run.status == RunStatus.COMPLETED else None
                self._snapshots[run_id] = _AnalysisSnapshot(
                    evidence=evidence,
                    skeptic=skeptic,
                    finance=finance,
                    location=location,
                    explicit_gap_findings=explicit_findings,
                    explicit_missing=explicit_missing,
                )
                self.store.put_run(run)
                for checkpoint in packet.checkpoints:
                    self._emit(
                        run_id,
                        "human_approval",
                        EventStatus.BLOCKED,
                        checkpoint.description,
                        details={
                            "checkpointId": checkpoint.checkpoint_id,
                            "action": checkpoint.action.value,
                            "payload": self.action_payload(run, checkpoint.action),
                        },
                    )
                self._emit(
                    run_id,
                    "supervisor",
                    (
                        EventStatus.BLOCKED
                        if run.status == RunStatus.WAITING_FOR_EVIDENCE
                        else EventStatus.COMPLETED
                    ),
                    (
                        "Decision packet is evidence-blocked pending targeted documents."
                        if run.status == RunStatus.WAITING_FOR_EVIDENCE
                        else "Decision packet is ready for human and qualified expert review."
                    ),
                    details={
                        "decisionState": packet.decision_state.value,
                        "packetRevision": packet.revision,
                    },
                )
                return self.store.get_run(run_id)
            except Exception as exc:
                run = self.store.get_run(run_id)
                run.status = RunStatus.FAILED
                run.error = _safe_error(exc)
                run.updated_at = utc_now()
                run.completed_at = utc_now()
                self.store.put_run(run)
                self._emit(
                    run_id,
                    "supervisor",
                    EventStatus.FAILED,
                    "The bounded investigation failed safely; no consequential action was taken.",
                    details={"error": run.error},
                )
                raise

    def _run_task(
        self,
        run_id: str,
        tool: str,
        message: str,
        operation: Callable[[], T],
        durations: dict[str, int],
    ) -> T:
        self._emit(run_id, tool, EventStatus.STARTED, message)
        started = perf_counter()
        result = operation()
        duration = max(0, round((perf_counter() - started) * 1000))
        durations[tool] = duration
        self._emit(
            run_id,
            tool,
            EventStatus.COMPLETED,
            f"{tool.replace('_', ' ').title()} completed.",
            duration_ms=duration,
            citations=_result_citations(result)[:8],
        )
        return result

    def _attempt_strands(self, run: RunRecord, case: CaseRecord) -> None:
        if run.mode != "strands":
            return
        if self.strands_adapter is None:
            run.mode = "local"
            self.store.put_run(run)
            self._emit(
                run.run_id,
                "strands_supervisor",
                EventStatus.INFO,
                "Strands is unavailable; continuing with the equivalent deterministic graph.",
                details={"degraded": True},
            )
            return
        try:
            self.strands_adapter.orchestrate(case, run.plan)
        except Exception as exc:
            run.mode = "local"
            self.store.put_run(run)
            self._emit(
                run.run_id,
                "strands_supervisor",
                EventStatus.INFO,
                "Bedrock/Strands invocation was unavailable; local deterministic execution continued.",
                details={"degraded": True, "reason": _safe_error(exc)},
            )
        else:
            self._emit(
                run.run_id,
                "strands_supervisor",
                EventStatus.COMPLETED,
                "Strands coordinated the bounded specialist tool graph.",
            )

    def _affected_tasks(
        self,
        changed_documents: list[EvidenceDocument] | None,
        snapshot: _AnalysisSnapshot | None,
    ) -> set[str]:
        all_tasks = {
            "collect_evidence",
            "challenge_claims",
            "calculate_finance",
            "screen_location",
            "validate",
            "assemble_packet",
        }
        if changed_documents is None or snapshot is None:
            return all_tasks
        delta = collect_evidence(changed_documents)
        topics = {claim.topic for claim in delta.claims}
        affected = {
            "collect_evidence",
            "challenge_claims",
            "validate",
            "assemble_packet",
        }
        if topics & FINANCIAL_TOPICS:
            affected.add("calculate_finance")
        if topics & LOCATION_TOPICS:
            affected.add("screen_location")
        return affected

    def _issue_checkpoints(
        self, run: RunRecord, packet: DecisionPacket
    ) -> list[HumanCheckpoint]:
        provisional = run.model_copy(update={"packet": packet, "revision": packet.revision})
        actions = [ApprovalAction.EXPORT_REPORT]
        if packet.missing_evidence:
            actions.append(ApprovalAction.SEND_TEST_EVIDENCE_REQUEST)
        descriptions = {
            ApprovalAction.EXPORT_REPORT: (
                "Human approval is required before exporting this exact packet revision."
            ),
            ApprovalAction.SEND_TEST_EVIDENCE_REQUEST: (
                "Human approval is required before sending this exact test evidence request."
            ),
        }
        return [
            self.approvals.issue(
                action=action,
                payload=self.action_payload(provisional, action),
                case_id=run.case_id,
                run_id=run.run_id,
                session_id=run.session_id,
                description=descriptions[action],
            )
            for action in actions
        ]

    def _emit(
        self,
        run_id: str,
        tool: str,
        status: EventStatus,
        message: str,
        *,
        duration_ms: int | None = None,
        citations: list[EvidenceReference] | None = None,
        details: dict[str, Any] | None = None,
    ) -> RunEvent:
        sequence = len(self.store.list_events(run_id)) + 1
        event = RunEvent(
            run_id=run_id,
            sequence=sequence,
            tool=tool,
            status=status,
            message=message,
            duration_ms=duration_ms,
            citations=citations or [],
            details=details or {},
        )
        self.store.append_event(event)
        return event

    def _skip(self, run_id: str, tool: str) -> None:
        self._emit(
            run_id,
            tool,
            EventStatus.SKIPPED,
            "No relevant input changed; the prior validated result was retained.",
        )

    def _run_lock(self, run_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(run_id, threading.RLock())


def _decision_state(
    findings: list[RiskFinding], missing_evidence: list[str]
) -> DecisionState:
    if missing_evidence or any(item.unresolved and item.material for item in findings):
        return DecisionState.MORE_EVIDENCE_REQUIRED
    if any(item.material and item.severity.rank >= Severity.HIGH.rank for item in findings):
        return DecisionState.MATERIAL_RISK_IDENTIFIED
    return DecisionState.READY_FOR_EXPERT_REVIEW


def _summary(
    state: DecisionState,
    findings: list[RiskFinding],
    missing_evidence: list[str],
) -> str:
    material_count = sum(item.material for item in findings)
    if state == DecisionState.MORE_EVIDENCE_REQUIRED:
        return (
            f"The investigation is paused with {len(missing_evidence)} targeted evidence "
            f"request(s) unresolved and {material_count} material risk finding(s). "
            "Review the cited sources and obtain the listed documents before proceeding."
        )
    if state == DecisionState.MATERIAL_RISK_IDENTIFIED:
        return (
            f"The investigation identified {material_count} material cited risk finding(s). "
            "The evidence and deterministic scenarios warrant qualified expert review."
        )
    return (
        "The curated evidence is sufficiently consistent for qualified expert review. "
        "The packet supports a human decision; it is not legal or investment advice."
    )


def _resolved_location_data(
    location_data: LocationData | None,
    evidence: EvidenceCollection,
) -> LocationData | None:
    if location_data is None:
        return None
    topics = facts_by_topic(evidence.claims)
    updates: dict[str, Any] = {}
    if location_data.protected_territory is None:
        territory = next(
            (
                claim.normalized_value
                for claim in topics.get("protected_territory", [])
                if isinstance(claim.normalized_value, bool)
            ),
            None,
        )
        if territory is not None:
            updates["protected_territory"] = territory
    return location_data.model_copy(update=updates) if updates else location_data


def _settle_superseded_unknowns(
    result: SkepticResult, claims: list[Any]
) -> SkepticResult:
    known_topics = {
        claim.topic for claim in claims if claim.normalized_value is not None
    }
    resolved_topics = {
        assessment.topic
        for assessment in result.assessments
        if assessment.status == ClaimStatus.UNRESOLVED
        and assessment.topic in known_topics
    }
    if not resolved_topics:
        return result
    requests = {
        f"Obtain a current, signed source that states the {TOPIC_LABELS.get(topic, topic.replace('_', ' '))}."
        for topic in resolved_topics
    }
    result.assessments = [
        item
        for item in result.assessments
        if not (item.status == ClaimStatus.UNRESOLVED and item.topic in resolved_topics)
    ]
    result.findings = [
        item for item in result.findings if item.requested_evidence not in requests
    ]
    result.missing_evidence = [
        item for item in result.missing_evidence if item not in requests
    ]
    return result


def _explicit_evidence_gaps(
    documents: list[EvidenceDocument],
) -> tuple[list[RiskFinding], list[str]]:
    positive = False
    negative: tuple[EvidenceDocument, str] | None = None
    for document in documents:
        document_mentions_landlord = "landlord" in document.content.lower()
        sentences = [
            " ".join(part.split())
            for part in re.split(r"(?<=[.!?])\s+|\n+", document.content)
            if part.strip()
        ]
        for sentence in sentences:
            lower = sentence.lower()
            if "consent" not in lower or (
                "landlord" not in lower and not document_mentions_landlord
            ):
                continue
            if re.search(r"\b(?:no|not|missing|absent|without)\b", lower):
                negative = (document, sentence)
            elif (
                not re.search(r"\b(?:require|requires|required|request)\b", lower)
                and re.search(r"\b(?:signed|granted|approved|attached)\b", lower)
            ):
                positive = True
    if negative is None or positive:
        return [], []
    document, excerpt = negative

    request = (
        "Provide the landlord's signed consent covering the proposed use, required works, "
        "and assignment to the franchise entity."
    )
    return [
        RiskFinding(
            category=FindingCategory.MISSING_EVIDENCE,
            title="Signed landlord consent is missing",
            description=(
                "The lease evidence states that landlord consent is required but no signed "
                "consent is attached."
            ),
            severity=Severity.HIGH,
            material=True,
            unresolved=True,
            evidence=[],
            requested_evidence=request,
        )
    ], [request]


def _unique_findings(findings: list[RiskFinding]) -> list[RiskFinding]:
    seen: set[tuple[Any, ...]] = set()
    result: list[RiskFinding] = []
    for finding in findings:
        key = (
            finding.category,
            finding.title,
            finding.requested_evidence,
            tuple(reference.document_id for reference in finding.evidence),
        )
        if key not in seen:
            seen.add(key)
            result.append(finding)
    return result


def _unique_references(
    references: list[EvidenceReference],
) -> list[EvidenceReference]:
    unique: dict[tuple[Any, ...], EvidenceReference] = {}
    for reference in references:
        key = (
            reference.document_id,
            reference.page,
            reference.excerpt,
            reference.content_hash,
        )
        unique.setdefault(key, reference)
    return list(unique.values())


def _result_citations(result: Any) -> list[EvidenceReference]:
    if isinstance(result, EvidenceCollection):
        return result.references
    references: list[EvidenceReference] = []
    for attr in ("assessments", "findings", "scenarios"):
        for item in getattr(result, attr, []):
            references.extend(getattr(item, "evidence", []))
            references.extend(getattr(item, "conflicting_evidence", []))
    assessment = getattr(result, "assessment", None)
    if assessment is not None:
        references.extend(assessment.evidence)
    return _unique_references(references)


def _change_explanations(
    changed_documents: list[EvidenceDocument] | None,
    affected: set[str],
    previous_packet: DecisionPacket | None,
) -> list[str]:
    if not changed_documents or previous_packet is None:
        return []
    names = ", ".join(document.title for document in changed_documents)
    rerun = [
        label
        for task, label in (
            ("challenge_claims", "claim challenge"),
            ("calculate_finance", "financial scenarios"),
            ("screen_location", "location screening"),
        )
        if task in affected
    ]
    return [
        f"New evidence was added: {names}.",
        f"Only affected analyses were recomputed: {', '.join(rerun) or 'validation only'}.",
        f"This packet supersedes revision {previous_packet.revision}.",
    ]


def _provenance(
    case: CaseRecord,
    affected: set[str],
    durations: dict[str, int],
    previous: list[ProvenanceRecord],
) -> list[ProvenanceRecord]:
    task_to_component = {
        "collect_evidence": "evidence_collector",
        "challenge_claims": "skeptic",
        "calculate_finance": "deterministic_finance",
        "screen_location": "location_risk",
        "validate": "evidence_validator",
        "assemble_packet": "supervisor",
    }
    by_component = {item.component: item for item in previous}
    case_hash = sha256(
        canonical_json(
            {
                "caseInput": case.input,
                "caseVersion": case.version,
                "documents": [
                    {"id": document.document_id, "hash": document.content_hash}
                    for document in case.documents
                ],
            }
        )
    ).hexdigest()
    for task in affected:
        component = task_to_component[task]
        by_component[component] = ProvenanceRecord(
            component=component,
            input_hash=case_hash,
            duration_ms=durations.get(component, 0),
        )
    return [
        by_component[component]
        for component in task_to_component.values()
        if component in by_component
    ]


def _safe_error(exc: Exception) -> str:
    text = " ".join(str(exc).split()) or type(exc).__name__
    text = re.sub(
        r"(?i)(secret|token|password|credential|authorization)\s*[=:]\s*\S+",
        r"\1=[redacted]",
        text,
    )
    return text[:500]
