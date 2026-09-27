#!/usr/bin/env python3
"""The pull-request workflow is present, read-only, and runs every root test.

No network. Fails when .github/workflows/pr-tests.yml is missing, does not
trigger on pull_request (including a pull_request that is not limited to
main), uses pull_request_target, grants any permission other than
contents: read, leaves a uses: action unpinned, references secrets., or does
not run a test_*.py file in the repo root.
"""
import glob
import os
import re
import sys

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "pr-tests.yml")
SHA = re.compile(r"[\w.-]+(?:/[\w.-]+)+@[0-9a-f]{40}\Z")


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def _strip_comments(text):
    out = []
    for line in text.splitlines():
        in_single = in_double = False
        cut = None
        for i, ch in enumerate(line):
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "#" and not in_single and not in_double:
                cut = i
                break
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _block_after(lines, i):
    """Lines more indented than lines[i], stripped. `i` points at the key line."""
    header = re.match(r"^([ \t]*)\S", lines[i])
    indent = len(header.group(1)) if header else 0
    rest = lines[i].split(":", 1)[1].strip() if ":" in lines[i] else ""
    body = [rest] if rest else []
    j = i + 1
    while j < len(lines):
        line = lines[j]
        if line.strip() == "":
            j += 1
            continue
        if _indent(line) <= indent:
            break
        body.append(line.strip())
        j += 1
    return body


def _keyed_blocks(text, key):
    lines = text.splitlines()
    found = []
    for i, line in enumerate(lines):
        m = re.match(rf"^([ \t]*){key}[ \t]*:[ \t]*(.*)$", line)
        if m:
            found.append((len(m.group(1)), _block_after(lines, i)))
    return found


def _norm_perm(item):
    item = item.strip().strip("{}")
    parts = []
    for piece in item.split(","):
        piece = piece.strip()
        if not piece:
            continue
        m = re.fullmatch(r"([A-Za-z0-9_-]+)[ \t]*:[ \t]*([A-Za-z0-9_-]+)", piece)
        parts.append(f"{m.group(1)}: {m.group(2)}" if m else piece)
    return parts


def _run_scripts(text):
    lines = text.splitlines()
    scripts = []
    i = 0
    while i < len(lines):
        m = re.match(r"^([ \t]*)run[ \t]*:[ \t]*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        rest = m.group(2).strip()
        if rest in {"|", "|-", "|+", ">", ">-", ">+"}:
            i += 1
            body = []
            while i < len(lines):
                line = lines[i]
                if line.strip() == "":
                    body.append("")
                    i += 1
                    continue
                if _indent(line) <= indent:
                    break
                body.append(line)
                i += 1
            scripts.append("\n".join(body))
        else:
            scripts.append(rest.strip("'\""))
            i += 1
    return scripts


def _glob_runs_every_test(script):
    """A bash loop over test_*.py that fails the step if python3 fails."""
    if "test_*.py" not in script:
        return False
    if re.search(r"\|\|\s*true\b", script) or re.search(r"\|\|\s*echo\b", script):
        return False
    if not re.search(r"\bset\s+-[^\n]*\be", script):
        return False
    direct = re.search(r"for[ \t]+(\w+)[ \t]+in[ \t]+test_\*\.py\b", script)
    if direct and re.search(rf"\bpython3?[ \t]+['\"]?\$\{{?{direct.group(1)}\}}?", script):
        return True
    arr = re.search(r"(\w+)=\([ \t]*test_\*\.py[ \t]*\)", script)
    if not arr:
        return False
    loop = re.search(
        rf"for[ \t]+(\w+)[ \t]+in[ \t]+['\"]?\$\{{{arr.group(1)}\[@\]\}}['\"]?", script)
    if not loop:
        return False
    return re.search(rf"\bpython3?[ \t]+['\"]?\$\{{?{loop.group(1)}\}}?", script) is not None


def problems(text, test_names):
    """Faults in a workflow document. Empty means it meets the PR-test rules."""
    text = _strip_comments(text)
    faults = []
    if re.search(r"pull_request_target", text):
        faults.append("uses pull_request_target")
    triggers = _keyed_blocks(text, "pull_request")
    if not triggers:
        faults.append("does not trigger on pull_request")
    else:
        for _indent, body in triggers:
            blob = "\n".join(body)
            listed = re.findall(r"(?m)^-[ \t]*(\S+)[ \t]*$", blob)
            inline = re.search(r"branches[ \t]*:[ \t]*\[([^\]]*)\]", blob)
            names = [p.strip() for p in inline.group(1).split(",")] if inline else listed
            names = [n.strip("'\"") for n in names if n.strip()]
            if names != ["main"]:
                faults.append("pull_request is not limited to main")
                break
    if not _keyed_blocks(text, "workflow_dispatch"):
        faults.append("does not allow workflow_dispatch")

    perms = _keyed_blocks(text, "permissions")
    if not any(indent == 0 for indent, _body in perms):
        faults.append("permissions are not exactly contents: read")
    for indent, body in perms:
        where = "top-level" if indent == 0 else "nested"
        norm = []
        for item in body:
            norm.extend(_norm_perm(item))
        if norm != ["contents: read"]:
            shown = ", ".join(norm) if norm else "(empty)"
            faults.append(f"{where} permissions are {shown}, not contents: read")

    for spec in re.findall(r"(?m)^[ \t]*(?:-[ \t]*)?uses[ \t]*:[ \t]*['\"]?([^'\"\s]+)", text):
        if not SHA.fullmatch(spec):
            faults.append(f"uses: is not pinned to a 40-character SHA ({spec})")
    if re.search(r"actions/checkout@", text) and not re.search(
            r"persist-credentials[ \t]*:[ \t]*false\b", text):
        faults.append("checkout does not set persist-credentials: false")

    if "secrets." in text:
        faults.append("references secrets.")
    if re.search(r"(?m)^[ \t]*continue-on-error[ \t]*:", text):
        faults.append("sets continue-on-error, so a failing test would not fail the job")
    if re.search(r"\|\|\s*true\b", text) or re.search(r"\|\|\s*echo\b", text):
        faults.append("swallows a command failure with || true or || echo")

    if not re.search(r"(?m)^concurrency[ \t]*:", text) or not re.search(
            r"cancel-in-progress[ \t]*:[ \t]*true\b", text):
        faults.append("does not cancel superseded runs")
    timeout = re.search(r"timeout-minutes[ \t]*:[ \t]*(\d+)", text)
    if not timeout or not 10 <= int(timeout.group(1)) <= 60:
        faults.append("timeout-minutes is missing or not between 10 and 60")

    scripts = _run_scripts(text)
    swallowed = any(
        re.search(r"\|\|\s*true\b", s) or re.search(r"\|\|\s*echo\b", s) for s in scripts)
    glob_ok = (not swallowed) and any(_glob_runs_every_test(s) for s in scripts)
    for name in test_names:
        explicit = any(
            re.search(rf"\bpython3?[ \t]+['\"]?{re.escape(name)}['\"]?", s)
            and not re.search(r"\|\|\s*true\b", s)
            and not re.search(r"\|\|\s*echo\b", s)
            for s in scripts)
        if not explicit and not glob_ok:
            faults.append(f"does not run {name}")
    return faults


def _root_tests():
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "test_*.py")))


print("pull-request workflow")
_names = _root_tests()
ok(bool(_names), "the repo root has test_*.py files")
print("  tests:", ", ".join(_names))
if not os.path.isfile(WORKFLOW):
    ok(False, ".github/workflows/pr-tests.yml is missing")
else:
    _text = open(WORKFLOW, encoding="utf-8").read()
    _faults = problems(_text, _names)
    if _faults:
        for _f in _faults:
            ok(False, _f)
    else:
        ok(True, "pr-tests.yml is read-only, pinned, and runs every root test")

print("\nthe checker rejects a workflow that would hide a failure")
_BAD = [
    ("no pull_request event",
     "name: x\non:\n  push:\npermissions:\n  contents: read\n"),
    ("pull_request_target",
     "name: x\non:\n  pull_request_target:\n    branches: [main]\n"
     "permissions:\n  contents: read\n"),
    ("contents: write",
     "name: x\non:\n  pull_request:\n    branches: [main]\n  workflow_dispatch:\n"
     "permissions:\n  contents: write\n"),
    ("an extra permission",
     "name: x\non:\n  pull_request:\n    branches: [main]\n  workflow_dispatch:\n"
     "permissions:\n  contents: read\n  issues: write\n"),
    ("a floating action tag",
     "name: x\non:\n  pull_request:\n    branches: [main]\n  workflow_dispatch:\n"
     "permissions:\n  contents: read\njobs:\n  t:\n    steps:\n"
     "      - uses: actions/checkout@v4\n"),
    ("a secrets reference",
     "name: x\non:\n  pull_request:\n    branches: [main]\n  workflow_dispatch:\n"
     "permissions:\n  contents: read\nenv:\n  TOKEN: ${{ secrets.GITHUB_TOKEN }}\n"),
]
for _why, _doc in _BAD:
    ok(bool(problems(_doc, ["test_pr_ci.py"])), f"rejects {_why}")

_GOOD_SHA = "0123456789abcdef0123456789abcdef01234567"
_GOOD = f"""name: PR tests
on:
  pull_request:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
concurrency:
  group: pr-tests
  cancel-in-progress: true
jobs:
  test:
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@{_GOOD_SHA}
        with:
          persist-credentials: false
      - uses: actions/setup-python@{_GOOD_SHA}
      - name: Run every root test
        run: |
          set -euo pipefail
          tests=(test_*.py)
          for f in "${{tests[@]}}"; do
            python3 "$f"
          done
"""
ok(problems(_GOOD, ["test_pr_ci.py", "test_audit.py"]) == [],
   "accepts a pinned read-only workflow that loops over test_*.py")
ok(any("not pinned" in f for f in problems(
    _GOOD.replace(_GOOD_SHA, "v4", 1), ["test_pr_ci.py"])),
   "rejects one floating action tag even when the rest is valid")
_with_secret = _GOOD.replace(
    "concurrency:", "env:\n  K: ${{ secrets.X }}\nconcurrency:", 1)
ok(any("secrets." in f for f in problems(_with_secret, ["test_pr_ci.py"])),
   "rejects a secrets reference even when the rest is valid")
ok(any(f.startswith("does not run test_left_out.py")
       for f in problems(_GOOD.replace("test_*.py", "test_pr_ci.py"),
                         ["test_pr_ci.py", "test_left_out.py"])),
   "rejects a workflow that names one test file and skips another")

print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'all pull-request workflow checks passed'}")
for _f in FAILS:
    print("   -", _f)
sys.exit(1 if FAILS else 0)
