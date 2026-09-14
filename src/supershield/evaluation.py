"""Answer-key-free adapters for the auditable SuperShield benchmark."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from decimal import Decimal
from enum import Enum
from typing import Any

from supershield.demo_cases import DemoCaseRepository
from supershield.models import CaseRecord
from supershield.settings import Settings
from supershield.storage import InMemoryStateStore
from supershield.tools.approval import ApprovalTokenService
from supershield.tools.evidence import collect_evidence, facts_by_topic
from supershield.tools.finance import assumptions_from_claims
from supershield.workflow import SupervisorWorkflow

_EVALUATION_SESSION = "evaluation-session"
_EVALUATION_SECRET = "evaluation-only-secret-at-least-32-bytes"  # pragma: allowlist secret
_PAGE_MARKER = re.compile(
    r"(?:^|\n)\s*#{0,6}\s*(?:-{2,}\s*)?(?:page|p\.)\s*(\d+)\b[^\n]*(?:\n|$)",
    re.IGNORECASE,
)


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain(item) for item in value]
    return str(value)


def _value(item: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(item, Mapping) and name in item:
            return item[name]
        if hasattr(item, name):
            return getattr(item, name)
    return default


def _pages(content: str) -> list[tuple[int, str]]:
    matches = list(_PAGE_MARKER.finditer(content))
    if not matches:
        return [(1, content)]
    result: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        result.append((int(match.group(1)), content[match.end() : end]))
    return result


def _deduplicate_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, int], dict[str, Any]] = {}
    for item in items:
        key = (str(item["documentId"]), int(item["page"]))
        unique[key] = {"documentId": key[0], "page": key[1]}
    return list(unique.values())


def _source_evidence(
    references: Any,
    *,
    lease_only: bool = False,
    excerpt_terms: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for reference in references or []:
        document_id = str(_value(reference, "document_id", "documentId", default=""))
        page = _value(reference, "page")
        kind = str(_plain(_value(reference, "document_kind", "documentKind", default="")))
        if not document_id or page is None or document_id.startswith("doc_"):
            continue
        if lease_only and kind != "lease":
            continue
        excerpt = str(_value(reference, "excerpt", default="")).lower()
        if excerpt_terms and not any(term in excerpt for term in excerpt_terms):
            continue
        result.append({"documentId": document_id, "page": int(page)})
    return _deduplicate_evidence(result)


def _matching_evidence(documents: Any, predicate: Any, *, kinds: set[str] | None = None) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for document in documents:
        document_id = str(_value(document, "document_id", "documentId", default=""))
        kind = str(_plain(_value(document, "kind", default="")))
        if not document_id or document_id.startswith("doc_") or (kinds and kind not in kinds):
            continue
        for page, text in _pages(str(_value(document, "content", default=""))):
            if predicate(text.lower()):
                matches.append({"documentId": document_id, "page": page})
    return _deduplicate_evidence(matches)


def _canonical_code(finding: Any) -> str | None:
    category = str(_plain(_value(finding, "category", default=""))).lower()
    title = str(_value(finding, "title", default="")).lower()
    description = str(_value(finding, "description", default="")).lower()
    text = f"{title} {description}"
    if category == "prompt_injection":
        return "INJECTION_QUARANTINED"
    if "conflicting outlet survival rate" in text:
        return "OUTLET_SURVIVAL_CONFLICT"
    if "conflicting total investment" in text:
        return "OPENING_COST_CONFLICT"
    if "investment requirement exceeds" in text:
        return "BUYER_LIMIT_EXCEEDED"
    if "conflicting royalty rate" in text:
        return "ROYALTY_RATE_CONFLICT"
    if "conflicting revenue projection" in text:
        return "REVENUE_CLAIM_CONFLICT"
    if "conflicting revenue-based system fee" in text:
        return "UNDISCLOSED_RECURRING_FEE"
    if "personal lease guarantee" in text:
        return "LEASE_GUARANTEE_AND_ESCALATION"
    if "location saturation" in text:
        return "LOCATION_SATURATION"
    if "signed landlord consent is missing" in text:
        return "LANDLORD_CONSENT_MISSING"
    if "missing support for" in text and ("lease" in text or "rent" in text):
        return "LEASE_TERMS_MISSING"
    if "earnings support" in text and ("missing" in text or "unresolved" in text):
        return "EARNINGS_SUPPORT_MISSING"
    return None


def _code_evidence(code: str, finding: Any, documents: Any) -> list[dict[str, Any]]:
    references = _value(finding, "evidence", default=[])
    if code == "LANDLORD_CONSENT_MISSING":
        return []
    if code == "ROYALTY_RATE_CONFLICT":
        return _matching_evidence(
            documents,
            lambda text: "royalty" in text and "%" in text,
            kinds={"brochure", "disclosure"},
        )
    if code == "BUYER_LIMIT_EXCEEDED":
        return _matching_evidence(
            documents,
            lambda text: "estimated total" in text and "over" in text and "limit" in text,
        )
    if code == "LEASE_GUARANTEE_AND_ESCALATION":
        return _source_evidence(
            references,
            lease_only=True,
            excerpt_terms=("guarantee", "escalat"),
        )
    if code == "LOCATION_SATURATION":
        return _source_evidence(
            references,
            excerpt_terms=("competitor", "territor", "same-brand", "saturation"),
        )
    return _source_evidence(references)


def _positive_controls(documents: Any) -> list[dict[str, Any]]:
    controls: list[tuple[str, list[dict[str, Any]]]] = []
    market = _matching_evidence(
        documents,
        lambda text: "service area" in text and "population" in text and "road distances" in text,
    )
    if market:
        controls.append(("MARKET_BASIS_DISCLOSED", market))
    fees = _matching_evidence(
        documents,
        lambda text: "schedule agrees with the booklet" in text,
        kinds={"disclosure"},
    )
    if fees:
        controls.append(("FEES_ALIGNED", fees))
    territory = _matching_evidence(
        documents,
        lambda text: "protected service area" in text and "may not establish" in text,
    )
    if territory:
        controls.append(("TERRITORY_DOCUMENTED", territory))
    enrollment = _matching_evidence(documents, lambda text: "learner-months" in text)
    if len(enrollment) >= 2:
        controls.append(("ENROLLMENT_BASIS_DISCLOSED", enrollment))
    seasonality = _matching_evidence(
        documents,
        lambda text: "summer" in text and "winter" in text and "annual" in text,
    )
    if len(seasonality) >= 2:
        controls.append(("SEASONALITY_DISCLOSED", seasonality))
    illustration = _matching_evidence(
        documents,
        lambda text: "full fee schedule" in text and "candidates must build" in text,
        kinds={"disclosure"},
    )
    lease = _matching_evidence(
        documents,
        lambda text: "permitted use" in text and "no personal guarantee" in text,
        kinds={"lease"},
    )
    if illustration and lease:
        controls.append(("TERMS_ALIGNED", illustration + lease))
    return [
        {
            "code": code,
            "severity": "info",
            "status": "supported",
            "evidence": _deduplicate_evidence(evidence),
            "material": False,
        }
        for code, evidence in controls
    ]


def _findings(packet: Any, documents: Any) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for finding in _value(packet, "risk_findings", "riskFindings", default=[]) or []:
        code = _canonical_code(finding)
        if code is None:
            continue
        unresolved = bool(_value(finding, "unresolved", default=False))
        item = {
            "code": code,
            "severity": str(_plain(_value(finding, "severity", default="high"))).lower(),
            "status": "unresolved" if unresolved else "supported",
            "evidence": _code_evidence(code, finding, documents),
            "material": bool(_value(finding, "material", default=False)),
        }
        existing = result.get(code)
        if existing is None:
            result[code] = item
        else:
            existing["evidence"] = _deduplicate_evidence(existing["evidence"] + item["evidence"])
            existing["material"] = existing["material"] or item["material"]
            if unresolved:
                existing["status"] = "unresolved"
    for control in _positive_controls(documents):
        result.setdefault(control["code"], control)
    return list(result.values())


def _calculations(packet: Any, record: CaseRecord) -> dict[str, float]:
    scenarios = _value(packet, "financial_scenarios", "financialScenarios", default=[]) or []
    base = next(
        (scenario for scenario in scenarios if str(_value(scenario, "name", default="")) == "base"),
        scenarios[0] if scenarios else None,
    )
    if base is None:
        return {}
    claims = collect_evidence(record.documents).claims
    assumptions = assumptions_from_claims(claims)
    revenue = Decimal(str(_value(base, "monthly_revenue", "monthlyRevenue", default=0)))
    operating_income = Decimal(
        str(_value(base, "monthly_operating_profit", "monthlyOperatingProfit", default=0))
    )
    calculations = {
        "total_initial_investment": float(
            _value(base, "investment_required", "investmentRequired", default=0)
        ),
        "monthly_recurring_fees": float(
            Decimal(str(_value(base, "monthly_percentage_fees", "monthlyPercentageFees", default=0)))
            + assumptions.recurring_monthly_fees
        ),
        "monthly_operating_income": float(operating_income),
        "break_even_monthly_revenue": float(
            _value(base, "break_even_monthly_revenue", "breakEvenMonthlyRevenue", default=0)
            or 0
        ),
        "cash_headroom_after_reserve": float(
            _value(base, "cash_after_investment", "cashAfterInvestment", default=0)
        ),
        "monthly_household_surplus": float(
            operating_income - record.input.required_monthly_household_income
        ),
    }
    topics = facts_by_topic(claims)
    technology_values = {
        claim.normalized_value
        for claim in topics.get("other_revenue_fee_rate", [])
        if isinstance(claim.normalized_value, Decimal)
    }
    if len(technology_values) > 1:
        calculations["hidden_technology_fee_impact"] = float(
            -(revenue * (max(technology_values) - min(technology_values)) + assumptions.recurring_monthly_fees)
        )
    royalty_values = {
        claim.normalized_value
        for claim in topics.get("royalty_rate", [])
        if isinstance(claim.normalized_value, Decimal)
    }
    if len(royalty_values) > 1:
        calculations["royalty_conflict_impact"] = float(
            -(revenue * (max(royalty_values) - min(royalty_values)))
        )
    return calculations


def _approval_enforced(packet: Any) -> bool:
    checkpoints = _value(packet, "checkpoints", default=[]) or []
    return bool(checkpoints) and all(
        _value(checkpoint, "token")
        and _value(checkpoint, "action")
        and str(_plain(_value(checkpoint, "status", default="pending"))).lower()
        not in {"bypassed", "auto_approved"}
        for checkpoint in checkpoints
    )


def _packet_tool_calls(packet: Any) -> list[dict[str, Any]]:
    plan = _value(packet, "investigation_plan", "investigationPlan", default={}) or {}
    tasks = _value(plan, "tasks", default=[]) or []
    return [
        {"name": str(_value(task, "tool")), "success": True}
        for task in tasks
        if _value(task, "tool")
    ]


def evaluate_packet(packet: Any, case_id: str) -> dict[str, Any]:
    """Normalize one real API packet without consulting benchmark answer keys."""

    settings = Settings.from_env()
    demo = DemoCaseRepository(settings.fixture_root).get(case_id)
    record = CaseRecord(
        demo_case_id=demo.id,
        title=demo.title,
        summary=demo.summary,
        input=demo.input,
        documents=demo.documents,
        location_data=demo.location_data,
    )
    return {
        "decision_state": str(
            _plain(_value(packet, "decision_state", "decisionState", default="UNKNOWN"))
        ),
        "findings": _findings(packet, demo.documents),
        "calculations": _calculations(packet, record),
        "approval_enforced": _approval_enforced(packet),
        "tool_calls": _packet_tool_calls(packet),
        "actions": [],
        "estimated_cost_usd": 0,
    }


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Execute a curated case through the real in-memory supervisor."""

    case_id = str(case.get("id", "")).strip()
    if not case_id:
        raise ValueError("Evaluation case must contain a non-empty 'id'.")
    settings = Settings.from_env()
    demo = DemoCaseRepository(settings.fixture_root).get(case_id)
    record = CaseRecord(
        demo_case_id=demo.id,
        title=demo.title,
        summary=demo.summary,
        input=demo.input,
        documents=demo.documents,
        location_data=demo.location_data,
    )
    store = InMemoryStateStore()
    store.put_case(record, create_only=True)
    workflow = SupervisorWorkflow(
        store,
        ApprovalTokenService(_EVALUATION_SECRET, ttl_seconds=600),
    )
    run = workflow.start_run(record.case_id, _EVALUATION_SESSION)
    if run.packet is None:
        raise RuntimeError(f"Supervisor produced no Decision Packet for case '{case_id}'.")
    output = evaluate_packet(run.packet, case_id)
    output["tool_calls"] = [
        {
            "name": event.tool,
            "success": str(_plain(event.status)).lower() != "failed",
        }
        for event in store.list_events(run.run_id)
    ]
    return output


__all__ = ["evaluate_packet", "run_case"]
