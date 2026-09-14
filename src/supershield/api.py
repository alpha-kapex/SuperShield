"""FastAPI boundary for the curated SuperShield demonstration."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from supershield.demo_cases import DemoCaseNotFound, DemoCaseRepository
from supershield.integrations import StrandsSupervisorAdapter, integration_diagnostics
from supershield.models import (
    ApprovalRequest,
    ApprovalResult,
    CaseRecord,
    CreateCaseRequest,
    CreateRunRequest,
    DecisionPacket,
    DemoCaseSummary,
    EvidenceIngestRequest,
    HealthResponse,
    RunRecord,
    utc_now,
)
from supershield.settings import Settings
from supershield.storage import (
    DocumentBackedStateStore,
    DynamoDBStateStore,
    InMemoryStateStore,
    RecordNotFound,
    S3DocumentStore,
    StateStore,
)
from supershield.tools.approval import ApprovalError, ApprovalTokenService
from supershield.workflow import SupervisorWorkflow, WorkflowConflict


@dataclass(slots=True)
class ApplicationServices:
    settings: Settings
    demos: DemoCaseRepository
    store: StateStore
    workflow: SupervisorWorkflow
    storage_status: str
    strands: StrandsSupervisorAdapter | None


def build_services(
    settings: Settings | None = None,
    *,
    store: StateStore | None = None,
) -> ApplicationServices:
    settings = settings or Settings.from_env()
    storage_status = "memory"
    if store is None and settings.storage_backend == "dynamodb":
        try:
            if not settings.s3_bucket:
                raise RuntimeError("SUPERSHIELD_S3_BUCKET is required with DynamoDB storage")
            state = DynamoDBStateStore(
                settings.dynamodb_table, region_name=settings.aws_region
            )
            documents = S3DocumentStore(
                settings.s3_bucket,
                region_name=settings.aws_region,
                kms_key_id=settings.s3_kms_key_id,
            )
            store = DocumentBackedStateStore(state, documents)
            storage_status = store.name
        except Exception as exc:
            store = InMemoryStateStore()
            storage_status = f"memory fallback ({type(exc).__name__})"
    elif store is None:
        store = InMemoryStateStore()
    else:
        storage_status = store.name

    strands = (
        StrandsSupervisorAdapter(
            model_id=settings.bedrock_model_id,
            region_name=settings.aws_region,
            provider=settings.strands_provider,
            ollama_model=settings.ollama_model,
            ollama_host=settings.ollama_host,
        )
        if settings.execution_mode == "strands"
        else None
    )
    workflow = SupervisorWorkflow(
        store,
        ApprovalTokenService(
            settings.approval_secret,
            ttl_seconds=settings.approval_ttl_seconds,
        ),
        execution_mode=settings.execution_mode,
        strands_adapter=strands,
    )
    return ApplicationServices(
        settings=settings,
        demos=DemoCaseRepository(settings.fixture_root),
        store=store,
        workflow=workflow,
        storage_status=storage_status,
        strands=strands,
    )


def create_case_record(
    services: ApplicationServices, request: CreateCaseRequest
) -> CaseRecord:
    settings = services.settings
    if settings.public_demo and not request.demo_case_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The public demo accepts curated cases only.",
        )
    if request.documents and not settings.allow_inline_documents:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inline documents are disabled in the public demo.",
        )
    if request.demo_case_id:
        try:
            demo = services.demos.get(request.demo_case_id)
        except DemoCaseNotFound as exc:
            raise HTTPException(status_code=404, detail="Demo case not found") from exc
        input_ = request.input or demo.input
        documents = [*demo.documents, *request.documents]
        location_data = request.location_data or demo.location_data
        title = request.title or demo.title
        summary = request.summary or demo.summary
    else:
        if request.input is None:
            raise HTTPException(status_code=422, detail="Case input is required")
        input_ = request.input
        documents = request.documents
        location_data = request.location_data
        title = request.title or "Franchise investigation"
        summary = request.summary or "User-provided investigation"
    _validate_documents(settings, documents)
    case = CaseRecord(
        demo_case_id=request.demo_case_id,
        title=title,
        summary=summary,
        input=input_,
        documents=documents,
        location_data=location_data,
        expires_at=utc_now() + timedelta(seconds=settings.case_ttl_seconds),
    )
    services.store.put_case(case, create_only=True)
    return services.store.get_case(case.case_id)


def create_app(
    settings: Settings | None = None,
    *,
    store: StateStore | None = None,
) -> FastAPI:
    services = build_services(settings, store=store)
    application = FastAPI(
        title="SuperShield API",
        version="0.1.0",
        description=(
            "Evidence-bound franchise investigation API. Outputs support human and "
            "qualified expert review; they are not legal or investment advice."
        ),
    )
    application.state.services = services
    application.add_middleware(
        CORSMiddleware,
        allow_origins=services.settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    router = APIRouter()

    @router.get("/health", response_model=HealthResponse)
    @router.get("/healthz", response_model=HealthResponse)
    def health() -> HealthResponse:
        diagnostics = integration_diagnostics(
            services.strands,
            execution_mode=services.settings.execution_mode,
        )
        degraded = (
            "fallback" in services.storage_status
            or (services.strands is not None and services.strands.last_error is not None)
        )
        return HealthResponse(
            status="degraded" if degraded else "ok",
            mode=services.settings.execution_mode,
            storage=services.storage_status,
            optional_integrations=diagnostics,
        )

    @router.get("/demo-cases", response_model=list[DemoCaseSummary])
    def list_demo_cases() -> list[DemoCaseSummary]:
        return services.demos.list()

    @router.post(
        "/cases",
        response_model=CaseRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def create_case(request: CreateCaseRequest) -> CaseRecord:
        return create_case_record(services, request)

    @router.post(
        "/cases/{case_id}/runs",
        response_model=RunRecord,
        status_code=status.HTTP_201_CREATED,
    )
    def start_run(case_id: str, request: CreateRunRequest) -> RunRecord:
        try:
            return services.workflow.start_run(case_id, request.session_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="Case not found") from exc

    @router.get("/runs/{run_id}/events")
    async def run_events(
        run_id: str,
        after: Annotated[int, Query(ge=0)] = 0,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        if last_event_id:
            try:
                after = max(after, int(last_event_id))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid Last-Event-ID") from exc
        try:
            services.store.get_run(run_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

        async def stream() -> Any:
            cursor = after
            while True:
                try:
                    events = services.store.list_events(
                        run_id, after_sequence=cursor
                    )
                    run = services.store.get_run(run_id)
                except RecordNotFound:
                    yield _sse("error", {"detail": "Run no longer exists"})
                    return
                for event in events:
                    cursor = event.sequence
                    yield _sse(
                        "run_event",
                        event.model_dump(mode="json", by_alias=True),
                        event_id=event.sequence,
                    )
                if run.status.terminal:
                    yield _sse(
                        "done",
                        {
                            "runId": run.run_id,
                            "status": run.status.value,
                            "revision": run.revision,
                        },
                    )
                    return
                yield ": keep-alive\n\n"
                await asyncio.sleep(0.25)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post(
        "/runs/{run_id}/approvals",
        response_model=ApprovalResult,
    )
    def approve(run_id: str, request: ApprovalRequest) -> ApprovalResult:
        try:
            return services.workflow.approve(run_id, request)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except (ApprovalError, WorkflowConflict) as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/runs/{run_id}/evidence", response_model=RunRecord)
    def ingest_evidence(run_id: str, request: EvidenceIngestRequest) -> RunRecord:
        _validate_documents(services.settings, request.documents)
        try:
            run = services.store.get_run(run_id)
            case = services.store.get_case(run.case_id)
            replacements = {item.document_id for item in request.documents}
            resulting_count = sum(
                item.document_id not in replacements for item in case.documents
            ) + len(request.documents)
            if resulting_count > services.settings.max_documents_per_case:
                raise HTTPException(status_code=413, detail="Too many documents")
            return services.workflow.ingest_evidence(
                run_id,
                session_id=request.session_id,
                documents=request.documents,
            )
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except WorkflowConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get(
        "/cases/{case_id}/decision-packet",
        response_model=DecisionPacket,
    )
    def decision_packet(case_id: str) -> DecisionPacket:
        try:
            runs = services.store.list_runs(case_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="Case not found") from exc
        completed = [run for run in runs if run.packet is not None]
        if not completed:
            raise HTTPException(status_code=409, detail="No decision packet is available")
        return max(completed, key=lambda run: (run.updated_at, run.revision)).packet

    @router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_case(case_id: str) -> Response:
        if not services.store.delete_case(case_id):
            raise HTTPException(status_code=404, detail="Case not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    application.include_router(router)
    _mount_spa(application)
    return application


def _validate_documents(settings: Settings, documents: list[Any]) -> None:
    if len(documents) > settings.max_documents_per_case:
        raise HTTPException(status_code=413, detail="Too many documents")
    seen: set[str] = set()
    for document in documents:
        if document.document_id in seen:
            raise HTTPException(status_code=422, detail="Document IDs must be unique")
        seen.add(document.document_id)
        if len(document.content.encode("utf-8")) > settings.max_document_bytes:
            raise HTTPException(status_code=413, detail="A document exceeds the size limit")


def _sse(event: str, payload: dict[str, Any], *, event_id: int | None = None) -> str:
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}event: {event}\ndata: {data}\n\n"


def _mount_spa(application: FastAPI) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    working_root = Path.cwd().resolve()
    candidates = [working_root / "web" / "dist", repository_root / "web" / "dist"]
    dist = next((path for path in candidates if (path / "index.html").is_file()), None)
    if dist is None:
        return
    assets = dist / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="assets")

    @application.get("/{spa_path:path}", include_in_schema=False)
    def spa_fallback(spa_path: str) -> FileResponse:
        requested = (dist / spa_path).resolve()
        if (
            spa_path
            and requested.is_relative_to(dist)
            and requested.is_file()
            and requested.name != "index.html"
        ):
            return FileResponse(requested)
        return FileResponse(dist / "index.html")


app = create_app()
