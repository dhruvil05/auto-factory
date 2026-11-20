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
<repo>/factory/jobs/<job-id>/attachments/   images from the issue (image-<k>.<ext>), for the agents
<repo>/factory/jobs/_runner/                the runner's lock, state.json, STOP request, runner.log
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

Every agent file has a `## Summary` of at most 3 bullets right after its header; the
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
  "paused": null,
  "history": [{"at": "…", "from": "intake", "to": "spec"}]
}
```

`held: true` = the approver said APPROVE but auto-merge is off for this job, so
it waits for a human merge. `cost.partial` = some model had no price in config.
`paused: {"at": "<iso>", "now": bool}` = a person paused this one job (`now`:
its running agent is ended at once); null otherwise. A paused job holds no
slot, the queue shows it as `hold … paused`, and no orchestrator moves it.

## Images in the issue

`write_issue_md` (on `create` and when intake runs again) downloads every
image in the issue body and in trusted comments into `attachments/`
(`image-1.png`, …) and points `issue.md` at them: inside the quoted text an
image becomes `[image (alt): attachments/image-1.png]`, or
`[image: <url> — couldn't download: <why>]`. A `## Images` section at the end
lists the saved files by absolute path. Rules: GitHub-hosted links only
(`github.com`, `*.githubusercontent.com`, plus hosts in
`$FACTORY_IMAGE_HOSTS`); private-repo images through the signed links in
GitHub's rendered HTML (`gh api … Accept: application/vnd.github.full+json`),
else the link with `gh auth token` sent to github.com only; at most 20
images, 10 MB each; PNG, JPEG, GIF and WebP only (checked by content). A
failed download never stops the job.

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
pause <job> [--now]      set job.json paused (with --now the runner ends its running agent)
unpause <job> | retry <job>   clear paused and runs/stopped.md: a runner picks the job up again
wait [--timeout <s>]     block until queue has new/resume rows (prints them) or exit 3 (default 540 s)
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

## Project profile (makes the agents fit any project)

The agent instructions are domain-neutral. Everything specific to one project
lives in a **Factory profile**: a `## Factory profile` section in the
project's `AGENTS.md` (Codex loads it automatically; `CLAUDE.md` imports it
with a line `@AGENTS.md`, so Claude Code loads it too). `install.py --profile
<name>` seeds it from `profiles/<name>.md`; you then replace the bracketed parts.
Its subsections, by these exact names:

| Subsection | Holds | Used by |
|---|---|---|
| `### What this project is` | product in 1–3 lines, who uses it | intake, spec-writer, approver |
| `### Users and roles` | roles and what each may do, or `None` | spec-writer, ux, access |
| `### Sensitive areas` | what always goes to a human (money, data deletion, …) | intake, approver |
| `### Authorization` | where access checks live (middleware, policies), how to verify | implementer, access, security |
| `### Data rules` | scoping/tenancy, audit log, migration tool and rules, money/rounding, or `None` | implementer, data, spec-writer |
| `### UI conventions` | design system, components, theme location, or `No UI` | implementer, ui, ux |
| `### Verify` | how to see the change working (dev server, seeded users) | implementer, ux, ui |
| `### Terms` | glossary (optional) | everyone |

A subsection that is missing, `None` or `No UI` turns the matching checks off.
Agents never assume a domain the profile doesn't state.

## Working rules every agent follows (token budget)

Each agent file carries the same short "Working rules" block:

- Context is the job header, the inputs listed for the role, and the project
  profile. Don't explore beyond what the task needs.
- Search before reading (grep/glob for symbols and paths). Read around the
  relevant lines; read a whole file only when it is short or you change or
  review all of it. Never read generated, vendored, minified, lock or build
  files, and never dump large files.
- Stop reading as soon as you can do the task.
- Write short: `## Summary` is at most 3 bullets; don't restate the spec or
  the diff; Findings are only real problems.

Reviewers: **Findings** are blocking (they make the verdict CHANGES); **Notes**
never block. Reviewers whose area the diff doesn't touch write a short PASS
straight away (e.g. no UI files changed → `reviewer-ui` passes).

## Re-reviews only look at what changed

From round 2, the task line of a reviewer may end with
`Previous review: round <M> at <sha>.` It comes from
`python factory/bin/job.py reviewed <job> <reviewer>`, which prints
`round-<M> <sha>` (the latest earlier round with that reviewer's file, and the
commit its gate passed) or `none`. With it, the reviewer reads its own
`round-<M>/review-<r>.md`, checks each earlier finding, and reviews only
`git diff <sha>..HEAD` for new problems. Without it, it reviews the whole
branch (`git diff origin/<base>...HEAD`).

## Prompt layout for other agent tools

`run.py` sends the role's instructions **first** and the job-specific block
**last** (`## This job`: header line, `Role:`, task line, optional port), so
the unchanging part can be cached by the provider.

## Two ways to run the agents

1. **Inside Claude Code**: `/factory run` (the skill) spawns the agents as
   Claude Code subagents.
2. **Any agent CLI**: `python factory/bin/run.py [<issue>] [--watch]` is a script
   orchestrator (also `stop [--now]`, `status`, `doctor`). It starts each agent
   as its own command from config `runner`, checks the file the agent had to
   write, and moves the job on with the same scripts. The state machine and
   files are identical, so a job can switch between the two between runs.

Only one orchestrator works on a project at a time: run.py holds the lock
`factory/jobs/_runner/.lock`, and the skill checks `run.py status` first.

**Watch mode** (`--watch`; the dashboard's Start runs this): the runner keeps
going until stopped. Each job runs in its own thread; one job waiting,
pausing or stopping never holds up the others. It re-reads the queue within
seconds of a person acting on this machine (feedback, reject, pause, resume,
retry, settings) and every `runner.poll_seconds` for GitHub (answers to
intake questions, merges, new issues). A stopped job stays stopped until
`retry` (or `unpause`) removes its `runs/stopped.md`. Without `--watch` it
ends when nothing can move without a person, as before; with `<issue>
--watch` it ends when that issue is merged or rejected.

**Stopping.** `factory/jobs/_runner/STOP` holds `graceful` (start no new step;
finish the ones running) or `now` (also end running agents). A job paused
with `--now` has its agent ended within a second (the process tree is
killed); the run record says `"stopped": true` and the step runs again on
resume. `state.json`: `{pid, beat, started, watch, issue, phase, active,
stopped, exit}`, rewritten every few seconds.

Runner config (inside config.json):

```json
"runner": {
  "harness": "claude",                 // tool for every role…
  "role_harness": {"intake": "codex"}, // …unless a role names its own
  "agent_timeout_minutes": 60,
  "poll_seconds": 60,
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
without frontmatter. The runner, not the agent, guarantees: a commit of what
the implementer left uncommitted (sandboxed tools such as Codex can't write
`.git`; `.env` is never included; a BLOCKED whose only reason is git access
gets the commit plus one more implementer turn to re-check its status instead
of going to a human), the gate's dry run
after the implementer (one retry), push + draft PR when the agent couldn't,
one retry when an agent didn't leave its file, reverting code changes by
read-only roles, and stopping when anything touches the main checkout.

Runner files in the job folder: `runs/NNN-<role>.prompt.md`, `.log`,
`.json` (`{role, harness, model, task, started, seconds, exit, timed_out,
stopped, cost_usd, tokens, reply, error, log}`), `runs/warnings.md`, `runs/stopped.md`.
`cost_usd` (from `claude-json` output) is added to the job's cost.

## Dashboard API (`serve.py`, 127.0.0.1 only)

Every `/api/` request needs header `X-Factory-Token: <token>` (printed by
`serve.py` and given to the page as `#token=<token>` in the URL) and a `Host`
of `127.0.0.1:<port>` or `localhost:<port>`. JSON in, JSON out.

```
GET  /                              dashboard/index.html
GET  /api/state                     {project, paused, config, config_dirty, jobs: [job.json + stopped], slots: {used, total}, preflight, runner}
GET  /api/jobs/<id>                 {job, files: [{path, first_line, summary: [..], size}]}
GET  /api/jobs/<id>/file?path=<p>   {path, content}, or the bytes for .png/.jpg/.gif/.webp (path must stay inside the job folder)
POST /api/config                    {config} → 200 {config} | 400 {errors: [..]} | 409 {error} (a job is in gate/merging)
GET  /api/config/history            {entries: [{name, at}]}
GET  /api/config/diff               {diff}   (git diff of factory/config.json)
POST /api/pause                     {paused: bool} → {paused}
POST /api/preflight                 202 {status: "running"}
GET  /api/preflight                 {status: idle|running|done, result: {gate, commit, at, steps: [{name, result, seconds}], rules: [{name, result}]}|null}
POST /api/jobs/<id>/feedback        {text} → {job}
POST /api/jobs/<id>/reject          {text} → {job}
POST /api/jobs/<id>/control         {action: pause|stop|resume|retry} → {job, message} | 409 {error}
GET  /api/runner                    {runner, log}   (log: the last 200 lines of runner.log)
POST /api/runner                    {action: start|stop|stop-now} → {runner, message} | 409 {error}
```

`runner` = `{running, stopping, pid, started, beat, watch, issue, phase,
active, stopped}` while one runs, else `{running: false, last}`. In
`/api/state` each job also has `stopped` (the first line of the reason in
`runs/stopped.md`, or null). Start launches `run.py --watch` in its own
process group with output to `factory/jobs/_runner/runner.log`; it keeps
running when the dashboard stops.

`project` = `{name, repo, base_branch}`. `preflight` in `/api/state` is the
last result or null.
