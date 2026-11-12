# auto-factory contracts

The fixed interfaces between the scripts, the agents, the orchestrator skill and
the dashboard. Change one side only together with the other.

Paths below are relative to the **target repo** the factory is installed in
(the "main checkout", `<repo>`). In this package they live under `template/`.

```
<repo>/.claude/skills/factory/SKILL.md      orchestrator (/factory)
<repo>/.claude/agents/<name>.md             one file per agent
<repo>/factory/config.json                  settings (edited from the dashboard)
<repo>/factory/bin/job.py                   the only writer of job.json
<repo>/factory/bin/gate.py                  checks + built-in rules → round-N/checks.md
<repo>/factory/bin/route.py                 risk + surfaces → reviewers, auto_merge
<repo>/factory/bin/env.py                   per-job .env, database, seed
<repo>/factory/bin/port.py                  ports: which, free, kill
<repo>/factory/bin/shot.py                  signed-in screenshots (optional Playwright)
<repo>/factory/bin/serve.py                 dashboard + settings server (127.0.0.1)
<repo>/factory/bin/run.py                   tool-neutral runner: drives any agent CLI (Claude, Codex, DeepSeek…)
<repo>/factory/factorylib/                  shared Python (stdlib only)
<repo>/factory/dashboard/index.html         dashboard single-page app
<repo>/factory/seed-users.json              test-only users per role (optional)
<repo>/factory/jobs/<job-id>/               runtime state (gitignored)
<repo>/factory/config-history/              previous settings (gitignored)
<repo>/.worktrees/<job-id>/                 each job's worktree (gitignored)
```

Every script is run as `python factory/bin/<name>.py …` from `<repo>` (never by
shebang). Python 3.10+, standard library only. Scripts print one line on
success, an error line starting with `<script>: ` on stderr and a non-zero exit
on refusal.

## Stages

```
intake → needs-info | rejected | spec
needs-info → intake | rejected
spec → implement
implement → gate | needs-human
gate → review | implement | needs-human
review → approve | implement | needs-human
approve → merging | needs-human
merging → needs-human
needs-human → implement | rejected
any unfinished stage → merged   (when its PR is merged on GitHub)
```

Running stages (hold a concurrency slot): `intake, spec, implement, gate,
review, approve, merging`. Waiting: `needs-info, needs-human`. Terminal:
`merged, rejected`.

## Job id, branch, ports, database

- Job id: `NNN-slug` (`045-add-a-priority-column`), NNN = next free number,
  slug = first 4 words of the issue title.
- Branch `factory/<job-id>`, worktree `.worktrees/<job-id>`.
- Ports: `n` = NNN as an integer. `base + step*n + offset` where offset is
  implementer 0, reviewer-ux 1, reviewer-ui 2, reviewer-access 3.
  `python factory/bin/port.py for <job> <role>` prints it.
- Database name: `config.env.db_name` with `{project}` and `{n}` replaced
  (default `{project}_job_{n}`); `project` = repo folder name, lowercased,
  non-alphanumerics → `_`.

## The header line

Every agent prompt starts with the line `python factory/bin/job.py header <job>`
prints:

```
Job: <id>. Job folder: <repo>/factory/jobs/<id>/. Main checkout: <repo>. Worktree: <repo>/.worktrees/<id>. Branch: factory/<id>. Base: origin/<base>. Issue: #<n>. Port: <implementer port>. DB: <db name or none>.
```

Paths use forward slashes. `Job: <id>.` must stay first: cost attribution and
the implementer's Stop hook find the job by it.

## Agent files (one file per agent; first line is machine-read)

| Agent | Writes | First line(s) | Replies with |
|---|---|---|---|
| intake | `intake.md` | `DECISION: ACCEPT\|NEEDS-INFO\|REJECT`, `RISK: low\|medium\|high`, `SURFACES: <list>\|none`, `RESCOPED: yes\|no`, blank line | the DECISION line |
| spec-writer | `spec.md` | `# <title>` then `> Issue #<n>: <issue title>` | `SPEC: <title>` |
| implementer | `impl.md` | `STATUS: READY\|BLOCKED` | that line |
| reviewer-`<r>` | `round-<N>/review-<r>.md` | `VERDICT: PASS\|CHANGES` | that line |
| approver | `decision.md` | `APPROVE\|ESCALATE` | that line |

`SURFACES` is a comma-separated subset of `ui, security, data, access,
integration`, or `none`. Reviewers `<r>`: `code, security, ux, ui, data, access`.

Every agent file has a `## Summary` of 3–5 bullets right after its header; the
dashboard shows it. Sections per file:

- intake.md: Summary, Scope, Why, Questions (NEEDS-INFO only). Everything below
  the header is posted on the issue.
- spec.md: Summary, Context, Requirements, Acceptance criteria, Role matrix
  (when `ui` or `access`), Out of scope, Assumptions.
- impl.md: Summary, Changes, Acceptance criteria, Validation, Log (`### Round N`
  entries), Blocked (BLOCKED only).
- review-*.md: Summary, Findings (`None.` when empty), Notes.
- decision.md: Summary, Why, Acceptance criteria, For the human (ESCALATE).
  Everything below the first line is posted on the PR when the job goes to a human.

Files written by scripts: `job.json`, `issue.md` (quoted, data only),
`round-<N>/checks.md` + `checks.log`, `round-<N>/merge-checks.md` +
`merge-checks.log`, `feedback-<k>.md`, `rejection.md`, `intake-<k>.md`
(previous intake after a NEEDS-INFO reply), `round-<N>/shots/*.png`.

## checks.md (gate output)

```
GATE: PASS|FAIL
COMMIT: <sha>

## Summary
- …

## Steps
| Step | Result | Time |
|---|---|---|
| lint | PASS | 8s |
| tests | PASS (FLAKY: passed on retry) | 1m 39s |

## Built-in rules
| Rule | Result |
|---|---|
| protected paths | PASS: none changed |
| diff budget | PASS: 214 lines, 7 files (high: 1500, 40) |
| secret scan | PASS: clean |
| local-only env | PASS |

## Failure
Last 80 lines of <step>: ```…```
```

## job.json

```json
{
  "id": "045-add-a-priority-column", "issue": 45, "title": "…", "issue_url": "…",
  "pr": 58, "pr_url": "…", "branch": "factory/045-…", "worktree": "<abs path>",
  "stage": "needs-human", "round": 1, "round_limit": 3,
  "intake": {"decision": "ACCEPT", "risk": "high", "surfaces": ["data"], "rescoped": false},
  "agents": {"reviewers": {"code": "sonnet", "data": "opus"}},
  "auto_merge": false, "auto_merge_reason": "data changes always go to a human",
  "always_human": true, "held": true,
  "gate": "PASS", "reviews": {"code": "PASS", "data": "PASS"},
  "port": 5550, "db": "backoffice_app_job_45",
  "cost": {"usd": 1.38, "by_agent": {"intake": 0.21}, "partial": false},
  "started": "2026-11-12T10:00:00Z", "ended": null,
  "history": [{"at": "…", "from": "intake", "to": "spec"}]
}
```

`held: true` = the approver said APPROVE but auto-merge is off for this job, so
it waits for a human merge. `cost.partial` = some model had no price in config.

## job.py commands

```
queue                    rows: action issue job stage note (action: resume|new|hold|wait|skip)
create <issue>           new job; prints the id
header <job>             the prompt header line
advance <job> <stage>    move or refuse
merge <job>              APPROVE → (held if auto-merge off) | sync base, gate --merge, gh pr merge
feedback <job>           stdin → feedback-<k>.md; needs-human → implement
reject <job>             stdin → rejection.md; needs-info|needs-human → rejected
agents <job> <json>      used by route.py only
sync <job>               refresh gate, reviews, cost from files
summary [<job>…]         table
preflight                run the gate on origin/<base> in a scratch worktree
pause | unpause          create/remove factory/PAUSE
archive <job>            zip a terminal job into factory/archive/
```

`<job>` is a job id or an issue number.

## config.json (validated by factorylib/config.py; the dashboard edits it)

```json
{
  "version": 1,
  "base_branch": "main",
  "merge_method": "squash",
  "shell": "system",
  "concurrency": 1,
  "max_rounds": 3,
  "labels": {"queue": "factory", "needs_info": "factory:needs-info", "needs_human": "factory:needs-human"},
  "models": {"intake": "fable", "spec-writer": "opus", "implementer": "opus", "approver": "opus"},
  "routing": {
    "low":    {"code": "haiku",  "auto_merge": false},
    "medium": {"code": "sonnet", "auto_merge": false},
    "high":   {"code": "sonnet", "auto_merge": false}
  },
  "surface_reviewers": {
    "ui": {"ux": "sonnet", "ui": "haiku"},
    "security": {"security": "opus"},
    "data": {"data": "opus"},
    "access": {"access": "opus"},
    "integration": {"security": "opus"}
  },
  "always_human_surfaces": ["data", "access", "integration"],
  "checks": [
    {"name": "tests", "cmd": "…", "enabled": true, "timeout": 900, "retry_on_fail": 1}
  ],
  "checks_none_ok": false,
  "env": {
    "template": ".env.factory",
    "db_name": "{project}_job_{n}",
    "db_create": "", "db_drop": "", "migrate": "", "seed": "",
    "dev_server": "",
    "login_path": "",
    "local_hosts": ["localhost", "127.0.0.1", "::1"]
  },
  "ports": {"base": 5100, "step": 10},
  "protected_paths": ["factory/*", ".claude/*", ".github/workflows/*"],
  "diff_budget": {
    "low": {"lines": 300, "files": 10},
    "medium": {"lines": 800, "files": 25},
    "high": {"lines": 1500, "files": 40}
  },
  "cost_caps_usd": {"job": null, "run": null},
  "prices_usd_per_mtok": {}
}
```

- `shell`: `system` (cmd.exe on Windows, sh elsewhere), `bash`, or `powershell`.
- Commands in `checks` and `env` may use `{JOB}`, `{N}`, `{PORT}`, `{DB}`,
  `{WORKTREE}`; they also get env vars `FACTORY_JOB`, `FACTORY_N`,
  `FACTORY_PORT`, `FACTORY_DB`, `FACTORY_WORKTREE`.
- `login_path`: optional dev-only login URL template, e.g. `/dev-login?as={ROLE}`.
  When empty, `shot.py` signs in with `factory/seed-users.json`.
- `prices_usd_per_mtok`: `{"<model id>": {"input", "output", "cache_write_5m",
  "cache_write_1h", "cache_read"}}`. Empty = cost shows as partial.
- Locked: `factory/*` and `.claude/*` can't be removed from `protected_paths`.

## Two ways to run the agents

1. **Inside Claude Code**: `/factory run` (the skill) spawns the agents as
   Claude Code subagents.
2. **Any agent CLI**: `python factory/bin/run.py [<issue>|doctor]` is a script
   orchestrator. It starts each agent as its own command from config `runner`,
   checks the file the agent had to write, and moves the job on with the same
   scripts. The state machine and files are identical, so a job can switch
   between the two between runs.

Runner config (inside config.json):

```json
"runner": {
  "harness": "claude",                 // tool for every role…
  "role_harness": {"intake": "codex"}, // …unless a role names its own
  "agent_timeout_minutes": 60,
  "harnesses": {
    "<name>": {
      "cmd": "…",                // one line; placeholders below
      "prompt": "stdin|file",    // how the prompt reaches the tool
      "output": "text|claude-json",
      "model_flag": "--model {MODEL}",
      "models": {"opus": "<model id>"},  // tier → model; missing = tool default
      "verified": false          // true once the command was checked against the tool's --help
    }
  }
}
```

Placeholders: `{MODEL_FLAG}` (the model flag, or nothing when the tier has no
model), `{MODEL}`, `{TOOLS}` (the role's tools from its agent file, comma
separated), `{PROMPT_FILE}`, `{ROLE}`. Agent commands run from `<repo>` with
the same `FACTORY_*` env vars as checks, plus `FACTORY_ROLE`.

The prompt is `<header line>`, `Role: <role>.`, the task line (e.g.
`Implement round 2. The gate failed: …`, `Review round 1.`), optionally
`Your port: <p>.`, then a tool-neutral preamble and the agent file's body
without frontmatter. The runner, not the agent, guarantees: the gate's dry run
after the implementer (one retry), push + draft PR when the agent couldn't,
one retry when an agent didn't leave its file, reverting code changes by
read-only roles, and stopping when anything touches the main checkout.

Runner files in the job folder: `runs/NNN-<role>.prompt.md`, `.log`,
`.json` (`{role, harness, model, task, started, seconds, exit, timed_out,
cost_usd, reply, error}`), `runs/warnings.md`, `runs/stopped.md`.
`cost_usd` (from `claude-json` output) is added to the job's cost.

## Dashboard API (`serve.py`, 127.0.0.1 only)

Every `/api/` request needs header `X-Factory-Token: <token>` (printed by
`serve.py` and given to the page as `#token=<token>` in the URL) and a `Host`
of `127.0.0.1:<port>` or `localhost:<port>`. JSON in, JSON out.

```
GET  /                              dashboard/index.html
GET  /api/state                     {project, paused, config, config_dirty, jobs: [job.json…], slots: {used, total}, preflight}
GET  /api/jobs/<id>                 {job, files: [{path, first_line, summary: [..], size}]}
GET  /api/jobs/<id>/file?path=<p>   {path, content}       (path must stay inside the job folder)
POST /api/config                    {config} → 200 {config} | 400 {errors: [..]} | 409 {error} (a job is in gate/merging)
GET  /api/config/history            {entries: [{name, at}]}
GET  /api/config/diff               {diff}   (git diff of factory/config.json)
POST /api/pause                     {paused: bool} → {paused}
POST /api/preflight                 202 {status: "running"}
GET  /api/preflight                 {status: idle|running|done, result: {gate, commit, at, steps: [{name, result, seconds}], rules: [{name, result}]}|null}
POST /api/jobs/<id>/feedback        {text} → {job}
POST /api/jobs/<id>/reject          {text} → {job}
```

`project` = `{name, repo, base_branch}`. `preflight` in `/api/state` is the
last result or null.
