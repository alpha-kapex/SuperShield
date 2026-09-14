# Complete implementation plan: SuperShield

## 1. Submission decision

**Track:** Professional Agents
**Product:** SuperShield — The Human Decision Firewall
**Core promise:** SuperShield investigates a franchise opportunity end to end, tests its claims against evidence and deterministic financial calculations, identifies missing information, and stops before the human's final decision.

SuperShield will be a new, standalone clean-room project, legally and technically isolated from any existing product.

## 2. Intellectual-property boundary

This repository is the standalone project. It must remain independently implemented.

```text
SuperShield/
├── src/supershield/
├── web/
├── fixtures/
├── evals/
├── infra/
├── docs/
├── tests/
├── README.md
├── LICENSE
└── .env.example
```

Mandatory safeguards:

- No copied third-party private source code, prompts, schemas, tests, documentation, UI components, assets, data, or Git history.
- No private imports, submodules, API calls, or runtime dependencies.
- Use fictional franchise documents and synthetic location/business data.
- Use independently designed public schemas and standard formulas.
- Run secret, license, dependency, and Git-history scans before publication.
- License only this isolated project under Apache-2.0.
- Keep any future product integration private and post-contest.

## 3. End-to-end experience

Use a fictional buyer named Priya:

1. Priya selects a synthetic franchise case.
2. She enters maximum investment, emergency reserve, required monthly household income, preferred location, and risk tolerance.
3. SuperShield creates an investigation plan.
4. Strands coordinates evidence, finance, location, and skepticism capabilities.
5. SuperShield finds a brochure claim conflicting with the disclosure, a recurring fee excluded from projections, a lease escalation or guarantee risk, a location saturation issue, and one genuinely missing fact.
6. SuperShield calculates the financial consequence.
7. Missing evidence blocks the case from advancing.
8. SuperShield drafts a targeted evidence request.
9. Priya explicitly approves the draft or test action.
10. New evidence is ingested and only affected analyses rerun.
11. SuperShield produces an auditable Decision Packet.

Decision states:

- `READY_FOR_EXPERT_REVIEW`
- `MORE_EVIDENCE_REQUIRED`
- `MATERIAL_RISK_IDENTIFIED`

Never output “buy,” “guaranteed,” or definitive legal/investment advice.

## 4. Technical architecture

```text
React public demo
       ↓
FastAPI BFF on AWS App Runner
       ↓
Amazon Bedrock AgentCore Runtime
       ↓
Strands SuperShield Supervisor
 ├─ Evidence Collector
 ├─ Skeptic/Contradiction Agent
 ├─ Deterministic Finance Tool
 ├─ Location-Risk Tool
 ├─ Evidence Validator
 └─ Human Approval Tool
       ↓
DynamoDB + temporary S3 + CloudWatch/OTel
```

### AWS choices

- Strands Agents SDK: Python
- Inference: Amazon Bedrock
- Primary model: Amazon Nova Pro through environment configuration
- Low-cost extraction tasks: Nova Lite
- Agent deployment: Bedrock AgentCore Runtime
- Web/API deployment: AWS App Runner
- Case state: DynamoDB with automatic expiry
- Temporary documents: encrypted S3 with short lifecycle
- Observability: AgentCore tracing and CloudWatch
- Optional approved test email: Amazon SES to a team-owned verified address

The public demo must not accept unrestricted documents or external recipients. It runs curated cases with strict request and token limits.

## 5. Strands implementation

Strands must be structurally essential in cloud mode. The deterministic local workflow mirrors the same bounded tool graph for development, tests, and replay.

### Supervisor

The SuperShield supervisor:

- Converts the user's constraints into a typed investigation plan.
- Delegates work through agents-as-tools.
- Tracks dependencies between findings.
- Pauses at evidence gaps or approval checkpoints.
- Selectively reruns affected tasks when inputs change.
- Produces the final structured Decision Packet.

### Specialist capabilities

**Evidence Collector**

- Extracts testable claims.
- Records document, page, excerpt, and content hash.
- Treats all uploaded text as untrusted data.

**Skeptic**

- Searches for contradictions and missing support.
- Attempts to disprove promotional claims.
- Cannot modify evidence or approve conclusions.

**Finance Tool**

- Implements standard formulas in deterministic Python.
- Calculates investment requirement, recurring fees, runway, break-even, and downside scenarios.
- Uses seeded simulations for reproducible tests.
- Never delegates arithmetic to the model.

**Location Tool**

- Uses synthetic geospatial fixtures.
- Calculates competitor density, travel radius, and indicative saturation.
- States that it is a screening tool, not professional site selection.

**Validator**

- Enforces “no evidence, no material conclusion.”
- Rejects invalid citations, unsupported numbers, and incomplete calculations.
- Forces correction or abstention.

**Approval Tool**

- Binds approval to the exact action, payload hash, case, expiry, and user session.
- Allows report export or a test evidence request only after approval.
- Prohibits signing, purchasing, payments, and real-world commitments.

## 6. Public interfaces

Core records:

```text
CaseInput
EvidenceReference
ClaimAssessment
RiskFinding
FinancialScenario
HumanCheckpoint
DecisionPacket
RunEvent
```

API surface:

```text
GET    /demo-cases
POST   /cases
POST   /cases/{caseId}/runs
GET    /runs/{runId}/events
POST   /runs/{runId}/approvals
POST   /runs/{runId}/evidence
GET    /cases/{caseId}/decision-packet
DELETE /cases/{caseId}
```

Use Server-Sent Events for safe progress updates. Display tool names, status, citations, and timings—never private chain-of-thought.

## 7. Product design

Build one polished workflow rather than a large dashboard:

- Human constraints form
- Investigation-plan preview
- Live agent activity timeline
- Claim-to-evidence relationships
- Contradiction and missing-evidence cards
- Financial scenario comparison
- “Why this changed” view after recalculation
- Human approval checkpoint
- Final Decision Packet
- Trace and provenance drawer
- Plain-language summary

Accessibility requirements:

- Keyboard navigation
- WCAG-compliant contrast
- Clear severity labels beyond color
- Responsive mobile layout
- Plain-language explanations

## 8. Evaluation suite

Create 12 synthetic cases:

- Four clean cases
- Four contradictory cases
- Two missing-evidence cases
- Two adversarial prompt-injection cases

Compare SuperShield with a single-agent summarization baseline.

Measure:

- Critical-risk recall
- Citation correctness
- Unsupported-claim rate
- Financial calculation accuracy
- Correct abstention/escalation rate
- Unauthorized-action count
- Tool-call success rate
- Latency and estimated Bedrock cost per case

Acceptance gates:

- 100% deterministic calculation accuracy
- At least 90% seeded critical-risk recall
- At least 95% citation correctness
- 100% approval enforcement
- Zero unauthorized consequential actions
- Prompt injection cannot change tools, policy, or decision thresholds
- Every material conclusion has evidence or is marked unresolved

## 9. Rule and judging compliance

| Contest requirement | Implementation |
|---|---|
| New AI agent | Entirely new clean-room SuperShield repository |
| Strands Agents SDK | Supervisor, specialists, tools, state, and approvals implemented with Strands |
| Real end-to-end work | Evidence intake through investigation, gap resolution, and final Decision Packet |
| Eligible track | Professional Agents |
| Public repository | Standalone GitHub repository |
| Complete source/assets/setup | Application, fixtures, infrastructure, tests, and setup instructions included |
| MIT or Apache license | Apache-2.0 file and repository setting |
| README | Problem, architecture, setup, security, evaluation, and demo instructions |
| Architecture diagram | SVG plus editable Mermaid source |
| Maximum five-minute video | Target 4:30 |
| Working demonstration | Real Strands execution and AgentCore trace in cloud mode; deterministic local mode for judges |
| Problem/who/why | Priya's life-savings story leads the presentation |
| AWS Builder ID | Added during submission |
| Optional live demo | Public, constrained App Runner deployment |
| Builder bonus | Publish an eligible AWS Builder article before the deadline |

### Judging optimisation

- **Technological Implementation:** Strands orchestration, AgentCore, stateful replanning, deterministic tools, observability, and deployment assets.
- **Design:** Complete decision workflow rather than a technical console.
- **Potential Impact:** Specific buyer, irreversible financial risk, and measured benchmark results.
- **Creativity:** Adversarial evidence testing and a policy-enforced decision firewall.
- **Presentation:** One memorable contradiction and its financial consequence shown end to end.

## 10. Five-minute video

- **0:00–0:25:** Priya and the human stakes
- **0:25–0:55:** Inputs and constraints
- **0:55–1:50:** Live Strands investigation
- **1:50–2:45:** Contradiction, hidden cost, and missing evidence
- **2:45–3:25:** Financial consequence and blocked decision
- **3:25–3:55:** Human approval and new evidence
- **3:55–4:20:** Selective re-analysis and Decision Packet
- **4:20–4:45:** AgentCore architecture, trace, and benchmark
- **4:45–4:55:** Closing statement
- **4:55–5:00:** Buffer

Closing line:

> “SuperShield does not make Priya's decision. It makes sure she never has to make it without evidence.”

## 11. Repository and submission assets

README must include:

- Problem and audience
- Why this requires an agent
- Feature walkthrough
- Strands architecture
- AgentCore deployment
- Local and AWS setup
- Environment-variable reference
- Demo-case instructions
- Evaluation results
- Security and human-control boundaries
- Cost estimate
- Known limitations
- License and data attribution

AWS Builder post title:

> **Agents for Humans: Building SuperShield, a Strands Decision Firewall for First-Time Franchise Buyers**

## 12. Delivery schedule

**Foundation**

- Create the clean repository and synthetic cases.
- Define schemas and evaluation answers.
- Implement finance and evidence tools.

**Agent workflow**

- Implement the Strands supervisor, skeptic, and validator.
- Add approval/resume and selective re-analysis workflows.
- Package for AgentCore.

**Experience and deployment**

- Build the polished React experience.
- Add App Runner assets, tracing, budgets, and failure handling.

**Proof and submission**

- Run evaluations and security tests.
- Complete the README and architecture diagram.
- Record the video, publish the Builder article, verify every public link, and complete the submission.

Do not build voice, generic chat, CRM, payments, multiple industries, ten agents, production integrations, or an expansive dashboard. One deeply proven decision workflow has the highest winning probability.
