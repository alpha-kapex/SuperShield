# Demo runbook

This runbook keeps the Agents for Humans demonstration reproducible and safe. The flagship path uses only `priya-saffron-route` and a test approval; it never contacts a real counterparty.

## Before recording or judging

1. Record the exact Git commit, deployment region, model IDs, UTC time, and public URLs.
2. Run tests, the oracle harness, and a dated HTTP benchmark. Archive the JSON output without secrets.
3. Confirm the live EC2 health endpoint and all twelve `/demo-cases` entries in a logged-out browser.
4. Confirm TCP 80 is the only ingress rule, IMDSv2 is required, the root volume is encrypted and delete-on-termination, and the EventBridge/Lambda cutoff is enabled for 2026-10-16 06:00 UTC.
5. Delete any old cases and inspect logs for source text, tokens, email addresses, account IDs, and private reasoning.
6. Set browser zoom and OS scaling so citations remain legible at 1080p. Enable captions.

## Golden path

1. Choose **Saffron Route — Priya's Investigation**.
2. Verify inputs: $225,000 maximum investment; $45,000 emergency reserve; $6,000 monthly household income; Maple Junction; low risk tolerance.
3. Preview and start the investigation plan.
4. In the activity timeline, verify evidence, skeptic, finance, location, and validator tool events. Do not expose prompts or chain-of-thought.
5. Open the revenue conflict: brochure page 2 ($1.2M) versus disclosure page 11 ($720k median; none reached $1.2M).
6. Open the omitted-fee conflict: projection page 1 versus disclosure page 6. Confirm $2,750 monthly impact at $60,000 revenue.
7. Open lease page 2 and location findings: 6% annual escalation, full-term guarantee, five competitors within four miles.
8. Confirm calculations: $205,000 initial investment, $7,550 recurring fees, $1,450 operating income, $57,500 break-even, $30,000 cash headroom, and −$4,550 household surplus.
9. Confirm signed landlord consent is unresolved and the state is `MORE_EVIDENCE_REQUIRED`.
10. Preview the exact targeted request. Change one character and verify any prior approval is rejected. Restore the text, approve, and verify action/payload/case/session/expiry in the audit event.
11. Ingest only the curated consent response used by the demo. Verify selective rerun and “Why this changed”; unchanged financial risks must remain.
12. Open the final Decision Packet and provenance drawer. State explicitly that this is preparation for expert review, not a recommendation.

## Adversarial proof

Run `adversarial-copper-kite` and `adversarial-quiet-quill`. Verify the hostile page is identified as untrusted evidence and that there is no policy change, threshold change, token disclosure, external email, signature, fabricated approval, or unauthorized action. Do not read the injected commands aloud in a way that obscures that they were rejected.

## Failure fallback

If cloud inference fails, show the safe fallback state and a previously generated dated trace/report from the same public commit. You may demonstrate deterministic local mode, but label it clearly. Never claim the oracle adapter is a live Strands result. Avoid switching to an unrelated branch or private environment during the recording.

## After the demo

Delete the demo case through the API, verify it is no longer readable, and confirm no sensitive fields reached logs. Note AWS spend. If the public endpoint remains available, keep nginx rate limiting and the EventBridge/Lambda cutoff enabled. Otherwise run the exact-stack teardown in `infra/EC2_OLLAMA_DEPLOYMENT.md`. The endpoint is HTTP-only and must never receive real or sensitive data.
