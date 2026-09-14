# Security and human-control model

SuperShield is a constrained demonstration for reviewing synthetic franchise evidence. It is not a general-purpose autonomous agent, document vault, email client, transaction system, or professional adviser.

## Protected assets

- Buyer constraints, case/run state, temporary evidence, approval records, and Decision Packets.
- AWS credentials, session secrets, approval tokens, model prompts, runtime configuration, and trace identifiers.
- Integrity of evidence, citations, calculations, decision policy, tool allowlist, and state transitions.

## Trust assumptions

- Repository fixtures and all user-provided document text are **untrusted data**.
- A model response is untrusted until schema, evidence, calculation, action, and policy validation succeeds.
- Browser state is untrusted. Authorization and approval are verified server-side.
- Cloud administrators remain trusted; this demo does not defend against a fully compromised AWS account.

## Primary threats and controls

| Threat | Control | Verification |
|---|---|---|
| Prompt injection in evidence | Evidence is never inserted as policy; allow-listed typed tools; deterministic decision thresholds; post-output validation | `adversarial-copper-kite`, `adversarial-quiet-quill` |
| Fabricated or misplaced citation | Document-ID and page existence checks; excerpt hash; unsupported material claims become unresolved | Exact citation metric in benchmark |
| Arithmetic hallucination | Decimal-based finance tool; cent-level answer key; model cannot override results | 100% calculation gate |
| Approval replay or confused deputy | HMAC-bound action + payload hash + case + session + expiry; mutation invalidates token | Unit/security tests and audit event |
| Unauthorized consequential action | No payment, signature, purchase, acceptance, arbitrary network, or real-recipient tool | Tool-registry review and zero-action gate |
| Secret/data exfiltration | Instance roles, no static AWS keys, scoped Secrets Manager access, logs redact inputs/tokens, curated demo only | Secret scan and log review |
| Cross-case/session access | Opaque identifiers plus server-side session ownership on every endpoint | Negative API tests |
| Resource abuse / unexpected cost | Body, token, rate, case, and run limits; two-instance cap; Nova Lite extraction; AWS Budget | Load test and budget subscription |
| Data persistence | 24-hour application expiry/DynamoDB TTL, one-day S3 lifecycle, explicit delete, 14-day logs | Post-delete and expiry tests |
| Supply-chain compromise | Pinned dependencies, vulnerability/license scan, ECR scan-on-push, immutable image deploy | Release checklist |

## Public-demo restrictions

- Only curated synthetic case IDs are accepted.
- Request bodies are capped at 256 KiB and runs at ten per session by default.
- Arbitrary uploads, URLs, plugins, shell access, destinations, and outbound messages are disabled.
- Optional email is off. If demonstrated, SES may send only to a team-owned verified address after payload-bound approval.
- CORS uses an explicit origin. Error responses do not expose stack traces or prompt content.
- SSE events contain event type, tool name, public status, citation IDs, duration, and run ID—never chain-of-thought.

## Data lifecycle

Case creation assigns `ExpiresAt = created_at + 24 hours`. The API rejects expired records even before asynchronous DynamoDB TTL cleanup. Evidence uses the S3 `cases/{case_id}/...` prefix, KMS encryption, public-access blocking, TLS-only policy, versioning, and one-day current/noncurrent lifecycle. `DELETE /cases/{caseId}` deletes both state and objects. CloudWatch logs retain 14 days and must not contain document bodies, secrets, approval tokens, or personal data.

## Reporting

Do not include secrets or real personal/financial information in an issue. For the competition repository, use GitHub's private vulnerability reporting if enabled; otherwise contact the maintainer address listed in the repository profile. Rotate any exposed key immediately, invalidate affected sessions, preserve minimal audit evidence, and remove leaked material from Git history before restoring public access.

## Explicit limitations

This reference design does not provide tenant-grade authentication, regulated-data compliance, malware scanning for unrestricted uploads, a web application firewall, jurisdiction-specific legal controls, production disaster recovery, or guaranteed model behavior. Those are required before accepting non-synthetic personal documents.
