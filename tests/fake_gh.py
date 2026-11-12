"""A stand-in for the GitHub CLI, for tests. State lives in $FAKE_GH_STATE (JSON).

Supports only the calls the factory makes. Unknown calls exit 2 so a test
notices when the scripts start using something new.
"""

import json
import os
import sys

STATE = os.environ["FAKE_GH_STATE"]
OPERATOR = "operator"


def load():
    with open(STATE, encoding="utf-8") as f:
        return json.load(f)


def save(s):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def tick(s):
    s["clock"] = s.get("clock", 0) + 1
    return f"2026-11-12T10:{s['clock'] // 60:02d}:{s['clock'] % 60:02d}Z"


def body_of(args):
    return sys.stdin.read() if opt(args, "--body-file") == "-" else opt(args, "--body", "")


def pick(obj, fields):
    return {k: obj.get(k) for k in fields.split(",")} if fields else obj


def main(a):
    s = load()
    s.setdefault("calls", []).append(a)
    out = None
    if a[:2] == ["api", "user"]:
        out = OPERATOR
    elif a[0] == "issue":
        if a[1] == "list":
            label = opt(a, "--label")
            out = [pick(i, opt(a, "--json")) for i in s["issues"].values()
                   if i["state"] == "OPEN" and any(lb["name"] == label for lb in i["labels"])]
        else:
            issue = s["issues"][str(a[2])]
            if a[1] == "view":
                out = pick(issue, opt(a, "--json"))
            elif a[1] == "comment":
                issue["comments"].append({"author": {"login": OPERATOR}, "body": body_of(a), "createdAt": tick(s)})
                out = ""
            elif a[1] == "edit":
                if opt(a, "--add-label"):
                    for name in opt(a, "--add-label").split(","):
                        if name not in [lb["name"] for lb in issue["labels"]]:
                            issue["labels"].append({"name": name})
                if opt(a, "--remove-label"):
                    drop = set(opt(a, "--remove-label").split(","))
                    issue["labels"] = [lb for lb in issue["labels"] if lb["name"] not in drop]
                out = ""
    elif a[0] == "pr":
        prs = s.setdefault("prs", {})
        if a[1] == "list":
            out = [pick(p, opt(a, "--json")) for p in prs.values()
                   if p["headRefName"] == opt(a, "--head") and p["state"] == "OPEN"]
        elif a[1] == "create":
            n = str(100 + len(prs) + 1)
            prs[n] = {"number": int(n), "url": f"https://example.test/pr/{n}", "headRefName": opt(a, "--head"),
                      "state": "OPEN", "isDraft": "--draft" in a, "comments": [], "body": opt(a, "--body", "")}
            out = prs[n]["url"]
        else:
            pr = prs[str(a[2])]
            if a[1] == "view":
                out = pick(pr, opt(a, "--json"))
            elif a[1] == "ready":
                pr["isDraft"] = False
                out = ""
            elif a[1] == "comment":
                pr["comments"].append(body_of(a))
                out = ""
            elif a[1] == "merge":
                if s.get("fail_merge"):
                    save(s)
                    print("merge blocked by branch protection", file=sys.stderr)
                    return 1
                pr["state"] = "MERGED"
                pr["method"] = a[3]
                out = ""
            elif a[1] == "close":
                pr["state"] = "CLOSED"
                out = ""
    if out is None:
        save(s)
        print(f"fake gh: unsupported call {a}", file=sys.stderr)
        return 2
    save(s)
    print(out if isinstance(out, str) else json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
