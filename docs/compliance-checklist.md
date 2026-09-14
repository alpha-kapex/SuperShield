# Agents for Humans submission checklist

Target: [agentsforhumans.devpost.com](https://agentsforhumans.devpost.com/)
Track: **Professional Agents**
Owners should attach a name, date, evidence URL, and reviewer to every checked release item. Repository presence alone is not proof of a deployed integration.

## Eligibility and clean-room boundary

- [ ] Project was created during the eligible event period; record start date and event rules snapshot.
- [x] Standalone SuperShield repository and independently designed schemas, prompts, tests, UI, documents, and assets.
- [x] Synthetic people, franchises, financials, leases, and location data only.
- [x] Git-history provenance reviewed on 2026-09-14: clean standalone repository with no unrelated or private history.
- [x] `detect-secrets` scan on 2026-09-14: zero candidate findings across releasable files; repeat after the release commit.
- [ ] Run dependency license and vulnerability scans; resolve or document every finding.
- [x] Apache-2.0 `LICENSE` included.
- [x] Public repository is visible without authentication under personal user account `alpha-kapex`: <https://github.com/alpha-kapex/SuperShield>.
- [x] Repository description and topics match the submission; Apache-2.0 license metadata is provided by `LICENSE`.
- [ ] Team members and prior/work-for-hire ownership are disclosed as required by the official rules.

## Required technology and working proof

- [x] Strands Agents SDK is used structurally by the supervisor and agents-as-tools; see `src/supershield/strands_adapter.py` and `src/supershield/workflow.py`.
- [x] Local end-to-end tests cover evidence intake, planning, delegation, contradiction, deterministic finance, gap, approval, new evidence, selective rerun, and Decision Packet.
- [x] Submission wording clearly labels the verified Ollama run as local and AgentCore/Bedrock deployment as optional and not yet live.
- [ ] App Runner demo works in a logged-out browser and exposes only curated cases.
- [ ] Nova model IDs, region, date, retry settings, and revision are recorded with benchmark results.
- [ ] Public API rate, body, run, token, origin, and session limits are verified.
- [ ] `DELETE /cases/{caseId}` and expiry behavior are tested in the deployed environment.
- [ ] Failure mode demonstrated: model/AWS timeout yields a safe error, no action, and preserved audit state.

## Evaluation evidence

- [x] Exactly 12 synthetic cases: 4 clean, 4 contradictory, 2 missing-evidence, 2 adversarial-injection.
- [x] Flagship Priya case contains claim conflict, omitted fee, lease risk, saturation, and a genuine evidence gap.
- [x] Expected decision states, risk codes, citations, and calculation results are versioned.
- [x] A single-agent summarization baseline is included.
- [x] Dated non-oracle local HTTP benchmark report preserved in `evals/REFERENCE_RESULTS.md` (2026-09-14).
- [x] 100% deterministic calculation accuracy across 12 cases.
- [x] 100% seeded critical-risk recall (gate: at least 90%).
- [x] 100% exact citation correctness (gate: at least 95%).
- [x] 100% approval enforcement and zero unauthorized consequential actions.
- [x] Both prompt-injection cases preserve tool policy, thresholds, secrets, and approval boundaries.
- [x] Every material conclusion has valid evidence or is explicitly unresolved.
- [x] Tool success, mean/p95 latency, inference mode, and estimated cost are recorded in `evals/REFERENCE_RESULTS.md`.

## Human control, privacy, and security

- [x] Decision states never authorize a purchase or replace expert review.
- [x] No payment, signature, purchase, franchise acceptance, or real-world commitment tool exists.
- [x] Approval design binds action, exact payload hash, case, session, and expiry.
- [x] Automated tests cover approval replay, mutation, cross-case use, cross-session use, and expiry.
- [x] Public demo has no unrestricted documents or arbitrary external recipients.
- [ ] Verify logs contain no prompts, source bodies, secrets, tokens, email addresses, or private chain-of-thought.
- [x] DynamoDB TTL, S3 lifecycle/encryption/public block, KMS rotation, log retention, ECR scan, capped App Runner scaling, and AWS Budget are configured.
- [ ] Confirm least-privilege IAM with AWS Access Analyzer or IAM Policy Simulator.
- [ ] Verify TLS, security headers, CORS allowlist, dependency pinning, and container non-root/read-only behavior.
- [ ] Publish contact and deletion instructions; do not collect production personal data for judging.

## Judging criteria evidence

### Technological Implementation

- [ ] Show the Strands supervisor, bounded specialist tools, pause/resume, selective rerun, validator, and approval enforcement in one real trace.
- [x] All measured results and demonstrations are explicitly labeled local; no live AgentCore claim is made.
- [x] Deployment templates and reproducible evaluation commands are linked from `README.md`, `infra/README.md`, and `evals/README.md`.

### Design

- [x] Local UI and API demonstrate constraints, plan, live work, evidence graph, changed scenario, checkpoint, and Decision Packet.
- [ ] Keyboard-only pass, visible focus, semantic headings, status text beyond color, responsive mobile layout, and contrast review completed.
- [x] Plain-language explanations and “Why this changed” are implemented in the responsive UI.

### Potential Impact

- [x] Submission draft states the exact user and problem without claiming universal coverage or professional advice.
- [x] Priya's $40,000 monthly revenue difference, $2,750 omitted fee, and $4,550 household shortfall are quantified.
- [x] Submission draft explains how evidence gaps and auditability improve expert preparation.

### Creativity and Originality

- [x] Two executable adversarial-evidence fixtures test prompt-injection resistance.
- [x] Automated tests demonstrate policy-enforced abstention and payload-bound approval.
- [x] Documentation and UI explain why selective dependency reruns improve trust.

### Presentation

- [ ] Final video is public/unlisted as permitted, under five minutes, captioned, and viewable logged out.
- [ ] Video shows real product behavior, exact citations, financial consequences, human approval, selective rerun, architecture, trace, and dated benchmark.
- [ ] No account IDs, tokens, email addresses, browser profiles, unrelated work, or private chain-of-thought appear.

## Submission fields and links

- [x] Devpost title, tagline, problem, implementation, challenges, accomplishments, lessons, and next steps completed in `docs/devpost-submission.md`.
- [x] Public personal-account GitHub URL: <https://github.com/alpha-kapex/SuperShield>
- [x] Benchmarked implementation commit: `9dcbca6974b4e7d404fddd652e3f2373e87ba571`
- [ ] Live demo URL: `[VERIFY]`
- [ ] Video URL and duration: `[VERIFY]`
- [ ] Architecture SVG renders from the public repository.
- [ ] AWS Builder ID attached as required: `[VERIFY]`
- [ ] AWS Builder article published before the deadline, if pursuing the bonus: `[VERIFY]`
- [ ] Every link checked in a private/logged-out browser session.
- [ ] Final submission preview reviewed by two people against current official rules.
