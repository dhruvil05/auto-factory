# Installing auto-factory (for a coding agent)

You are installing this factory into the user's project. Copy with the script,
tailor what's project-specific, verify, and report. Don't commit or push without
asking.

## 1. Check

Stop and tell the user if any fails:

- The project is a git repo whose `origin` is on GitHub, and `gh auth status`
  shows an account that can push and manage labels.
- `python --version` is 3.10 or later.
- The default branch (`gh repo view --json defaultBranchRef`) exists on `origin`.

## 2. Copy

```bash
python "<this package>/install.py" "<project root>" --profile <name>
```

If it lists files that already exist, show the user and ask before using `--upgrade`.

It installs both skills: `.claude/skills/factory/` (Claude Code, `/factory`)
and `.agents/skills/factory/` (Codex, `$factory`). Keep both even if the user
uses one tool today.

## 3. Tailor (keep structure, first lines and one-line replies unchanged)

- Pick the closest profile and pass it: `--profile backoffice | web-app |
  api-service | library | mobile-app | data-pipeline | blank`. Then fill the
  `## Factory profile` section it added to `AGENTS.md` from the README, routes,
  models and config: what the project is, roles, sensitive areas, where
  authorization and data rules live, UI conventions, how to verify. Keep it
  under ~45 lines; write `None` / `No UI` where a section doesn't apply.
  Don't edit the agent files for project details: the profile is the place.
- `factory/config.json`: set `base_branch` and a `merge_method` the repo allows
  (`gh api repos/{owner}/{repo} --jq '{allow_merge_commit, allow_squash_merge, allow_rebase_merge}'`).
  Leave `checks` empty: the user sets them in the dashboard. You may suggest
  commands you found, in your report.
- If the app needs a database or env file to run tests, write `.env.factory` with
  local-only values using `{DB}` and `{PORT}`, and suggest `env` commands
  (db_create, migrate, seed, dev_server with `{PORT}`) in your report.
- Optional: `factory/seed-users.json` with test-only users per role (see the
  docstring of `factory/bin/shot.py`). Never real accounts.

Add to `CLAUDE.md` (or `AGENTS.md`):

```markdown
## Software factory
`/factory run` builds open GitHub issues labeled `factory`: intake → spec →
implement → gate → review → approve, one PR per issue. State: `factory/jobs/`
(gitignored), written only by `python factory/bin/job.py`. Settings and check
steps: `python factory/bin/serve.py` (dashboard). Each job works in
`.worktrees/<job-id>`; tools that scan the repo should exclude `.worktrees/`.
```

If the user will run the agents with another tool (Codex, DeepSeek, …):
put the section above in `AGENTS.md` (most non-Claude tools read that file),
set `runner.harness` in `factory/config.json` (or in the dashboard under
Settings → Agent tools), and fill that tool's `models` and command from its
`--help`. Then `python factory/bin/run.py doctor` must print `ok`.

## 4. Verify

1. `python factory/bin/job.py queue` runs (needs `gh`).
2. `python -c "import json; json.load(open('factory/config.json'))"` succeeds.
3. `git check-ignore factory/jobs/x .worktrees/x` prints both paths.
4. Every `.claude/agents/*.md` frontmatter has only `name`, `description`,
   `tools`, `model` (and `hooks` on the implementer).

## 5. Report

Show the diff and tell the user, in a few lines:

- Create the labels (the install script printed the `gh label create` commands).
- Commit and push to the base branch; jobs branch from `origin`.
- Run `python factory/bin/serve.py`, set the check steps, press **Test on main**.
- Label one small issue `factory` and run `/factory run`. Auto-merge is off for
  every risk at first, so every PR waits for them.
