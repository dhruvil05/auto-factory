# Factory profiles

A profile is the `## Factory profile` section of a project's `AGENTS.md`.
Every factory agent reads it on every job to learn the project: roles,
what goes to a human, where access checks live, data rules, UI and how to verify.

## Pick one
| Profile | For |
|---|---|
| `backoffice` | internal admin apps: roles, tenants, audit, money |
| `web-app` | customer-facing SaaS: accounts, billing, public pages |
| `api-service` | HTTP/JSON APIs and backend services |
| `library` | reusable packages and SDKs |
| `mobile-app` | iOS/Android/cross-platform apps |
| `data-pipeline` | ETL, analytics and ML pipelines |
| `blank` | anything else |

`python install.py <project> --profile <name>` seeds it into `AGENTS.md`;
`CLAUDE.md` imports `AGENTS.md`, so Codex and Claude Code both load it.

## Then

- Replace every `[bracketed]` part; delete lines that aren't true.
- Keep it short: every line is read by every agent on every job.
- Write `None` or `No UI` for a section that doesn't apply; agents skip those checks.
