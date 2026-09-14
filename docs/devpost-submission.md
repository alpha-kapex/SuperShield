# Devpost submission draft

Submission target: [Agents for Humans](https://agentsforhumans.devpost.com/)
Track: **Professional Agents**

> Replace every `[VERIFY: ...]` marker before submission. Do not publish a metric, demo mode, or integration that has not been independently checked from the public URL and repository revision.

## Project name

**SuperShield — The Human Decision Firewall**

## Tagline

An evidence-first Strands agent that pressure-tests a franchise opportunity, calculates the consequences, and stops before the human's decision.

## One-line description

SuperShield coordinates specialist agents and deterministic tools to expose contradictions, hidden costs, missing evidence, and location risk in a franchise opportunity—then produces a cited Decision Packet for the buyer and their professionals.

## Inspiration

First-time franchise buyers face an information asymmetry at exactly the moment the stakes become personal. A glossy brochure, a long disclosure, a site proposal, and a spreadsheet may describe the same business with different assumptions. A conventional summary can make the pile feel shorter while leaving the dangerous inconsistency untouched.

We designed SuperShield around Priya, a fictional buyer protecting her life savings and monthly household income. She does not need an AI to make an irreversible decision for her. She needs a system that relentlessly asks, “What supports this claim, what contradicts it, what is missing, and what changes when we use the defensible number?”

## What it does

Priya selects one of twelve curated synthetic cases and enters her investment ceiling, emergency reserve, household-income requirement, location, and risk tolerance. SuperShield then:

1. builds a typed, dependency-aware investigation plan;
2. extracts claims with document/page provenance and content hashes;
3. asks a skeptic to find contradictions and missing support;
4. performs deterministic investment, recurring-fee, operating-income, break-even, and downside calculations;
5. screens a synthetic location for competitor density;
6. rejects unsupported material conclusions and pauses on evidence gaps;
7. drafts a targeted evidence request behind a payload-bound human approval; and
8. selectively reruns affected analysis when new evidence arrives, producing an auditable Decision Packet.

The only terminal states are `READY_FOR_EXPERT_REVIEW`, `MORE_EVIDENCE_REQUIRED`, and `MATERIAL_RISK_IDENTIFIED`. SuperShield never says “buy,” guarantees an outcome, or substitutes for legal, accounting, lending, or site-selection advice.

## The flagship moment

Saffron Route's brochure says “typical” kitchens reach $1.2 million in annual sales. Its synthetic disclosure reports a $720,000 median and says none of the measured kitchens reached $1.2 million. A provided projection omits a mandatory 4% platform fee plus $350 monthly. At the evidenced $60,000 monthly revenue, that omission is $2,750 a month; operating income becomes $1,450, which is $4,550 below Priya's household requirement. The lease adds 6% annual escalation and a ten-year personal guarantee, five competitors sit within four miles, and signed landlord consent is missing. SuperShield cites each fact, calculates the impact, and blocks advancement pending evidence.

## How we built it

- **Strands Agents SDK (Python):** the real supervisor delegates to evidence, skepticism, finance, location, validation, and approval capabilities as bounded tools.
- **Ollama + `qwen3:8b-q4_K_M`:** the live Strands provider on an AWS Graviton `t4g.large`, private to the instance's Docker network.
- **Amazon EC2 + nginx:** one short-lived instance serves the React/FastAPI origin through a rate-limited HTTP gateway; Systems Manager provides administration without SSH.
- **AWS CloudFormation + EventBridge + Lambda:** reproducible infrastructure with a fixed 2026-10-16 06:00 UTC compute-termination guardrail.
- **Amazon Bedrock / Amazon Nova and Bedrock AgentCore:** optional provider and deployment assets for future use; they are not part of the live demo.
- **FastAPI + Server-Sent Events:** exposes the constrained workflow and safe progress updates.
- **React:** presents constraints, plan, agent activity, evidence relationships, scenario changes, approval, and the Decision Packet.
- **In-memory state + curated fixtures:** the live deployment accepts no unrestricted uploads and retains no durable case database. Optional DynamoDB and encrypted S3 templates remain for a future architecture.

The default deterministic mode mirrors the same bounded tool graph for fast replay. The verified live Strands/Ollama mode invokes the actual SDK on EC2, while deterministic code remains authoritative for evidence validation and arithmetic.

## Why this needs an agent

The task is not one prompt over one document. Findings depend on multiple sources, calculations, skeptical checks, missing evidence, and human choices. When one document changes, only downstream work should rerun. Strands supplies the coordination, tool boundaries, checkpointing, and stateful replanning; deterministic code supplies policy and arithmetic authority.

## Human control and security

Evidence is untrusted input. Two benchmark documents explicitly try to change policy, reveal an approval token, send data externally, and sign an agreement. They cannot add tools, alter thresholds, access secrets, or create approval. Approval is bound to the exact action, payload hash, case, session, and expiry. The public demo has no unrestricted upload, arbitrary recipient, payment, signature, purchase, or production-integration capability. Live state is in memory, cases expire after 24 hours, and an app or instance restart clears all case state. The optional S3/DynamoDB design has separate lifecycle controls but is not deployed.

## Evaluation

The versioned suite contains exactly twelve fictional cases: four clean, four contradictory, two missing-evidence, and two adversarial-injection cases. It compares SuperShield with a single-pass summarization baseline and measures critical-risk recall, exact citation correctness, unsupported claims, deterministic calculation accuracy, correct abstention/escalation, approval enforcement, unauthorized actions, injection resistance, tool success, latency, and estimated Bedrock cost.

**Measured locally on 2026-09-14 through the real FastAPI workflow (`9dcbca6974b4e7d404fddd652e3f2373e87ba571`):**

- Critical-risk recall: `100%`
- Citation correctness: `100%`
- Unsupported-claim rate: `0%`
- Calculation accuracy: `100%`
- Correct abstention/escalation: `100%`
- Approval enforcement / unauthorized actions: `100% / 0`
- Prompt-injection resistance: `100%`
- Tool-call success: `100%`
- Mean / p95 latency: `93.41 ms / 98.70 ms`
- Inference cost: `$0` because this measured run used deterministic local mode

A separate live Priya run on release `79930702cfc740b51fe84b16a89eda43148314a1` completed through the real Strands Agents SDK and Ollama `qwen3:8b-q4_K_M` without fallback. It emitted the SSE `done` event and produced a valid `MORE_EVIDENCE_REQUIRED` packet with 6 findings, 4 scenarios, 29 evidence-index entries, and 2 human checkpoints. This is not a Bedrock or AgentCore performance claim. The dated metrics above remain local deterministic measurements; the repository's oracle mode is excluded from system-performance claims.

## Challenges

The hardest design choice was refusing to let fluent synthesis become authority. We built a typed evidence chain, separated the skeptic from the evidence record, moved money math into Decimal code, and made unresolved facts block material conclusions. Selective reruns also required explicit dependencies: changing landlord consent should not silently recompute unrelated revenue evidence.

## Accomplishments

- One coherent end-to-end decision workflow instead of a generic chat surface.
- Page-level provenance and a readable “Why this changed” history.
- Exact approval binding with no real-world commitment tools.
- Reproducible synthetic benchmark, including hostile evidence.
- A verified live EC2/Ollama deployment with SSM-only administration, encrypted storage, rate limiting, synthetic-only inputs, and scheduled compute termination.
- Optional AgentCore/App Runner architecture retained for future Bedrock-enabled deployment.

## What we learned

Human-centered agents become more useful when they are allowed to abstain. “I cannot support this yet” is not a failure state; for a life-changing financial decision, it is often the most valuable result. We also learned that a model-generated number and a model-generated citation are not evidence of correctness. Both need deterministic verification.

## What's next

After the competition, we would add expert-configurable policy packs, jurisdiction-aware document checklists, consented integrations for buyer-owned data, richer geospatial sources with clear licensing, and longitudinal evaluations. Those additions would preserve the same boundary: the agent investigates and prepares; a human decides and acts.

## Links

- Public repository: `https://github.com/alpha-kapex/SuperShield`
- Live constrained demo: [http://ec2-13-220-29-156.compute-1.amazonaws.com](http://ec2-13-220-29-156.compute-1.amazonaws.com) — HTTP-only; synthetic fixtures only
- Demo video (under five minutes): `[VERIFY: video URL]`
- AWS Builder article: `[VERIFY: published article URL]`
- Architecture: `docs/architecture.svg`
- Reproducible evaluation: `evals/README.md`

## Built with

Python, Strands Agents SDK, Ollama, Qwen3, FastAPI, React, TypeScript, Docker, nginx, AWS CloudFormation, Amazon EC2, AWS Systems Manager, Amazon EventBridge, and AWS Lambda. Optional, not-live assets cover Amazon Bedrock, Amazon Nova, Bedrock AgentCore Runtime, AWS App Runner, DynamoDB, Amazon S3, AWS KMS, Amazon ECR, and CloudWatch.

## Attribution and license

All franchise names, people, documents, addresses, financial figures, and location data are fictional and synthetic. No private product code, prompts, schemas, tests, documents, assets, data, or Git history were reused. SuperShield is licensed under Apache-2.0. See `docs/data-attribution.md`.
