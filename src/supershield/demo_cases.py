"""Safe loader for repository-owned, fictional demo cases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from supershield.models import (
    CaseInput,
    CompetitorLocation,
    DemoCaseSummary,
    DocumentKind,
    EvidenceDocument,
    LocationData,
)


class DemoCaseNotFound(KeyError):
    pass


class InvalidDemoCase(ValueError):
    pass


@dataclass(slots=True)
class DemoCase:
    id: str
    title: str
    summary: str
    tags: list[str]
    input: CaseInput
    documents: list[EvidenceDocument]
    location_data: LocationData | None


class DemoCaseRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def list(self) -> list[DemoCaseSummary]:
        summaries: list[DemoCaseSummary] = []
        for manifest in self._manifests():
            try:
                demo = self._load_manifest(manifest)
            except (InvalidDemoCase, OSError, json.JSONDecodeError):
                continue
            summaries.append(
                DemoCaseSummary(
                    id=demo.id,
                    title=demo.title,
                    summary=demo.summary,
                    tags=demo.tags,
                    document_count=len(demo.documents),
                )
            )
        return sorted(summaries, key=lambda item: item.id)

    def get(self, demo_case_id: str) -> DemoCase:
        if not demo_case_id or any(part in demo_case_id for part in ("..", "/", "\\")):
            raise DemoCaseNotFound(demo_case_id)
        for manifest in self._manifests():
            try:
                raw = self._read_json(manifest)
            except (OSError, json.JSONDecodeError):
                continue
            candidate_id = str(
                raw.get("id") or raw.get("caseId") or raw.get("case_id") or manifest.parent.name
            )
            if candidate_id == demo_case_id:
                return self._load_manifest(manifest, raw=raw)
        raise DemoCaseNotFound(demo_case_id)

    def _manifests(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        results: list[Path] = []
        for path in self.root.rglob("case.json"):
            try:
                if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                    continue
            except OSError:
                continue
            results.append(path)
        return sorted(results)

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.resolve().is_relative_to(self.root):
            raise InvalidDemoCase("manifest path leaves fixture root")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise InvalidDemoCase("case manifest must be an object")
        return value

    def _load_manifest(
        self, manifest: Path, *, raw: dict[str, Any] | None = None
    ) -> DemoCase:
        raw = raw or self._read_json(manifest)
        demo_id = str(raw.get("id") or raw.get("caseId") or raw.get("case_id") or manifest.parent.name)
        title = str(raw.get("title") or raw.get("name") or demo_id.replace("-", " ").title())
        summary = str(raw.get("summary") or raw.get("description") or "Curated fictional case")
        tags = [str(item) for item in raw.get("tags", [])]
        category = raw.get("category")
        if category and str(category) not in tags:
            tags.append(str(category))
        if raw.get("flagship") and "flagship" not in tags:
            tags.append("flagship")
        input_value = _case_input(raw.get("input") or raw.get("caseInput") or raw.get("constraints") or raw)
        documents = self._documents(manifest.parent, raw.get("documents"))
        location_raw = raw.get("locationData") or raw.get("location_data") or raw.get("location")
        location_data = _location_data(location_raw, input_value.preferred_location)
        if location_data is not None and not any(doc.kind == DocumentKind.LOCATION for doc in documents):
            documents.append(_location_document(demo_id, location_data))
        financial_raw = (
            raw.get("financialData")
            or raw.get("financial_data")
            or raw.get("finance_inputs")
            or raw.get("financials")
        )
        if financial_raw:
            documents.append(_financial_document(demo_id, financial_raw))
        if not documents:
            raise InvalidDemoCase(f"Demo case {demo_id!r} has no documents")
        return DemoCase(
            id=demo_id,
            title=title,
            summary=summary,
            tags=tags,
            input=input_value,
            documents=documents,
            location_data=location_data,
        )

    def _documents(
        self, case_directory: Path, configured: Any
    ) -> list[EvidenceDocument]:
        entries: list[Any]
        if configured is None:
            document_directory = case_directory / "documents"
            entries = sorted(document_directory.glob("*.md")) if document_directory.is_dir() else []
        elif isinstance(configured, list):
            entries = configured
        else:
            raise InvalidDemoCase("documents must be a list")
        documents: list[EvidenceDocument] = []
        for index, entry in enumerate(entries):
            if isinstance(entry, Path):
                relative_path, metadata = entry.relative_to(case_directory), {}
            elif isinstance(entry, str):
                relative_path, metadata = Path(entry), {}
            elif isinstance(entry, dict):
                metadata = entry
                path_value = entry.get("path") or entry.get("file") or entry.get("filename")
                if not path_value and entry.get("content"):
                    documents.append(_inline_document(entry, index))
                    continue
                if not path_value:
                    raise InvalidDemoCase("document entry needs path or content")
                relative_path = Path(str(path_value))
            else:
                raise InvalidDemoCase("invalid document entry")
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise InvalidDemoCase("document path must remain inside its demo case")
            path = (case_directory / relative_path).resolve()
            if not path.is_relative_to(case_directory.resolve()) or not path.is_relative_to(self.root):
                raise InvalidDemoCase("document path leaves fixture root")
            if path.is_symlink() or not path.is_file():
                raise InvalidDemoCase(f"document not found: {relative_path}")
            content = path.read_text(encoding="utf-8")
            documents.append(
                EvidenceDocument(
                    document_id=str(
                        metadata.get("documentId")
                        or metadata.get("document_id")
                        or metadata.get("id")
                        or f"doc_{index + 1}_{path.stem}"
                    ),
                    title=str(metadata.get("title") or path.stem.replace("_", " ").title()),
                    kind=_document_kind(metadata.get("kind") or _kind_from_name(path.stem)),
                    content=content,
                    source=f"fixture:{relative_path.as_posix()}",
                    metadata={"relativePath": relative_path.as_posix()},
                )
            )
        return documents


def _get(raw: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in raw:
            return raw[name]
    return default


def _case_input(raw: Any) -> CaseInput:
    if not isinstance(raw, dict):
        raise InvalidDemoCase("case input must be an object")
    location = _get(raw, "preferredLocation", "preferred_location", "location", default="Synthetic district")
    if isinstance(location, dict):
        location = _get(location, "name", "label", "address", default="Synthetic district")
    try:
        return CaseInput(
            buyer_name=_get(raw, "buyerName", "buyer_name", "buyer", default="Priya"),
            cash_available=_get(raw, "cashAvailable", "cash_available"),
            maximum_investment=_get(
                raw,
                "maximumInvestment",
                "maximum_investment",
                "maxInvestment",
                "investmentLimit",
                default="250000",
            ),
            emergency_reserve=_get(
                raw, "emergencyReserve", "emergency_reserve", "reserve", default="30000"
            ),
            required_monthly_household_income=_get(
                raw,
                "requiredMonthlyHouseholdIncome",
                "required_monthly_household_income",
                "requiredMonthlyIncome",
                "monthlyIncomeNeed",
                default="5000",
            ),
            preferred_location=str(location),
            risk_tolerance=_get(
                raw, "riskTolerance", "risk_tolerance", default="low"
            ),
            currency=str(_get(raw, "currency", default="USD")).upper(),
        )
    except Exception as exc:
        raise InvalidDemoCase(f"invalid case input: {exc}") from exc


def _document_kind(raw: Any) -> DocumentKind:
    value = str(raw or "other").lower().replace("_", "-")
    aliases = {
        "fdd": DocumentKind.DISCLOSURE,
        "disclosure-document": DocumentKind.DISCLOSURE,
        "projection": DocumentKind.FINANCIAL,
        "financial-projection": DocumentKind.FINANCIAL,
        "site": DocumentKind.LOCATION,
        "email": DocumentKind.CORRESPONDENCE,
    }
    if value in aliases:
        return aliases[value]
    try:
        return DocumentKind(value)
    except ValueError:
        return DocumentKind.OTHER


def _kind_from_name(name: str) -> str:
    lower = name.lower()
    for marker, kind in (
        ("brochure", "brochure"),
        ("disclosure", "disclosure"),
        ("fdd", "disclosure"),
        ("financial", "financial"),
        ("projection", "financial"),
        ("lease", "lease"),
        ("location", "location"),
        ("email", "correspondence"),
    ):
        if marker in lower:
            return kind
    return "other"


def _inline_document(entry: dict[str, Any], index: int) -> EvidenceDocument:
    return EvidenceDocument(
        document_id=str(entry.get("documentId") or entry.get("id") or f"doc_{index + 1}"),
        title=str(entry.get("title") or f"Document {index + 1}"),
        kind=_document_kind(entry.get("kind")),
        content=str(entry["content"]),
        source="fixture:inline",
    )


def _location_data(raw: Any, preferred_location: str) -> LocationData | None:
    if not isinstance(raw, dict):
        return None
    competitors_raw = _get(raw, "competitors", "nearbyCompetitors", default=[])
    competitors: list[CompetitorLocation] = []
    if isinstance(competitors_raw, int):
        competitors = [
            CompetitorLocation(name=f"Synthetic competitor {index + 1}", distance_km=Decimal("5"))
            for index in range(competitors_raw)
        ]
    elif isinstance(competitors_raw, list):
        for index, item in enumerate(competitors_raw):
            if isinstance(item, dict):
                distance = _get(
                    item,
                    "distanceKm",
                    "distance_km",
                    "distance",
                    default=None,
                )
                if distance is None and _get(item, "distanceMiles", "distance_miles") is not None:
                    distance = Decimal(
                        str(_get(item, "distanceMiles", "distance_miles"))
                    ) * Decimal("1.609344")
                competitors.append(
                    CompetitorLocation(
                        name=str(item.get("name") or f"Synthetic competitor {index + 1}"),
                        distance_km=distance if distance is not None else "5",
                        category=str(item.get("category") or "direct"),
                    )
                )
    radius = _get(raw, "radiusKm", "radius_km", "travelRadiusKm", default=None)
    if radius is None and _get(raw, "market_area_sq_miles") is not None:
        # The fixture's market area is an area, not a literal radius.
        radius = "5"
    return LocationData(
        location_name=str(_get(raw, "locationName", "location_name", "name", default=preferred_location)),
        population=_get(raw, "population", "targetPopulation"),
        radius_km=radius or "5",
        competitors=competitors,
        same_brand_units=_get(raw, "sameBrandUnits", "same_brand_units", default=0),
        protected_territory=_get(raw, "protectedTerritory", "protected_territory"),
        source=str(raw.get("source") or "synthetic fixture"),
    )


def _location_document(demo_id: str, data: LocationData) -> EvidenceDocument:
    competitors_in_radius = sum(
        1 for competitor in data.competitors if competitor.distance_km <= data.radius_km
    )
    content = [
        "Synthetic location screening dataset.",
        f"Population: {data.population if data.population is not None else 'not provided'}.",
        f"Direct competitors: {competitors_in_radius} within {data.radius_km} km.",
        f"Same-brand units: {data.same_brand_units} within {data.radius_km} km.",
    ]
    if data.protected_territory is not None:
        content.append(
            "Protected territory: yes."
            if data.protected_territory
            else "Protected territory: no."
        )
    return EvidenceDocument(
        document_id=f"doc_{demo_id}_location_data",
        title="Synthetic location dataset",
        kind=DocumentKind.LOCATION,
        content="\n".join(content),
        source="fixture:structured-location",
    )


def _financial_document(demo_id: str, raw: Any) -> EvidenceDocument:
    if not isinstance(raw, dict):
        raise InvalidDemoCase("financial data must be an object")
    labels = {
        "initialFee": "Initial franchise fee",
        "initial_fee": "Initial franchise fee",
        "franchise_fee": "Initial franchise fee",
        "buildoutCost": "Build-out cost",
        "buildout_cost": "Build-out cost",
        "buildout": "Build-out cost",
        "equipmentCost": "Equipment cost",
        "equipment_cost": "Equipment cost",
        "equipment": "Equipment cost",
        "opening_inventory": "Opening inventory",
        "other_opening_costs": "Working capital and other startup costs",
        "workingCapital": "Working capital",
        "working_capital": "Working capital",
        "projectedMonthlyRevenue": "Monthly revenue projection",
        "projected_monthly_revenue": "Monthly revenue projection",
        "monthly_revenue": "Monthly revenue projection per month",
        "grossMarginRate": "Gross margin",
        "gross_margin_rate": "Gross margin",
        "royaltyRate": "Royalty rate",
        "royalty_rate": "Royalty rate",
        "marketingRate": "Marketing fee",
        "marketing_rate": "Marketing fee",
        "technology_rate": "Technology system fee",
        "technology_fixed": "Recurring monthly technology fee",
        "recurringMonthlyFees": "Recurring monthly fee",
        "recurring_monthly_fees": "Recurring monthly fee",
        "fixedMonthlyCosts": "Fixed monthly costs",
        "fixed_monthly_costs": "Fixed monthly costs",
        "leaseMonthlyCost": "Monthly lease cost",
        "lease_monthly_cost": "Monthly lease cost",
        "rent": "Monthly lease cost",
    }
    lines = ["Structured fictional financial assumptions."]
    for key, value in raw.items():
        if key not in labels:
            continue
        if value is None:
            lines.append(f"{labels[key]}: not provided.")
            continue
        if "Rate" in key or key.endswith("_rate"):
            decimal = Decimal(str(value))
            rendered = f"{decimal * 100}%" if decimal <= 1 else f"{decimal}%"
        else:
            rendered = f"${Decimal(str(value)):,.2f}"
        lines.append(f"{labels[key]}: {rendered}.")
    if "cogs_rate" in raw and raw["cogs_rate"] is not None:
        gross_margin = (Decimal("1") - Decimal(str(raw["cogs_rate"]))) * Decimal("100")
        lines.append(f"Gross margin: {gross_margin}%.")
    fixed_keys = ("payroll", "utilities", "insurance", "other_fixed")
    fixed_values = [raw.get(key) for key in fixed_keys]
    if all(value is not None for value in fixed_values):
        fixed_total = sum((Decimal(str(value)) for value in fixed_values), Decimal("0"))
        lines.append(f"Fixed monthly costs: ${fixed_total:,.2f}.")
    return EvidenceDocument(
        document_id=f"doc_{demo_id}_financial_data",
        title="Structured fictional financial data",
        kind=DocumentKind.FINANCIAL,
        content="\n".join(lines),
        source="fixture:structured-financial",
    )
