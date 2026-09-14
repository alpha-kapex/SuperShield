# Architecture

SuperShield separates language-model coordination from deterministic policy and arithmetic. The verified judging deployment runs the React app, FastAPI API, Strands supervisor, and a private Ollama `qwen3:8b-q4_K_M` service on one AWS Graviton EC2 instance.

> Live demo: [http://ec2-13-220-29-156.compute-1.amazonaws.com](http://ec2-13-220-29-156.compute-1.amazonaws.com). This endpoint is HTTP-only and accepts only the included synthetic cases. Never enter real or sensitive data.

![SuperShield architecture](architecture.svg)

The editable source is [`architecture.mmd`](architecture.mmd). The SVG is standalone and uses text labels in addition to color.

## Deployed runtime

1. **Browser boundary.** The React interface offers exactly 12 curated synthetic cases and no unrestricted upload path.
2. **Gateway boundary.** A rate-limited nginx container is the only public application listener on TCP 80. It adds browser security headers and proxies to FastAPI over a private Docker network.
3. **Application boundary.** FastAPI binds case, session, approval, and expiry. State is intentionally in memory, so application or instance restarts clear cases and approvals.
4. **Agent boundary.** Strands coordinates the Evidence Collector, Skeptic, deterministic Finance, and Location tools through private Ollama inference. Tool results returned to the model are compact receipts; the authoritative results are recomputed and validated in Python.
5. **Deterministic boundary.** Decimal formulas, citation existence checks, evidence sufficiency, decision-state policy, and approval-token verification run as code. The model cannot approve a transaction or perform authoritative arithmetic.
6. **Operations boundary.** AWS Systems Manager is the administrative route; there is no SSH listener. EventBridge invokes a narrowly scoped Lambda at 2026-10-16 06:00 UTC to terminate the EC2 instance and its encrypted root volume.

The terminal states are `READY_FOR_EXPERT_REVIEW`, `MORE_EVIDENCE_REQUIRED`, and `MATERIAL_RISK_IDENTIFIED`. None means “buy,” and none substitutes for legal, accounting, lending, or site-selection advice.

## Optional future architecture

The repository retains CloudFormation and adapters for a future App Runner, Bedrock AgentCore, DynamoDB, S3, and CloudWatch design. Those services are **not deployed** for the current judging demo; CloudFront is also not deployed.
