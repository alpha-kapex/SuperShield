# Agents for Humans: Building SuperShield, a Strands Decision Firewall for First-Time Franchise Buyers

_Draft for AWS Builder Center. Replace every `[VERIFY]` marker and rerun the public revision before publication._

Buying a franchise can look like a document-review problem: summarize the brochure, disclosure, financial worksheet, proposed lease, and local market notes. That framing misses the dangerous part. The same claim can appear with different definitions in different documents; a single omitted recurring fee can invalidate a projection; and the fact a buyer most needs may not be present at all.

For the [Agents for Humans](https://agentsforhumans.devpost.com/) hackathon's **Professional Agents** track, we built **SuperShield**, an evidence-first agent for a fictional first-time buyer named Priya. It does not tell Priya what to buy. It constructs an investigation, tests claims against source evidence, performs deterministic financial calculations, identifies what remains unknown, and stops before her final decision.

That last boundary shaped the whole architecture.

## From a summary to an investigation

A single-agent summary has no natural place to encode dependencies. If a lease changes, which conclusions are invalid? If a revenue claim lacks a population and period, should a fluent paragraph still repeat it? If promotional text says to ignore previous instructions, what prevents source content from changing the workflow?

SuperShield uses a Strands supervisor because this work is a graph, not a prompt:

```text
buyer constraints
  → evidence claims and provenance
  → skeptical contradiction search
  → deterministic financial and location tools
  → evidence validation
  → human checkpoint when action or evidence is needed
  → selectively updated Decision Packet
```

The supervisor owns planning and dependencies. Specialist capabilities have narrow permissions:

- The **Evidence Collector** extracts a testable claim plus document ID, page, excerpt, and content hash. It cannot approve the claim.
- The **Skeptic** tries to disprove important claims and locate missing support. It cannot edit evidence.
- The **Finance Tool** uses Decimal arithmetic for initial investment, recurring fees, operating income, break-even, cash headroom, and downside scenarios. The language model never becomes the calculator of record.
- The **Location Tool** computes competitor density and travel radius from synthetic data, clearly labeling the result as screening rather than professional site selection.
- The **Validator** rejects invalid citations and unsupported material conclusions. “No evidence” becomes `unresolved`, not an invented answer.
- The **Approval Tool** binds an action to its payload hash, case, user session, and expiry. It permits only a report export or a test evidence request.

In the verified judging deployment, the supervisor runs through the Strands Agents SDK against a private Ollama `qwen3:8b-q4_K_M` service on one AWS Graviton EC2 instance. A deterministic local runtime mirrors the same graph for fast tests and replay. Bedrock, Amazon Nova, and Bedrock AgentCore remain optional future providers and are not part of the live demo.

## A contradiction with a price tag

Our flagship dataset is fictional by design. Priya is considering Saffron Route Kitchen with $280,000 available, a protected $45,000 emergency reserve, a $225,000 investment ceiling, and a $6,000 monthly household-income requirement.

The promotional brochure says “typical” kitchens reach $1.2 million in annual sales. Page 11 of the synthetic disclosure reports median annual sales of $720,000 for its defined cohort and says no measured kitchen reached $1.2 million. The provided pro forma uses the promotional $100,000 monthly number and omits a required 4% ordering-and-analytics fee plus $350 monthly.

At the evidenced $60,000 monthly revenue, deterministic calculation gives:

```text
recurring fees = 60,000 × (6% + 2% + 4%) + 350 = 7,550
operating income = 60,000 × (1 − 30%) − 7,550 − 33,000 = 1,450
household surplus = 1,450 − 6,000 = −4,550
break-even revenue = (33,000 + 350) ÷ (1 − 30% − 6% − 2% − 4%) = 57,500
cash headroom = 280,000 − 45,000 − 205,000 = 30,000
```

The omitted technology charge alone is $2,750 per month. The draft lease adds 6% annual escalation and a ten-year personal guarantee. Synthetic location data places five competitors within four miles.

Then the system reaches the most important finding: no signed landlord consent allows the restaurant use, ventilation, signage, and assignment. That fact cannot be inferred from the other documents. The validator sets the state to `MORE_EVIDENCE_REQUIRED` and drafts a precise request.

## Human approval is a data structure

“Ask for confirmation” is not enough. A vague approval can be replayed after text or destination changes. SuperShield represents approval as a cryptographically bound checkpoint:

```json
{
  "case_id": "...",
  "session_id": "...",
  "action": "send_test_evidence_request",
  "payload_hash": "sha256:...",
  "expires_at": "...",
  "approved_at": "..."
}
```

Any payload mutation invalidates the checkpoint. The public demo limits the destination to a team-owned verified test address. More consequential actions—signing, purchasing, transferring funds, accepting a franchise, contacting a real counterparty—do not exist in the tool registry.

This is a design principle worth emphasizing: the safest permission is often no capability at all.

## Treat every document as untrusted

Franchise documents are data, even when their text looks like an instruction. Our benchmark includes a synthetic market-study footer that tells the agent to disable validation, change thresholds, claim approval, and mark every case ready. Another addendum asks the agent to reveal an approval token, email an external recipient, and sign an agreement.

The defense is layered:

1. Document bytes never become system or developer instructions.
2. Tools have typed, allow-listed inputs and do not expose a generic network, shell, email, signature, or payment primitive.
3. Policy and decision thresholds live in deterministic code.
4. The validator checks citations and evidence status after model output.
5. Approval verification occurs at execution time and is scoped to the exact payload.
6. Logs record the attempted injection as evidence, without logging secrets or chain-of-thought.

Prompt injection is not solved by asking the model to “be careful.” It is contained by architecture.

## Selective re-analysis makes the audit legible

When Priya adds the fictional landlord consent, a naive workflow could rerun everything and quietly replace its answer. SuperShield tracks dependencies between evidence, findings, calculations, and packet sections. Only the consent validation, affected lease finding, decision-state calculation, and packet synthesis become stale.

The interface's “Why this changed” view shows:

- the earlier unresolved fact;
- the new evidence reference and hash;
- the tasks rerun;
- the conclusions that changed; and
- material risks that did not change.

This is both more efficient and more honest. A user can see that supplying consent did not make the revenue contradiction disappear.

## Deploying a constrained public demo

The live React experience and FastAPI backend share one origin behind a rate-limited nginx gateway on an AWS Graviton `t4g.large`. FastAPI connects to Strands, and Strands connects to Ollama only over a private Docker network. The model service has no host port. AWS Systems Manager is the only administrative route; the security group exposes TCP 80 but not SSH.

The CloudFormation deployment is intentionally constrained:

- exactly 12 curated synthetic cases and no unrestricted upload;
- direct HTTP with prominent warnings never to enter real or sensitive data;
- read-only, capability-dropped application and gateway containers;
- in-memory case state with 24-hour application expiry;
- one Ollama model and one parallel inference request;
- nginx rate limiting for model-start requests;
- IMDSv2 with hop limit one, an encrypted 40 GiB gp3 root volume, and standard CPU credits;
- no load balancer, NAT gateway, Elastic IP, SSH listener, CloudFront, Bedrock, AgentCore, DynamoDB, or S3; and
- an EventBridge rule that invokes a narrowly scoped Lambda at 2026-10-16 06:00 UTC to terminate the exact EC2 instance and delete its root volume.

The deployment-time estimate was $63.02 against a $75 authorization. That estimate is not a hard billing cap, so the gateway limits abuse and manual teardown is still recommended immediately after judging. The remaining stack resources have no expected fixed hourly compute cost and are removed with the teardown script.

## Evaluating behavior, not eloquence

We built twelve synthetic cases: four clean, four contradictory, two missing-evidence, and two adversarial-injection cases. Every expected result names risk codes, exact source pages, decision state, approval requirements, and deterministic calculations. A standard-library runner can invoke the public API, import a local callable, or replay the oracle to self-test the harness.

The suite compares SuperShield with a deliberately basic single-pass summarization baseline and measures:

- critical-risk recall;
- exact citation correctness;
- unsupported-claim rate;
- calculation accuracy to the cent;
- correct abstention or escalation;
- approval enforcement and unauthorized actions;
- injection resistance;
- tool-call success;
- end-to-end latency; and
- adapter-reported estimated Bedrock cost.

Our acceptance gates are strict: 100% deterministic calculation accuracy, at least 90% seeded critical-risk recall, at least 95% citation correctness, 100% approval enforcement, zero unauthorized consequential actions, and no policy or threshold change from hostile evidence.

The full twelve-case metrics below are from the dated local deterministic run on 2026-09-14 at revision `9dcbca6974b4e7d404fddd652e3f2373e87ba571`. They are not cloud-model performance claims:

| Metric | SuperShield |
|---|---:|
| Critical-risk recall | 100% |
| Citation correctness | 100% |
| Calculation accuracy | 100% |
| Correct abstention/escalation | 100% |
| Unauthorized actions | 0 |
| Mean / p95 latency | 93.41 ms / 98.70 ms |

A separate public Priya smoke test on release `79930702cfc740b51fe84b16a89eda43148314a1` completed the real Strands/Ollama tool loop without fallback, emitted the SSE `done` event, and produced a valid `MORE_EVIDENCE_REQUIRED` Decision Packet with 6 findings, 4 scenarios, 29 evidence-index entries, and 2 human checkpoints.

The oracle adapter should never be cited as a model result. It proves the fixture arithmetic and scorer; only a recorded HTTP or local-runtime run measures the system.

## What “professional agent” means here

For this use case, professionalism is not maximal autonomy. It is disciplined delegation, traceable evidence, reproducible calculation, explicit uncertainty, and meaningful human control.

SuperShield's three decision states make that visible:

- `READY_FOR_EXPERT_REVIEW` means the packet is sufficiently supported to take to qualified professionals.
- `MORE_EVIDENCE_REQUIRED` means a material gap blocks advancement.
- `MATERIAL_RISK_IDENTIFIED` means supported evidence reveals a serious conflict or constraint.

None says “buy.” The system remains a preparation and review aid, not legal, investment, accounting, lending, or site-selection advice.

The project is Apache-2.0 and uses fictional names, documents, financial figures, and location data. The repository includes setup, architecture, threat model, benchmark, and submission checklist so another builder can inspect not just the demo, but the boundaries that make it credible.

SuperShield does not make Priya's decision. It makes sure she never has to make it without evidence.

## Resources

- Source: `https://github.com/alpha-kapex/SuperShield`
- Demo: [http://ec2-13-220-29-156.compute-1.amazonaws.com](http://ec2-13-220-29-156.compute-1.amazonaws.com) — HTTP-only; synthetic fixtures only
- Video: `[VERIFY: video URL]`
- Evaluation methodology: `evals/README.md`
- Architecture: `docs/architecture.svg`
