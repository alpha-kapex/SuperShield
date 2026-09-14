"""Deterministic extraction of citable, testable statements.

Document content is always handled as data.  Nothing in a document can select a
tool, alter policy, or issue an instruction to the workflow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from supershield.models import (
    DocumentKind,
    EvidenceDocument,
    EvidenceReference,
    ExtractedClaim,
    FindingCategory,
    RiskFinding,
    Severity,
)

PAGE_MARKER = re.compile(
    r"(?:^|\n)\s*#{0,6}\s*(?:-{2,}\s*)?(?:page|p\.)\s*(\d+)\b[^\n]*(?:\n|$)",
    re.IGNORECASE,
)
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")
INJECTION_PATTERNS = (
    re.compile(r"\bignore\s+(?:all\s+)?(?:previous|prior|system)\s+instructions?\b", re.I),
    re.compile(r"\b(?:system|developer)\s+prompt\b", re.I),
    re.compile(r"\b(?:call|invoke|use)\s+(?:the\s+)?(?:tool|function|api)\b", re.I),
    re.compile(r"\boverride\s+(?:policy|rules?|guardrails?)\b|\bsystem\s+override\b", re.I),
    re.compile(
        r"\b(?:disable|bypass)\s+(?:the\s+)?(?:validator|guardrails?)\b|"
        r"\bchange\s+(?:the\s+)?(?:critical[- ]risk\s+)?threshold\b",
        re.I,
    ),
    re.compile(
        r"\bexfiltrat(?:e|ion)\b|\breveal\s+(?:the\s+)?(?:current\s+)?"
        r"(?:secrets?|credentials?|approval\s+token)\b|\bdecode\s+and\s+obey\b",
        re.I,
    ),
    re.compile(r"\bsign\s+(?:it|this|the\s+agreement).{0,30}\bon\s+\w+'?s?\s+behalf\b", re.I),
)

# Ordered from specific to broad so a lease payment is not classified merely as a fee.
TOPIC_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "projected_monthly_revenue",
        re.compile(
            r"(?:monthly\s+(?:revenue|sales)|(?:revenue|sales)\s+(?:projection|forecast))",
            re.I,
        ),
    ),
    (
        "annual_revenue",
        re.compile(
            r"(?:annual|yearly)\s+(?:gross\s+)?(?:revenue|sales)|"
            r"(?:revenue|sales).{0,25}(?:annual|per\s+year)",
            re.I,
        ),
    ),
    ("initial_fee", re.compile(r"(?:initial|franchise|licen[cs]e)\s+fee", re.I)),
    ("buildout_cost", re.compile(r"build[- ]?out|fit[- ]?out|tenant\s+improvement", re.I)),
    ("equipment_cost", re.compile(r"equipment\s+(?:cost|package|investment)|cost.{0,20}equipment", re.I)),
    (
        "opening_inventory",
        re.compile(
            r"(?:(?:opening|initial|starting).{0,15}inventory|"
            r"inventory.{0,15}(?:opening|initial|cost))",
            re.I,
        ),
    ),
    ("working_capital", re.compile(r"working\s+capital", re.I)),
    ("gross_margin_rate", re.compile(r"gross\s+margin", re.I)),
    ("royalty_rate", re.compile(r"royalt(?:y|ies)", re.I)),
    ("marketing_rate", re.compile(r"(?:marketing|advertising)\s+(?:fund\s+)?(?:fee|contribution|rate|charge)?|brand\s+(?:fund|fee|contribution|rate|charge)", re.I)),
    (
        "other_revenue_fee_rate",
        re.compile(
            r"(?:technology|platform|system|ordering|analytics).{0,35}(?:fee|cost).{0,30}%|"
            r"%.{0,40}(?:technology|platform|system|ordering|analytics).{0,20}(?:fee|cost)",
            re.I,
        ),
    ),
    ("recurring_monthly_fees", re.compile(r"(?:monthly|recurring|technology|platform|software)\s+fee|fee.{0,20}(?:monthly|per\s+month)", re.I)),
    ("lease_escalation_rate", re.compile(r"(?:lease|rent).{0,35}(?:escalat|increase|annual\s+rise)|(?:escalat|increase).{0,25}(?:lease|rent)", re.I)),
    ("lease_monthly_cost", re.compile(r"(?:monthly\s+)?(?:lease|rent).{0,35}(?:month|monthly|payment|cost)|per\s+month.{0,25}(?:lease|rent)", re.I)),
    (
        "personal_guarantee_months",
        re.compile(r"\bpersonal(?:ly)?(?:\s+\w+){0,3}\s+guarant(?:ee|eed|ees|y|or)\b", re.I),
    ),
    (
        "fixed_monthly_costs",
        re.compile(
            r"(?:fixed\s+monthly|monthly\s+fixed|operating\s+monthly|"
            r"monthly\s+operating|overhead\s+monthly)\s+(?:costs?|expenses?)",
            re.I,
        ),
    ),
    ("break_even", re.compile(r"break[- ]?even|profitable\s+(?:within|after|by)", re.I)),
    ("protected_territory", re.compile(r"exclusive|protected\s+(?:service\s+area|territor)|territorial\s+protection", re.I)),
    ("competitor_count", re.compile(r"competitors?|competing\s+(?:sites?|units?|businesses?)", re.I)),
    ("same_brand_units", re.compile(r"same[- ]brand|existing\s+(?:brand\s+)?units?|franchise\s+units?\s+within", re.I)),
    ("population", re.compile(r"population|residents?", re.I)),
    ("outlet_survival_rate", re.compile(r"stay\s+open|remain(?:ed)?\s+open|survival\s+rate|ceased\s+operation", re.I)),
    ("earnings_support", re.compile(r"financial\s+performance\s+representation|unit[- ]level\s+revenue|earnings\s+support", re.I)),
    ("investment_range", re.compile(r"(?:total|required|estimated)\s+(?:initial\s+)?investment|open\s+for.{0,30}all[- ]in|estimated\s+total", re.I)),
)

MATERIAL_TOPICS = {
    "projected_monthly_revenue",
    "annual_revenue",
    "initial_fee",
    "buildout_cost",
    "equipment_cost",
    "working_capital",
    "gross_margin_rate",
    "royalty_rate",
    "marketing_rate",
    "recurring_monthly_fees",
    "lease_escalation_rate",
    "lease_monthly_cost",
    "personal_guarantee_months",
    "break_even",
    "protected_territory",
    "investment_range",
    "outlet_survival_rate",
    "earnings_support",
}


@dataclass(slots=True)
class EvidenceCollection:
    claims: list[ExtractedClaim] = field(default_factory=list)
    references: list[EvidenceReference] = field(default_factory=list)
    security_findings: list[RiskFinding] = field(default_factory=list)


def _split_pages(content: str) -> list[tuple[int, str]]:
    if "\f" in content:
        return [(index, page) for index, page in enumerate(content.split("\f"), start=1)]
    matches = list(PAGE_MARKER.finditer(content))
    if not matches:
        return [(1, content)]
    pages: list[tuple[int, str]] = []
    if content[: matches[0].start()].strip():
        pages.append((1, content[: matches[0].start()]))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        pages.append((int(match.group(1)), content[match.end() : end]))
    return pages


def _sentences(page_text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", part).strip(" \t-*•")
        for part in SENTENCE_BREAK.split(page_text)
        if len(re.sub(r"\s+", " ", part).strip(" \t-*•")) >= 8
    ]


def _reference(document: EvidenceDocument, page: int, excerpt: str) -> EvidenceReference:
    return EvidenceReference(
        document_id=document.document_id,
        document_title=document.title,
        document_kind=document.kind,
        page=page,
        excerpt=excerpt[:2_000],
        content_hash=document.content_hash,
        locator=f"page {page}",
    )


def _decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "").replace(" ", ""))
    except InvalidOperation:
        return None


def _scaled_number(raw: str, suffix: str | None = None) -> Decimal | None:
    value = _decimal(raw)
    if value is None:
        return None
    normalized_suffix = (suffix or "").lower()
    if normalized_suffix in {"million", "m"}:
        return value * Decimal("1000000")
    if normalized_suffix in {"thousand", "k"}:
        return value * Decimal("1000")
    return value


def _money_near(text: str, label: str) -> Decimal | None:
    token_pattern = (
        r"(?:\$|USD\s*|INR\s*|EUR\s*|GBP\s*)\s*"
        r"(\d[\d,]*(?:\.\d{1,2})?)\s*(million|thousand|[mk]\b)?"
    )
    labels = list(re.finditer(label, text, re.I))
    amounts = list(re.finditer(token_pattern, text, re.I))
    nearest: tuple[int, re.Match[str]] | None = None
    for label_match in labels:
        for amount_match in amounts:
            if amount_match.end() <= label_match.start():
                distance = label_match.start() - amount_match.end()
            elif label_match.end() <= amount_match.start():
                distance = amount_match.start() - label_match.end()
            else:
                distance = 0
            if distance <= 45 and (nearest is None or distance < nearest[0]):
                nearest = (distance, amount_match)
    if nearest is not None:
        return _scaled_number(nearest[1].group(1), nearest[1].group(2))
    return None


def _percent_near(text: str, label: str) -> Decimal | None:
    nearest: tuple[int, re.Match[str]] | None = None
    for label_match in re.finditer(label, text, re.I):
        clause_start = max(
            text.rfind(";", 0, label_match.start()),
            text.rfind(",", 0, label_match.start()),
        ) + 1
        clause_ends = [
            position
            for position in (
                text.find(";", label_match.end()),
                text.find(",", label_match.end()),
            )
            if position >= 0
        ]
        clause_end = min(clause_ends) if clause_ends else len(text)
        for percentage in re.finditer(
            r"(-?\d+(?:\.\d+)?)\s*%",
            text[clause_start:clause_end],
        ):
            absolute_start = clause_start + percentage.start()
            absolute_end = clause_start + percentage.end()
            if absolute_end <= label_match.start():
                distance = label_match.start() - absolute_end
            elif label_match.end() <= absolute_start:
                distance = absolute_start - label_match.end()
            else:
                distance = 0
            if distance <= 45 and (nearest is None or distance < nearest[0]):
                nearest = (distance, percentage)
    return _decimal(nearest[1].group(1)) if nearest is not None else None


def _guarantee_term(document_text: str) -> Decimal | None:
    match = re.search(
        r"\b(?:term|initial\s+term)\s+(?:is|of)\s+"
        r"(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve)\s*(years?|yrs?|months?|mos?)\b",
        document_text,
        re.I,
    )
    if not match:
        return None
    words = {
        "one": Decimal("1"),
        "two": Decimal("2"),
        "three": Decimal("3"),
        "four": Decimal("4"),
        "five": Decimal("5"),
        "six": Decimal("6"),
        "seven": Decimal("7"),
        "eight": Decimal("8"),
        "nine": Decimal("9"),
        "ten": Decimal("10"),
        "eleven": Decimal("11"),
        "twelve": Decimal("12"),
    }
    value = words.get(match.group(1).lower()) or _decimal(match.group(1))
    if value is None:
        return None
    return value * 12 if match.group(2).lower().startswith(("year", "yr")) else value


def _normalized_value(topic: str, text: str) -> Decimal | str | bool | None:
    lower = text.lower()
    if re.search(r"\b(?:not\s+(?:provided|disclosed|available)|unknown|tbd|to\s+be\s+determined)\b", lower):
        return None
    if topic == "earnings_support":
        missing = re.search(
            r"\b(?:no|does\s+not).{0,80}"
            r"(?:supplied|financial\s+performance\s+representation)",
            lower,
        )
        return None if missing else True
    if topic == "protected_territory":
        return not bool(
            re.search(
                r"\b(?:no|not|non[- ]exclusive|without)\b.{0,25}"
                r"\b(?:exclusive|protected|territor)",
                lower,
            )
        )
    if topic in {"royalty_rate", "marketing_rate", "other_revenue_fee_rate", "gross_margin_rate", "lease_escalation_rate"}:
        if topic == "other_revenue_fee_rate" and re.search(
            r"\b(?:no\s+row|omit(?:s|ted)?|exclude[sd]?)\b", lower
        ):
            return Decimal("0")
        rate_labels = {
            "royalty_rate": r"royalt(?:y|ies)",
            "marketing_rate": r"marketing|advertising|brand\s+fund",
            "other_revenue_fee_rate": r"technology|platform|system|ordering|analytics",
            "gross_margin_rate": r"gross\s+margin",
            "lease_escalation_rate": r"escalat|increase|annual\s+rise",
        }
        value = _percent_near(text, rate_labels[topic])
        return value / Decimal("100") if value is not None else None
    if topic == "personal_guarantee_months":
        if re.search(
            r"\b(?:no\s+personal\s+guarantee|not\s+personally\s+guaranteed|"
            r"personal\s+guarantee\s+(?:is\s+)?not\s+(?:required|requested))\b",
            lower,
        ):
            return Decimal("0")
        match = re.search(r"(\d+)\s*(?:months?|mos?\b)", text, re.I)
        if match:
            return _decimal(match.group(1))
        year_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?\b)", text, re.I)
        years = _decimal(year_match.group(1)) if year_match else None
        return years * 12 if years is not None else None
    if topic == "outlet_survival_rate":
        value = _percent_near(
            text,
            r"stay\s+open|remain(?:ed)?\s+open|survival\s+rate",
        )
        return value / Decimal("100") if value is not None else None
    if topic == "population":
        # Do not let a bare mention such as "no measured population" borrow
        # an unrelated number, such as annual sales, from the same sentence.
        if re.search(
            r"\b(?:no|without|unknown|undisclosed|unreported)\b.{0,30}"
            r"\b(?:measured\s+)?population\b",
            lower,
        ):
            return None
        population_patterns = (
            r"\bpopulation\s*(?:is|of|equals|:|=)?\s*(\d[\d,]*(?:\.\d+)?)\b",
            r"\b(\d[\d,]*(?:\.\d+)?)\s+(?:people|persons|residents?|population)\b",
        )
        for pattern in population_patterns:
            if match := re.search(pattern, text, re.I):
                return _decimal(match.group(1))
        return None
    if topic in {"competitor_count", "same_brand_units", "break_even"}:
        match = re.search(r"\b(\d[\d,]*(?:\.\d+)?)\b", text)
        return _decimal(match.group(1)) if match else text[:240]
    money_labels = {
        "projected_monthly_revenue": r"(?:monthly\s+(?:revenue|sales)|(?:revenue|sales)\s+(?:projection|forecast))",
        "annual_revenue": r"(?:annual|yearly)\s+(?:gross\s+)?(?:revenue|sales)|(?:revenue|sales).{0,20}(?:annual|per\s+year)",
        "initial_fee": r"(?:initial|franchise|licen[cs]e)\s+fee",
        "buildout_cost": r"build[- ]?out|fit[- ]?out|tenant\s+improvement",
        "equipment_cost": r"equipment\s+(?:cost|package|investment)|cost.{0,20}equipment",
        "opening_inventory": r"(?:opening|initial|starting).{0,15}inventory",
        "working_capital": r"working\s+capital",
        "recurring_monthly_fees": r"(?:recurring\s+monthly|monthly\s+technology|monthly\s+platform|monthly\s+software)\s+(?:fee|charge)",
        "fixed_monthly_costs": r"(?:fixed\s+monthly|monthly\s+fixed|operating\s+monthly|monthly\s+operating|overhead\s+monthly)\s+(?:costs?|expenses?)",
        "lease_monthly_cost": r"(?:monthly\s+)?(?:lease|rent).{0,20}(?:cost|payment|per\s+month)",
        "investment_range": r"(?:total|required|estimated)\s+(?:initial\s+)?investment|opening\s+budget|open\s+for.{0,30}all[- ]in|estimated\s+total",
    }
    if label := money_labels.get(topic):
        value = _money_near(text, label)
        if value is not None:
            return value / Decimal("12") if topic == "annual_revenue" else value
    money = re.search(
        r"(?:\$|USD\s*|INR\s*|EUR\s*|GBP\s*)\s*"
        r"(\d[\d,]*(?:\.\d{1,2})?)\s*(million|thousand|[mk]\b)?",
        text,
        re.I,
    )
    if money:
        value = _scaled_number(money.group(1), money.group(2))
        if value is not None and topic == "annual_revenue":
            return value / Decimal("12")
        return value
    number = re.search(r"\b(\d[\d,]*(?:\.\d+)?)\b", text)
    return _decimal(number.group(1)) if number else text[:240]


def _is_promotional(document: EvidenceDocument, text: str) -> bool:
    return document.kind == DocumentKind.BROCHURE or bool(
        re.search(r"\b(?:proven|leading|exceptional|strong|rapid|lucrative|success|opportunity)\b", text, re.I)
    )


def _topics(text: str) -> list[str]:
    return [topic for topic, pattern in TOPIC_RULES if pattern.search(text)]


def collect_evidence(documents: list[EvidenceDocument]) -> EvidenceCollection:
    """Extract claims and immutable citations from curated documents.

    Extraction is deliberately bounded and deterministic.  Prompt-like content
    becomes a security finding; it is never executed or forwarded as an instruction.
    """

    collection = EvidenceCollection()
    for document in documents:
        for page, page_text in _split_pages(document.content):
            for sentence in _sentences(page_text):
                reference: EvidenceReference | None = None
                if any(pattern.search(sentence) for pattern in INJECTION_PATTERNS):
                    reference = _reference(document, page, sentence)
                    collection.references.append(reference)
                    collection.security_findings.append(
                        RiskFinding(
                            category=FindingCategory.PROMPT_INJECTION,
                            title="Instruction-like document content isolated",
                            description=(
                                "The document contains text that attempts to influence the analysis "
                                "process. It was treated only as untrusted evidence data."
                            ),
                            severity=Severity.INFO,
                            material=False,
                            evidence=[reference],
                        )
                    )
                topics = _topics(sentence)
                if not topics:
                    continue
                if reference is None:
                    reference = _reference(document, page, sentence)
                    collection.references.append(reference)
                for topic in topics:
                    normalized_value = _normalized_value(topic, sentence)
                    if topic == "personal_guarantee_months" and normalized_value is None:
                        normalized_value = _guarantee_term(document.content)
                    collection.claims.append(
                        ExtractedClaim(
                            text=sentence,
                            topic=topic,
                            normalized_value=normalized_value,
                            unit=_unit_for_topic(topic),
                            material=topic in MATERIAL_TOPICS,
                            promotional=_is_promotional(document, sentence),
                            evidence=reference,
                        )
                    )
    return collection


def _unit_for_topic(topic: str) -> str | None:
    if topic.endswith("_rate"):
        return "ratio"
    if topic in {"competitor_count", "same_brand_units", "population"}:
        return "count"
    if topic == "personal_guarantee_months":
        return "months"
    if topic == "protected_territory":
        return "boolean"
    if topic in {
        "projected_monthly_revenue",
        "annual_revenue",
        "initial_fee",
        "buildout_cost",
        "equipment_cost",
        "opening_inventory",
        "working_capital",
        "recurring_monthly_fees",
        "lease_monthly_cost",
        "fixed_monthly_costs",
        "investment_range",
    }:
        return "currency"
    return None


def references_by_id(collection: EvidenceCollection) -> dict[str, EvidenceReference]:
    return {reference.reference_id: reference for reference in collection.references}


def facts_by_topic(claims: list[ExtractedClaim]) -> dict[str, list[ExtractedClaim]]:
    result: dict[str, list[ExtractedClaim]] = {}
    for claim in claims:
        result.setdefault(claim.topic, []).append(claim)
    return result


def as_safe_tool_payload(collection: EvidenceCollection) -> dict[str, Any]:
    """A compact, serializable result suitable for a bounded Strands tool."""

    return {
        "claims": [claim.model_dump(mode="json", by_alias=True) for claim in collection.claims],
        "securityFindings": [
            finding.model_dump(mode="json", by_alias=True)
            for finding in collection.security_findings
        ],
    }
