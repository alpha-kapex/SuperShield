# Reference results

## Measured local HTTP workflow

Command run on 2026-09-14 against the real FastAPI workflow:

```bash
python evals/run_benchmark.py --adapter http \
  --base-url http://127.0.0.1:8765 \
  --output evals/results/http-local.json
```

| Metric | SuperShield | Naive summary baseline |
|---|---:|---:|
| Cases | 12 | 12 |
| Critical-risk recall | 100% | 0% |
| Exact citation correctness | 100% | 0% |
| Unsupported-claim rate | 0% | 0%* |
| Financial calculation accuracy | 100% | 0% |
| Correct abstention/escalation | 100% | 0% |
| Approval enforcement | 100% | 0% |
| Unauthorized actions | 0 | 0 |
| Prompt-injection resistance | 100% | 0% |
| Tool-call success | 100% | n/a |
| Mean / p95 latency | 93.41 ms / 98.70 ms | not published |

This is a measured deterministic workflow/API result with no cloud model call and therefore $0 inference cost. A separate flagship smoke run completed through the real Strands Agents SDK with local Ollama `qwen3:0.6b`, producing `MORE_EVIDENCE_REQUIRED` without a provider error. Neither result is presented as Bedrock or AgentCore performance.

*The baseline's zero unsupported-claim rate is vacuous because it emits no high/critical claims.


## Fixture/scorer self-test

Command run on 2026-09-14:

```bash
python evals/run_benchmark.py --adapter oracle \
  --output evals/results/oracle-self-test.json
```

| Metric | Oracle self-test | Naive summary baseline |
|---|---:|---:|
| Cases | 12 | 12 |
| Critical-risk recall | 100% | 0% |
| Exact citation correctness | 100% | 0% |
| Unsupported-claim rate | 0% | 0%* |
| Financial calculation accuracy | 100% | 0% |
| Correct abstention/escalation | 100% | 0% |
| Approval enforcement | 100% | 0% |
| Unauthorized actions | 0 | 0 |
| Prompt-injection resistance | 100% | 0% |
| Tool-call success | 100% | n/a |

\*The naive baseline produces no high/critical claims, so its zero unsupported-claim rate is vacuous; its 0% risk recall and citation correctness expose that omission.

These numbers validate fixture composition, answer-key citations, Decimal arithmetic, scoring, and report generation. **They are not a measured Strands, model, AgentCore, latency, or cloud-cost result.** Replace this comparison in the Devpost submission with a dated `--adapter http` or `--adapter python` run tied to the public commit, model IDs, region, and retry settings.

The generated JSON and Markdown artifacts are intentionally ignored because timings and raw model outputs vary. Preserve a release result by copying it to a versioned, clearly dated file after review.
