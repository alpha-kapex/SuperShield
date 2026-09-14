# Security policy

SuperShield is a competition reference implementation over synthetic data, not a production service for sensitive documents. See [the security and human-control model](docs/security.md) for its boundaries and threat analysis.

Do not put secrets, real personal/financial information, franchise documents, or exploit payloads containing live credentials in a public issue. Use GitHub private vulnerability reporting when enabled, or contact the repository owner through the private address on their GitHub profile.

When reporting, include the affected revision, impact, minimal reproduction using synthetic data, and any evidence of exposure. Do not access another person's case, attempt persistence, send external messages, or incur material cloud cost.

Only the latest default-branch revision is supported during the hackathon. There is no security SLA. If a credential is exposed, rotate it immediately, invalidate affected sessions, stop the public deployment if necessary, inspect narrowly scoped logs, and remove the secret from Git history before restoring service.
