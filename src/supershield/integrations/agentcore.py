"""Optional Bedrock AgentCore Runtime entrypoint for SuperShield."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from pydantic import Field

from supershield.api import ApplicationServices, build_services, create_case_record
from supershield.models import CreateCaseRequest, ShieldModel


class AgentCoreInvocation(ShieldModel):
    """Minimal bounded payload accepted by the managed runtime."""

    demo_case_id: str = Field(min_length=1, max_length=120)
    session_id: str = Field(min_length=8, max_length=200)


app = BedrockAgentCoreApp()


@lru_cache(maxsize=1)
def _services() -> ApplicationServices:
    return build_services()


@app.entrypoint
def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    """Run one curated investigation and return its auditable decision packet."""

    request = AgentCoreInvocation.model_validate(payload)
    services = _services()
    case = create_case_record(
        services,
        CreateCaseRequest(demo_case_id=request.demo_case_id),
    )
    run = services.workflow.start_run(case.case_id, request.session_id)
    if run.packet is None:
        raise RuntimeError("SuperShield completed without a decision packet")
    return {
        "caseId": case.case_id,
        "runId": run.run_id,
        "status": run.status.value,
        "mode": run.mode,
        "decisionPacket": run.packet.model_dump(mode="json", by_alias=True),
    }


if __name__ == "__main__":
    app.run()
