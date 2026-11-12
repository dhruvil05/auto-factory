# auto-factory

An issue-driven software factory for backoffice projects, run by Claude Code
or any other agent CLI (Codex, DeepSeek, …).
Label a GitHub issue `factory`, run `/factory run`, and agents decide whether
it's worth building, write a spec, implement it on its own branch, pass it
through your checks, review it, and open a pull request. The approver merges
what it's allowed to; everything else waits for you with a specific question.

Built from the design in [PLAN.md](PLAN.md). The interfaces between the pieces
are fixed in [CONTRACTS.md](CONTRACTS.md).

## The loop

```
issue labeled `factory`
  intake            ACCEPT (maybe rescoped) | NEEDS-INFO (asks on the issue) | REJECT
  route.py          reviewers + models from risk and areas; may it auto-merge?
  job.py            worktree, branch, the job's own .env, database, migrations, seed
  spec-writer       spec.md with testable acceptance criteria and a role matrix
  implementer       commits, pushes, draft PR "Closes #n", impl.md
  gate.py           your check steps + built-in rules; FAIL goes straight back
  reviewers         code (+ ux, ui, security, data, access by area), all in parallel
  approver          APPROVE → job.py merge (or held for you) | ESCALATE → you
```

Nothing assumes an install or build step: each project's check steps (lint,
tests, a migration check…) are set in the dashboard. With no steps the gate
refuses to run, unless you switch on "No automated checks", which then sends
every job to you.

## Layout

```
install.py                     install or upgrade the factory in a project
template/                      what gets installed
  .claude/skills/factory/      the /factory orchestrator (Claude Code)
  .agents/skills/factory/      the $factory skill (Codex), which drives run.py
  .claude/agents/              intake, spec-writer, implementer, approver, 6 reviewers
  factory/bin/                 job, gate, route, env, port, shot, serve, run (python …/x.py)
  factory/factorylib/          shared Python, standard library only
  factory/dashboard/           the dashboard page (served by serve.py)
  factory/config.json          defaults; edited from the dashboard afterwards
tests/                         unit and end-to-end tests (fake GitHub, real git)
PLAN.md  CONTRACTS.md
```

## Requirements

- Python 3.10+ (`python` on PATH), git, Claude Code.
- The GitHub CLI `gh`, logged in with an account that can push and manage labels.
- Optional: Playwright for Python (`pip install playwright && python -m playwright
  install chromium`) so reviewers can take signed-in screenshots. Without it they
  review from code and say so.

Works on Windows (cmd, PowerShell or Git Bash), macOS and Linux.

## Install into a project

```bash
python install.py "C:/path/to/your-backoffice-repo"
```

It copies `template/`, adds the runtime folders to `.gitignore`, and prints the
remaining steps: tailor two placeholder lines in the intake and approver
agents, create the three GitHub labels, commit and push, then open the
dashboard and set the check steps.

Later, to take new scripts without losing your settings or tailored prompts:

```bash
python install.py "C:/path/to/your-backoffice-repo" --upgrade
```

## Run it

In the project, in Claude Code:

```
/factory run          every open `factory` issue, `concurrency` at a time
/factory run 12       one issue
/factory <anything>   ask about jobs, give feedback on one, reject one, file a feature
```

## The `factory` skill in Claude Code and in Codex

Both tools get the same commands from their own skill file:

| | Claude Code | Codex |
|---|---|---|
| Skill file | `.claude/skills/factory/SKILL.md` | `.agents/skills/factory/SKILL.md` |
| Type | `/factory run`, `/factory run 12`, `/factory <anything>` | `$factory run`, `$factory run 12`, `$factory <anything>` (or pick it in `/skills`) |
| Who runs the agents | Claude Code's own subagents | `factory/bin/run.py`, started by the skill |

In Codex the skill hands `run` to `run.py`, which needs network access and
starts other agent processes, so Codex asks you to approve running it outside
its sandbox. If your Codex session can't keep a long command running, run
`python factory/bin/run.py` in a terminal instead; the result is the same.
The Codex skill only runs when you name it (`allow_implicit_invocation: false`
in its `agents/openai.yaml`), because it opens and merges pull requests.

## Use it with Codex, DeepSeek or another agent tool

The factory doesn't need Claude Code. `run.py` is a script version of the
`/factory` orchestrator that starts every agent through a command you choose:

```bash
python factory/bin/run.py doctor    # check settings and that the tools are installed
python factory/bin/run.py           # every open `factory` issue
python factory/bin/run.py 12        # one issue
```

Pick the tool in the dashboard (Settings → Agent tools) or in `config.json`
under `runner`: one default tool for every role, and optionally a different
tool per role (say Codex implements, Claude reviews). Presets ship for:

| Tool | Status |
|---|---|
| Claude Code (`claude -p`) | checked against Claude Code 2.1.286; records cost per agent |
| Codex (`codex exec`) | preset, **not verified here**: compare with `codex exec --help` and set model names |
| DeepSeek (`deepseek exec`) | preset, **not verified here**: DeepSeek's terminal agents differ; set the real command |

Any other CLI works if it can run non-interactively, read a prompt from stdin
or a file, use a shell and edit files in the working folder. The agents'
instructions stay in `.claude/agents/*.md` for every tool. The runner adds a
short tool-neutral preamble, runs the gate's dry run after the implementer,
pushes and opens the PR itself when a sandbox blocks the network, and
reverts code changes made by agents that should only read.

Give each tool the permissions its role needs and no more. The implementer
edits and commits in its worktree; everyone else writes one file in the job
folder. All agents run from the project root.

## Dashboard

Board, job files and settings:

```bash
python factory/bin/serve.py
```

Open the printed link (it carries a private token). Settings saved there are
written to `factory/config.json`; commit that file so everyone running the
factory shares them.

## Safety

- Only issues labeled `factory` run; labels need triage or write access.
- Issue text reaches agents only as quoted data in `issue.md`, and only the
  author's and operator's comments.
- Branches are `factory/*`; merges happen only through `job.py merge` → `gh pr merge`.
  It never deploys.
- Auto-merge starts off for every risk; high risk, data, access and integration
  changes always go to a human.
- Each job gets its own worktree, database, ports and `.env`; anything that points
  at a host off this machine is refused before a command runs.
- The gate reads the main checkout's settings, so a branch can't change its own
  checks, and it fails any change to the factory's own files.

## Tests

```bash
cd tests
python -m unittest -v
```

The end-to-end tests build a throwaway repo with a bare `origin`, install the
factory, and drive every stage with a fake `gh`; no network or GitHub account
is needed. About three minutes on Windows.
