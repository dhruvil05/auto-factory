"""Install or upgrade auto-factory in a project.

Usage:
  python install.py <project folder>             first install; refuses to overwrite anything
  python install.py <project folder> --upgrade   replace the factory's scripts and dashboard;
                                                 keeps config.json, seed-users.json and the
                                                 tailored agent and skill files

It copies files and edits .gitignore. It never commits, pushes, or talks to GitHub:
the steps that need you are printed at the end.
"""

import filecmp
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "template"
IGNORE = ["/factory/jobs/", "/factory/config-history/", "/factory/archive/", "/factory/PAUSE", "/.worktrees/"]
# Files a project tailors; --upgrade leaves them alone.
TAILORED = ("factory/config.json", "factory/seed-users.json", ".claude/agents/", ".claude/skills/factory/",
            ".agents/skills/factory/")
RUNTIME = ("factory/jobs/", "factory/config-history/", "factory/archive/", ".worktrees/")


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


def main(argv):
    if not argv or argv[0] in ("-h", "--help") or len(argv) > 2 or (len(argv) == 2 and argv[1] != "--upgrade"):
        print(__doc__.strip())
        sys.exit(0 if argv and argv[0] in ("-h", "--help") else 1)
    target = Path(argv[0]).resolve()
    upgrade = len(argv) == 2
    if not (target / ".git").exists():
        die(f"{target} isn't the root of a git repository")
    if sys.version_info < (3, 10):
        die("the factory needs Python 3.10 or later")

    files = list(template_files())
    if not upgrade:
        clashes = [f for f in files if (target / f).exists()]
        if clashes:
            die("these files already exist; run with --upgrade, or move them first:\n  " + "\n  ".join(clashes))
    copied, kept, same = [], [], 0
    for rel in files:
        src, dst = TEMPLATE / rel, target / rel
        if upgrade and dst.exists() and rel.startswith(TAILORED):
            if not filecmp.cmp(src, dst, shallow=False):
                kept.append(rel)
            continue
        if dst.exists() and filecmp.cmp(src, dst, shallow=False):
            same += 1
            continue
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

    print(f"{'Upgraded' if upgrade else 'Installed'} auto-factory "
          f"{(TEMPLATE / 'factory' / 'VERSION').read_text().strip()} in {target}")
    print(f"  {len(copied)} files written, {same} unchanged" + (f", {len(missing)} .gitignore lines added" if missing else ""))
    if kept:
        print("  Kept your versions of (compare with template/ by hand if you want the new text):")
        for rel in kept:
            print(f"    {rel}")
    if not upgrade:
        print("""
Next steps:
  1. Tailor the placeholders in .claude/agents/intake.md ("This project: …") and
     .claude/agents/approver.md ("Project-specific: …").
  2. Optional: factory/seed-users.json with test-only users per role, and a
     .env.factory template with local-only values ({DB}, {PORT} are filled per job).
  3. Create the GitHub labels (needs the GitHub CLI, logged in):
       gh label create factory --color 5319E7 --description "Build this with the factory"
       gh label create factory:needs-info --color FBCA04 --description "The factory asked the author"
       gh label create factory:needs-human --color D93F0B --description "The factory needs a human decision"
  4. Commit the files above and push them to the base branch (jobs branch from origin).
  5. python factory/bin/serve.py, open the printed link, set the check steps in
     Settings, and press Test on main.
  6. Label a small issue `factory` and run /factory run in Claude Code.""")


if __name__ == "__main__":
    main(sys.argv[1:])
