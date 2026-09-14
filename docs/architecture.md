# Architecture

SuperShield separates language-model judgment from deterministic policy and arithmetic. Strands is structurally essential in agent mode: its supervisor invokes bounded evidence, skepticism, finance, and location tools before deterministic validation and approval controls assemble the packet. Agent mode supports the verified local Ollama provider and an optional Bedrock provider. A deterministic local runtime mirrors the same graph for fast tests and replay.

![SuperShield architecture](architecture.svg)

The editable source is [`architecture.mmd`](architecture.mmd). The SVG is standalone, readable without Mermaid tooling, and uses text labels in addition to color.

## Trust boundaries

1. **Browser boundary.** The public-demo configuration exposes only curated synthetic cases, validates request size and schema, and never accepts an arbitrary recipient.
2. **BFF boundary.** App Runner binds the case, session, and approval. SSE exposes tool names, status, citations, and timing—not prompts or private reasoning.
3. **Agent boundary.** The verified local mode runs Strands with Ollama; the optional AWS deployment runs the same entrypoint in AgentCore. Evidence is always untrusted data. No evidence text can add tools, modify policy, change risk thresholds, or manufacture approval.
4. **Deterministic boundary.** Decimal formulas, citation existence checks, decision-state policy, and approval verification run as code. Models do not perform authoritative arithmetic.
5. **Data boundary.** Case records carry a 24-hour expiry; encrypted S3 evidence expires after one day; logs expire after 14 days. The application treats expiry as immediate even though AWS deletion is asynchronous.

## Control flow

- Evidence Collector records a document ID, page, excerpt, and content hash for every testable claim.
- Skeptic cannot edit evidence or approve a conclusion; it searches for conflicts and absent support.
- Finance and location tools return typed results with input provenance.
- Validator enforces “no evidence, no material conclusion.” A missing material fact becomes `unresolved` and the case cannot advance.
- Approval Tool signs an exact tuple of action, payload hash, case, user session, and expiry. It permits a decision-packet export or a test evidence request only; it never permits signing, purchasing, deposits, or real-world commitments.

The terminal states are `READY_FOR_EXPERT_REVIEW`, `MORE_EVIDENCE_REQUIRED`, and `MATERIAL_RISK_IDENTIFIED`. None means “buy,” and none substitutes for legal, accounting, lending, or site-selection advice.
