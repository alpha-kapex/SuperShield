# Five-minute demo script

Target: **4:55**, with five seconds of safety buffer. Event: [Agents for Humans](https://agentsforhumans.devpost.com/), **Professional Agents** track. Record one continuous product story; use cuts only to keep the pace. Capture a real Strands/Ollama run from the live EC2 demo. Do not substitute staged screenshots for a claimed live deployment.

## 0:00–0:25 — Priya and the stakes

**Visual:** Title, then Priya's constraints beside a simple “life savings” illustration.

**Narration:** “Priya has $280,000 available, but $45,000 is her emergency reserve. She needs $6,000 a month for her household. A franchise brochure promises typical annual sales of $1.2 million. The documents are long, the claims are inconsistent, and one mistake could consume her safety net. SuperShield is a human decision firewall: it investigates, calculates, and stops before the human's final decision.”

## 0:25–0:55 — Constraints and investigation plan

**Visual:** Select **Saffron Route — Priya's Investigation**. Enter $225,000 maximum investment, $45,000 reserve, $6,000 income requirement, Maple Junction, low tolerance. Open the plan preview.

**Narration:** “Priya chooses a curated, entirely synthetic case. Before analysis, she declares the constraints that matter. The Strands supervisor turns them into a typed plan: verify claims, reconcile fees, calculate affordability, screen location risk, validate every material conclusion, then pause for missing evidence or human approval.”

## 0:55–1:50 — Live Strands investigation

**Visual:** Start the run. Keep the activity timeline visible as Evidence Collector, Skeptic, Finance, Location, and Validator complete. Open one provenance detail.

**Narration:** “This is not a chat wrapper. In the live AWS demo, a Strands supervisor delegates bounded work while a private Ollama service runs Qwen3. The Evidence Collector extracts testable claims with document, page, excerpt, and hash. The Skeptic looks for disconfirming evidence but cannot change the record. Finance uses deterministic Decimal formulas—never model arithmetic. Location uses a synthetic competitor map. The Validator enforces a simple rule: no evidence, no material conclusion. The interface streams tool names, status, citations, and timing, never private chain-of-thought.”

## 1:50–2:45 — The contradiction, hidden cost, and gap

**Visual:** Open the brochure/disclosure relationship, omitted-fee card, lease card, and map in that order. Zoom the exact citations.

**Narration:** “The brochure says ‘typical’ kitchens reach $1.2 million. Page 11 of the disclosure reports a $720,000 median—and no measured kitchen reached $1.2 million. The projection also omits the required 4% platform fee plus $350 a month: $2,750 every month at the evidenced sales level. The draft lease escalates 6% annually and personally guarantees the full ten-year term. Five competitors sit within four miles. And the required signed landlord consent for restaurant use, ventilation, signage, and assignment is simply missing.”

## 2:45–3:25 — Financial consequence and block

**Visual:** Switch from promotional to evidenced scenario. Highlight changes: revenue $100,000 → $60,000; recurring fees $7,550; operating income $1,450; household surplus −$4,550; break-even $57,500; cash headroom $30,000. Show `MORE_EVIDENCE_REQUIRED`.

**Narration:** “SuperShield recalculates the consequence. Using the disclosed median, monthly revenue falls by $40,000. Full recurring fees are $7,550. Business operating income is only $1,450, leaving a $4,550 household shortfall. Priya has $30,000 after investment and reserve. Because a material consent is missing, the validator will not let the case advance. It marks the fact unresolved and sets ‘More Evidence Required’—not ‘buy,’ and not legal or investment advice.”

## 3:25–3:55 — Human approval

**Visual:** Open the generated request; show exact payload, destination restricted to a verified team test address, hash, expiry, and buttons. Click approve. Show audit event. Do not use a real counterparty.

**Narration:** “The agent drafts a targeted request, but drafting is not sending. The approval is bound to this action, payload hash, case, session, and ten-minute expiry. Only Priya's explicit click permits this test action. Changing the text invalidates approval. Signing, paying, purchasing, and external commitments are not tools SuperShield has.”

## 3:55–4:20 — Evidence arrives; selective rerun

**Visual:** Add the curated consent evidence. Timeline highlights only evidence validation, affected lease finding, and packet synthesis. Open “Why this changed.”

**Narration:** “When the curated consent arrives, SuperShield hashes and validates it, then reruns only dependent work—not the whole investigation. ‘Why this changed’ shows the old gap, new citation, affected tasks, and unchanged risks. The resulting Decision Packet preserves every source, calculation input, approval, and state transition for expert review.”

## 4:20–4:45 — Architecture and evidence of quality

**Visual:** Architecture SVG, live health status showing a successful Ollama invocation, the completed Strands event, then the dated local benchmark report.

**Narration:** “The public React demo reaches a rate-limited nginx and FastAPI service on one AWS Graviton EC2 instance. Strands coordinates private Qwen3 inference through Ollama, while deterministic code owns evidence validation and arithmetic. Systems Manager replaces SSH, and EventBridge plus Lambda terminates the compute after judging. Twelve synthetic cases—four clean, four contradictory, two missing-evidence, and two hostile documents—measure recall, citation correctness, arithmetic, abstention, approval, tool success, and latency against a single-summary baseline.”

## 4:45–4:55 — Close

**Visual:** Decision Packet beside Priya; repository, demo, and evaluation links.

**Narration:** “SuperShield does not make Priya's decision. It makes sure she never has to make it without evidence.”

## Recording checklist

- Keep the final export below five minutes at normal playback speed and verify the public link logged out.
- Use captions, at least 1080p, a readable pointer, and no rapid flashing. Avoid tiny trace text; zoom before discussing it.
- Blur account IDs, session values, headers, tokens, email addresses, browser profiles, and unrelated tabs.
- Verify the run ID shown in the UI exists in the recorded trace. Keep a dated benchmark artifact from the same revision.
- Replace every placeholder URL in the Devpost draft; never claim a cloud result measured only with `--adapter oracle`.
