# Contributing to SuperShield

Thank you for improving an evidence-first, human-controlled agent.

## Clean-room requirement

Contributions must be original or from a clearly identified compatible open-source source. Do not paste private source code, prompts, schemas, tests, documents, UI components, assets, business data, credentials, or Git history. Do not submit real franchise disclosures or personal financial information. Stop and raise provenance uncertainty before opening a pull request.

## Development loop

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python evals/run_benchmark.py --adapter oracle
```

For user-interface changes, also run the checks documented in `web/package.json`, test keyboard-only navigation and mobile layout, and include an accessible screenshot only when it helps review.

## Pull requests

- Keep a change focused and explain the user-visible behavior.
- Add or update tests for policy, evidence, calculation, and API changes.
- Preserve exact evidence provenance and deterministic arithmetic.
- Never add a tool that signs, purchases, pays, accepts a franchise, or contacts an arbitrary recipient.
- Document new data sources and licenses in `docs/data-attribution.md`.
- Do not commit `.env`, AWS identifiers, generated AgentCore configuration, traces, raw user data, or benchmark outputs containing sensitive data.
- Run secret, dependency, license, and vulnerability scans before requesting release review.

By contributing, you agree that your contribution is licensed under Apache-2.0.
