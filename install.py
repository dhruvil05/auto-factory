"""Install or upgrade auto-factory in a project.

Usage:
  python install.py <project> [--profile <name>]
      first install; refuses to overwrite anything. --profile seeds the project
      profile (profiles/<name>.md) into AGENTS.md, which CLAUDE.md imports.
  python install.py <project> --upgrade [--prompts] [--profile <name>]
      replace the factory's scripts and dashboard; keeps config.json, seed-users.json
      and the agent and skill prompts. --prompts replaces the prompts too (your old
      ones are saved in factory/archive/prompts-<time>/ first).

Profiles: blank, backoffice, web-app, api-service, library, mobile-app, data-pipeline.
It copies files and edits .gitignore, AGENTS.md and CLAUDE.md. It never commits,
pushes, or talks to GitHub: the steps that need you are printed at the end.
"""

import argparse
import filecmp
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "template"
PROFILES = HERE / "profiles"
IGNORE = ["/factory/jobs/", "/factory/config-history/", "/factory/archive/", "/factory/PAUSE", "/.worktrees/"]
PROMPTS = (".claude/agents/", ".claude/skills/factory/", ".agents/skills/factory/")
# Files a project tailors; --upgrade leaves them alone (prompts only without --prompts).
TAILORED = ("factory/config.json", "factory/seed-users.json") + PROMPTS
RUNTIME = ("factory/jobs/", "factory/config-history/", "factory/archive/", ".worktrees/")
PROFILE_HEADING = "## Factory profile"


def die(msg):
    print(f"install: {msg}", file=sys.stderr)
    sys.exit(1)


def template_files():
    """The files to install: never caches or runtime state left by running the template itself."""
    for p in sorted(TEMPLATE.rglob("*")):
        rel = p.relative_to(TEMPLATE).as_posix()
        if (not p.is_file() or "__pycache__" in p.parts or p.suffix in (".pyc", ".tmp")
                or rel.startswith(RUNTIME) or rel in ("factory/PAUSE",)):
            continue
        yield rel


def profile_names():
    return sorted(p.stem for p in PROFILES.glob("*.md") if p.stem.lower() != "readme")


def add_profile(target, name):
    """Append the profile to AGENTS.md and make CLAUDE.md import AGENTS.md. Returns what it did."""
    done = []
    text = (PROFILES / f"{name}.md").read_text(encoding="utf-8")
    body = "\n".join(l for l in text.splitlines() if not l.strip().startswith("<!--")).strip() + "\n"
    agents = target / "AGENTS.md"
    current = agents.read_text(encoding="utf-8") if agents.exists() else ""
    if PROFILE_HEADING in current:
        done.append("AGENTS.md already has a Factory profile: left as it is")
    else:
        sep = "" if not current else ("\n" if current.endswith("\n") else "\n\n")
        agents.write_text(current + sep + ("\n" if current else "") + body, encoding="utf-8")
        done.append(f"added the '{name}' Factory profile to AGENTS.md")
    claude = target / "CLAUDE.md"
    ctext = claude.read_text(encoding="utf-8") if claude.exists() else ""
    if not any(l.strip() == "@AGENTS.md" for l in ctext.splitlines()):
        claude.write_text(ctext + ("\n" if ctext and not ctext.endswith("\n") else "") + ("\n" if ctext else "") +
                          "@AGENTS.md\n", encoding="utf-8")
        done.append("CLAUDE.md now imports AGENTS.md (one line: @AGENTS.md)")
    return done


def main(argv):
    ap = argparse.ArgumentParser(prog="install.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--upgrade", action="store_true")
    ap.add_argument("--prompts", action="store_true")
    ap.add_argument("--profile")
    a = ap.parse_args(argv)
    target = Path(a.project).resolve()
    if not (target / ".git").exists():
        die(f"{target} isn't the root of a git repository")
    if sys.version_info < (3, 10):
        die("the factory needs Python 3.10 or later")
    if a.prompts and not a.upgrade:
        die("--prompts only goes with --upgrade (a first install always copies the prompts)")
    if a.profile and a.profile not in profile_names():
        die(f"no profile {a.profile!r}; choose one of: {', '.join(profile_names())}")

    files = list(template_files())
    if not a.upgrade:
        clashes = [f for f in files if (target / f).exists()]
        if clashes:
            die("these files already exist; run with --upgrade, or move them first:\n  " + "\n  ".join(clashes))
    keep = ("factory/config.json", "factory/seed-users.json") if a.prompts else TAILORED
    backup = target / "factory" / "archive" / f"prompts-{datetime.now():%Y%m%d-%H%M%S}"
    copied, kept, backed, same = [], [], 0, 0
    for rel in files:
        src, dst = TEMPLATE / rel, target / rel
        if a.upgrade and dst.exists() and rel.startswith(keep):
            if not filecmp.cmp(src, dst, shallow=False):
                kept.append(rel)
            continue
        if dst.exists() and filecmp.cmp(src, dst, shallow=False):
            same += 1
            continue
        if a.upgrade and dst.exists() and rel.startswith(PROMPTS):
            (backup / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup / rel)
            backed += 1
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)

    gitignore = target / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    missing = [line for line in IGNORE if line not in existing]
    if missing:
        with gitignore.open("a", encoding="utf-8") as f:
            if existing and existing[-1].strip():
                f.write("\n")
            f.write("# auto-factory runtime state\n" + "\n".join(missing) + "\n")
    subprocess.run(["git", "config", "core.longpaths", "true"], cwd=target, capture_output=True)
    profile_notes = add_profile(target, a.profile) if a.profile else []

    print(f"{'Upgraded' if a.upgrade else 'Installed'} auto-factory "
          f"{(TEMPLATE / 'factory' / 'VERSION').read_text().strip()} in {target}")
    print(f"  {len(copied)} files written, {same} unchanged" + (f", {len(missing)} .gitignore lines added" if missing else ""))
    if backed:
        print(f"  Your previous prompts ({backed} files) are saved in {backup.relative_to(target).as_posix()}/")
    for note in profile_notes:
        print(f"  {note}")
    if kept:
        print("  Kept your versions of these (add --prompts to replace the prompts with the new ones):")
        for rel in kept:
            print(f"    {rel}")
    has_profile = (target / "AGENTS.md").exists() and PROFILE_HEADING in (target / "AGENTS.md").read_text(encoding="utf-8")
    if not has_profile:
        print(f"\n  No Factory profile yet. Add one so the agents know this project:\n"
              f"    python install.py \"{target}\" --upgrade --profile <{'|'.join(profile_names())}>")
    if not a.upgrade:
        print("""
Next steps:
  1. Open AGENTS.md and replace the [bracketed] parts of the Factory profile
     (what the project is, roles, sensitive areas, where auth and data rules live).
  2. Optional: factory/seed-users.json with test-only users per role, and a
     .env.factory template with local-only values ({DB}, {PORT} are filled per job).
  3. Create the GitHub labels (needs the GitHub CLI, logged in):
       gh label create factory --color 5319E7 --description "Build this with the factory"
       gh label create factory:needs-info --color FBCA04 --description "The factory asked the author"
       gh label create factory:needs-human --color D93F0B --description "The factory needs a human decision"
  4. Commit the files above and push them to the base branch (jobs branch from origin).
  5. python factory/bin/serve.py, open the printed link, set the check steps in
     Settings, and press Test on main.
  6. Label a small issue `factory`, then /factory run (Claude Code), $factory run (Codex)
     or python factory/bin/run.py.""")


if __name__ == "__main__":
    main(sys.argv[1:])
