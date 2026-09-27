#!/usr/bin/env python3
"""The pull-request workflow is present, read-only, and runs every root test.

No network. Fails when .github/workflows/pr-tests.yml is missing, does not
trigger on pull_request (including a pull_request that is not limited to
main), uses pull_request_target, grants any permission other than
contents: read, leaves a uses: action unpinned, references secrets, hides a
failure, or does not run a test_*.py file in the repo root.

Also fails when any workflow pins a uses: to something other than a full
commit SHA, when a git push line swallows failure, when any workflow sets
continue-on-error, or when a pushing workflow's push step still exits 0
after the remote rejects the push or a rebase conflicts, or exits non-zero
when there is nothing to commit.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "pr-tests.yml")
SHA = re.compile(r"[\w.-]+(?:/[\w.-]+)+@[0-9a-f]{40}\Z")
_CONTINUE_ON_ERROR = re.compile(r"""(?i)["']?continue-on-error["']?\s*:""")
WF_DIR = os.path.join(ROOT, ".github", "workflows")
_USES_RE = re.compile(r"(?m)(?:^|[\s{,])uses[ \t]*:[ \t]*['\"]?([^'\"\s#>,}]+)")
_PUSH_SWALLOW = re.compile(r"\|\|\s*(?:true\b|:(?:\s|$)|exit\s+0\b|echo\b)")


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


def _uses_specs(text):
    return [m.group(1).strip() for m in _USES_RE.finditer(text)]


def _push_swallow_faults(text):
    faults = []
    for line in text.splitlines():
        if "git push" not in line:
            continue
        if _PUSH_SWALLOW.search(line):
            faults.append(f"git push failure is swallowed ({line.strip()})")
    return faults


def _flow_items(text):
    start = text.find("[")
    if start < 0:
        return []
    items = []
    depth = 0
    buf = []
    for ch in text[start + 1:]:
        if ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            if ch == "]" and depth == 0:
                item = "".join(buf).strip()
                if item:
                    items.append(item)
                break
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            item = "".join(buf).strip()
            if item:
                items.append(item)
            buf = []
        else:
            buf.append(ch)
    return items


def _steps(text):
    """Text of each step under every steps: block, including flow-style items."""
    lines = text.splitlines()
    found = []
    i = 0
    n = len(lines)
    while i < n:
        m = re.match(r"^([ \t]*)steps[ \t]*:[ \t]*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        base = len(m.group(1))
        inline = m.group(2).strip()
        if inline.startswith("["):
            blob = inline
            while blob.count("[") > blob.count("]") and i + 1 < n:
                i += 1
                blob += "\n" + lines[i]
            found.extend(_flow_items(blob))
            i += 1
            continue
        i += 1
        step = None
        step_indent = None
        while i < n:
            line = lines[i]
            if line.strip() == "":
                if step is not None:
                    step.append(line)
                i += 1
                continue
            ind = _indent(line)
            if ind <= base:
                break
            dm = re.match(r"^([ \t]*)-[ \t]+(.*)$", line)
            if dm and (step_indent is None or len(dm.group(1)) == step_indent):
                if step is not None:
                    found.append("\n".join(step))
                step_indent = len(dm.group(1))
                step = [dm.group(2)]
                i += 1
                continue
            if step is not None and ind > step_indent:
                step.append(line.strip())
                i += 1
                continue
            i += 1
        if step is not None:
            found.append("\n".join(step))
    return found


def _persist_faults(text):
    faults = []
    for step in _steps(text):
        if "actions/checkout@" not in step:
            continue
        if not re.search(r"persist-credentials[ \t]*:[ \t]*['\"]?false\b", step):
            faults.append("a checkout step does not set persist-credentials: false")
    return faults


def _top_keyed_body(text, key):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"^{key}[ \t]*:", line):
            return "\n".join(_block_after(lines, i))
    return ""


def _named_run_scripts(text):
    """(step name, script) for each run:. Names are the nearest preceding name:."""
    lines = text.splitlines()
    found = []
    i = 0
    while i < len(lines):
        m = re.match(r"^([ \t]*)run[ \t]*:[ \t]*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        name = ""
        for k in range(i - 1, -1, -1):
            prev = lines[k]
            if prev.strip() == "":
                continue
            nm = re.match(r"^[ \t]*(?:-[ \t]+)?name[ \t]*:[ \t]*(.*?)\s*$", prev)
            if nm and _indent(prev) <= indent:
                name = nm.group(1).strip().strip("'\"")
                break
            if _indent(prev) + 2 < indent and not prev.lstrip().startswith("-"):
                break
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
            found.append((name, "\n".join(body)))
        else:
            found.append((name, rest.strip("'\"")))
            i += 1
    return found


def _dedent_run(script):
    """Drop the YAML block indent so a heredoc body is real Python."""
    lines = script.split("\n")
    indents = [len(line) - len(line.lstrip(" ")) for line in lines if line.strip()]
    if not indents:
        return script
    n = min(indents)
    out = []
    for line in lines:
        if line.strip() and line.startswith(" " * n):
            out.append(line[n:])
        elif line.strip():
            out.append(line.lstrip(" "))
        else:
            out.append("")
    return "\n".join(out)


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


def _test_step_if_faults(text):
    """Any if: on the step that runs the root tests, including if: success()."""
    faults = []
    for step in _steps(text):
        if "test_*.py" not in step and not re.search(r"python3?[ \t]+['\"]?test_", step):
            continue
        if re.search(r"""(?m)(?:^|[{\s,])["']?if["']?[ \t]*:""", step):
            faults.append("the test step sets if:")
    return faults


def _pull_request_types(text):
    """True when the pull_request trigger restricts types:."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"""^([ \t]*)["']?pull_request["']?[ \t]*:(.*)$""", lines[i])
        if not m:
            i += 1
            continue
        if re.search(r"""(?i)["']?types["']?[ \t]*:""", m.group(2)):
            return True
        base = len(m.group(1))
        j = i + 1
        while j < len(lines):
            line = lines[j]
            if line.strip() == "":
                j += 1
                continue
            if _indent(line) <= base:
                break
            if re.search(r"""(?i)["']?types["']?[ \t]*:""", line):
                return True
            j += 1
        i = j
    return False


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

    for spec in _uses_specs(text):
        if not SHA.fullmatch(spec):
            faults.append(f"uses: is not pinned to a 40-character SHA ({spec})")
    faults.extend(_persist_faults(text))

    if (re.search(r"(?i)secrets\s*[.\[]", text)
            or re.search(r"(?i)tojson\s*\(\s*secrets\b", text)):
        faults.append("references secrets.")
    if _CONTINUE_ON_ERROR.search(text):
        faults.append("sets continue-on-error, so a failing test would not fail the job")
    if re.search(r"(?i)(?:^|[\s{,])[\"']?if[\"']?[ \t]*:[ \t]*(\$\{\{\s*)?['\"]?false\b", text):
        faults.append("sets if: false")
    faults.extend(_test_step_if_faults(text))
    trigger = _top_keyed_body(text, "on")
    if re.search(r"(?i)(?<![\w-])[\"']?paths-ignore[\"']?[ \t]*:", trigger) or re.search(
            r"(?i)(?<![\w-])[\"']?paths[\"']?[ \t]*:", trigger):
        faults.append("trigger sets paths or paths-ignore")
    if _pull_request_types(text):
        faults.append("pull_request trigger sets types")
    if re.search(r"(?i)shell[ \t]*:[ \t]*['\"]?bash[ \t]*\{0\}", text):
        faults.append("shell: bash {0} disables errexit")
    if re.search(r"\|\|\s*true\b", text) or re.search(r"\|\|\s*echo\b", text):
        faults.append("swallows a command failure with || true or || echo")
    faults.extend(_push_swallow_faults(text))

    if not re.search(r"(?m)^concurrency[ \t]*:", text) or not re.search(
            r"cancel-in-progress[ \t]*:[ \t]*true\b", text):
        faults.append("does not cancel superseded runs")
    timeout = re.search(r"timeout-minutes[ \t]*:[ \t]*(\d+)", text)
    if not timeout or not 10 <= int(timeout.group(1)) <= 60:
        faults.append("timeout-minutes is missing or not between 10 and 60")

    scripts = _run_scripts(text)
    if any(re.search(r"\bset\s+\+e", s) for s in scripts):
        faults.append("set +e in a run step")
    if any(re.search(r"\bset\s+\+o\s+errexit\b", s) for s in scripts):
        faults.append("set +o errexit in a run step")
    for script in scripts:
        for line in script.splitlines():
            if re.search(r"\|\|\s*(?:true\b|:(?:\s|$)|exit\s+0\b)", line):
                faults.append(f"a run line swallows failure ({line.strip()})")
                break
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
ok(any("not pinned" in f for f in problems(
    _GOOD.replace(f"- uses: actions/checkout@{_GOOD_SHA}",
                  "- {uses: actions/checkout@v1}"),
    ["test_pr_ci.py"])),
   "rejects a flow-style {uses: action@v1}")
ok(any("continue-on-error" in f for f in problems(
    _GOOD.replace("    steps:\n",
                  "    steps:\n      - continue-on-error: true\n        run: echo hi\n"),
    ["test_pr_ci.py"])),
   "rejects - continue-on-error: true in a list")
ok(any("set +e" in f for f in problems(
    _GOOD.replace("set -euo pipefail", "set +e"), ["test_pr_ci.py"])),
   "rejects set +e in a run step")
for _snippet in (
        "git push origin main || true",
        "git push origin main || :",
        "git push origin main || exit 0",
        'git push origin main || echo "failed"',
):
    ok(bool(_push_swallow_faults(_snippet)), f"rejects a swallowed push: {_snippet}")
ok(_push_swallow_faults("git push origin main") == [],
   "a bare git push is not treated as swallowed")
ok(_push_swallow_faults("python3 sandbox_close.py || echo kept") == [],
   "|| echo on a line that is not git push is not a swallowed push")
ok(any("secrets." in f for f in problems(
    _GOOD.replace("concurrency:", "env:\n  K: ${{ secrets['X'] }}\nconcurrency:"),
    ["test_pr_ci.py"])),
   "rejects a secrets[ ] reference")
ok(any("secrets." in f for f in problems(
    _GOOD.replace("concurrency:", "env:\n  K: ${{ toJSON(secrets) }}\nconcurrency:"),
    ["test_pr_ci.py"])),
   "rejects toJSON(secrets)")
ok(any("if: false" in f for f in problems(
    _GOOD.replace("    timeout-minutes: 20\n", "    timeout-minutes: 20\n    if: false\n"),
    ["test_pr_ci.py"])),
   "rejects if: false")
ok(any("if: false" in f for f in problems(
    _GOOD.replace("    timeout-minutes: 20\n",
                  "    timeout-minutes: 20\n    if: ${{ false }}\n"),
    ["test_pr_ci.py"])),
   "rejects if: ${{ false }}")
ok(any("secrets." in f for f in problems(
    _GOOD.replace("concurrency:", "env:\n  K: ${{ toJson(secrets) }}\nconcurrency:"),
    ["test_pr_ci.py"])),
   "rejects toJson(secrets)")
ok(any("secrets." in f for f in problems(
    _GOOD.replace("concurrency:", "env:\n  K: ${{ tojson(secrets) }}\nconcurrency:"),
    ["test_pr_ci.py"])),
   "rejects tojson(secrets)")
ok(any("the test step sets if:" in f for f in problems(
    _GOOD.replace("      - name: Run every root test\n        run: |",
                  "      - name: Run every root test\n        if: success()\n        run: |"),
    ["test_pr_ci.py"])),
   "rejects any if: on the test step")
ok(any("continue-on-error" in f for f in problems(
    _GOOD.replace("    steps:\n",
                  '    steps:\n      - "continue-on-error": true\n        run: echo hi\n'),
    ["test_pr_ci.py"])),
   'rejects a quoted "continue-on-error" key')
ok(any("paths" in f for f in problems(
    _GOOD.replace("    branches: [main]\n",
                  '    branches: [main]\n    "paths":\n      - "**"\n'),
    ["test_pr_ci.py"])),
   'rejects a quoted "paths" key on the trigger')
ok(any("types" in f for f in problems(
    _GOOD.replace("    branches: [main]\n",
                  "    branches: [main]\n    types: [opened]\n"),
    ["test_pr_ci.py"])),
   "rejects types: on the pull_request trigger")
ok(any("set +o errexit" in f for f in problems(
    _GOOD.replace("set -euo pipefail", "set +o errexit"), ["test_pr_ci.py"])),
   "rejects set +o errexit in a run step")
ok(any("bash {0}" in f for f in problems(
    _GOOD.replace("      - name: Run every root test\n        run: |",
                  "      - name: Run every root test\n        shell: bash {0}\n        run: |"),
    ["test_pr_ci.py"])),
   "rejects shell: bash {0}")
for _swallow_line, _why in (
        ('python3 "$f" || :', "|| :"),
        ('python3 "$f" || true', "|| true"),
        ('python3 "$f" || exit 0', "|| exit 0"),
):
    ok(any("swallows failure" in f for f in problems(
        _GOOD.replace('python3 "$f"', _swallow_line), ["test_pr_ci.py"])),
       f"rejects {_why} on a run line that is not git push")
ok(any("paths" in f for f in problems(
    _GOOD.replace("    branches: [main]\n",
                  "    branches: [main]\n    paths:\n      - '**'\n"),
    ["test_pr_ci.py"])),
   "rejects paths on the trigger")
ok(any("paths" in f for f in problems(
    _GOOD.replace("    branches: [main]\n",
                  "    branches: [main]\n    paths-ignore:\n      - '**.md'\n"),
    ["test_pr_ci.py"])),
   "rejects paths-ignore on the trigger")
_second_checkout = _GOOD.replace(
    f"      - uses: actions/setup-python@{_GOOD_SHA}",
    f"      - uses: actions/checkout@{_GOOD_SHA}\n"
    f"        with:\n          fetch-depth: 1\n"
    f"      - uses: actions/setup-python@{_GOOD_SHA}")
ok(any("persist-credentials" in f for f in problems(_second_checkout, ["test_pr_ci.py"])),
   "rejects a later checkout that omits persist-credentials: false")
_decoy = _GOOD.replace(
    "        with:\n          persist-credentials: false\n",
    "      - name: decoy\n        run: echo persist-credentials: false\n")
ok(any("persist-credentials" in f for f in problems(_decoy, ["test_pr_ci.py"])),
   "a persist-credentials: false string in another step does not cover checkout")
_FLOW_SHA = "0123456789abcdef0123456789abcdef01234567"
ok(_persist_faults(
    "jobs:\n  t:\n    steps: [{uses: actions/checkout@" + _FLOW_SHA + "}]") != [],
   "a flow-style checkout without persist-credentials: false fails")
ok(_persist_faults(
    "jobs:\n  t:\n    steps: [{uses: actions/checkout@" + _FLOW_SHA
    + ", with: {persist-credentials: false}}]") == [],
   "a flow-style checkout with persist-credentials: false passes")

print("\nevery workflow pins actions and does not swallow a push")
_wf_paths = sorted(glob.glob(os.path.join(WF_DIR, "*.yml")))
_wf_paths += sorted(glob.glob(os.path.join(WF_DIR, "*.yaml")))
ok(bool(_wf_paths), "the repo has workflow files")
_pin_bad = []
_swallow_bad = []
_coe_bad = []
for _path in _wf_paths:
    _raw = open(_path, encoding="utf-8").read()
    _rel = os.path.relpath(_path, ROOT)
    _stripped = _strip_comments(_raw)
    for _spec in _uses_specs(_stripped):
        if not SHA.fullmatch(_spec):
            _pin_bad.append(f"{_rel}: {_spec}")
    for _fault in _push_swallow_faults(_stripped):
        _swallow_bad.append(f"{_rel}: {_fault}")
    if _CONTINUE_ON_ERROR.search(_stripped):
        _coe_bad.append(_rel)
if _pin_bad:
    for _item in _pin_bad:
        ok(False, f"uses: is not pinned to a 40-character SHA ({_item})")
else:
    ok(True, "every uses: in every workflow is a 40-character SHA")
if _swallow_bad:
    for _item in _swallow_bad:
        ok(False, _item)
else:
    ok(True, "no git push line swallows failure with || true, || :, || exit 0, or || echo")
if _coe_bad:
    for _item in _coe_bad:
        ok(False, f"{_item} sets continue-on-error")
else:
    ok(True, "no workflow step sets continue-on-error")


def _added_paths(script):
    """Paths a push step stages, expanding the simple VAR=\"a b\" assignments it uses."""
    assigned = {}
    for m in re.finditer(r'(?m)^\s*([A-Z_][A-Z0-9_]*)="([^"]*)"', script):
        assigned[m.group(1)] = m.group(2)
    paths = []
    for line in script.splitlines():
        m = re.match(r"\s*git add(?:\s+--)?\s+(.+)$", line)
        if not m:
            continue
        for tok in m.group(1).split():
            if tok == "--":
                continue
            if tok.startswith("$"):
                name = tok[1:].lstrip("{").rstrip("}")
                paths.extend(assigned.get(name, "").split())
            else:
                paths.append(tok)
    return paths


def _dirty(path):
    if os.path.isdir(path):
        for dirpath, _dirs, files in os.walk(path):
            for name in files:
                _dirty(os.path.join(dirpath, name))
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if path.endswith(".json"):
        with open(path, "w") as fh:
            fh.write('{"changed": true}\n')
    else:
        with open(path, "w") as fh:
            fh.write("changed\n")


def _rewrite(path, plain, json_text):
    if os.path.isdir(path):
        for dirpath, _dirs, files in os.walk(path):
            for name in files:
                _rewrite(os.path.join(dirpath, name), plain, json_text)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(json_text if path.endswith(".json") else plain)


def _push_rejected(script, mode="reject"):
    """Run a push step against a local remote.

    mode "reject": the tree is dirty and every git push fails.
    mode "conflict": origin/main changes the same paths, then every push fails.
    mode "empty": the tree matches HEAD, so the step must exit 0 without pushing.
    """
    tmp = tempfile.mkdtemp(prefix="push-fail-")
    try:
        origin = os.path.join(tmp, "origin.git")
        local = os.path.join(tmp, "local")
        bindir = os.path.join(tmp, "bin")
        os.makedirs(bindir)
        real_git = shutil.which("git")
        with open(os.path.join(bindir, "git"), "w") as fh:
            fh.write(
                "#!/bin/sh\n"
                "for a in \"$@\"; do\n"
                "  if [ \"$a\" = \"push\" ]; then\n"
                "    echo hook-rejected-push >&2\n"
                "    exit 1\n"
                "  fi\n"
                "done\n"
                f"exec {real_git} \"$@\"\n"
            )
        os.chmod(os.path.join(bindir, "git"), 0o755)
        env = os.environ.copy()
        env.update({
            "GIT_AUTHOR_NAME": "T",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "T",
            "GIT_COMMITTER_EMAIL": "t@example.com",
            "GIT_TERMINAL_PROMPT": "0",
            "COMMIT_SITE": "true",
            "GIT_CONFIG_COUNT": "3",
            "GIT_CONFIG_KEY_0": "protocol.file.allow",
            "GIT_CONFIG_VALUE_0": "always",
            "GIT_CONFIG_KEY_1": "safe.directory",
            "GIT_CONFIG_VALUE_1": "*",
            "GIT_CONFIG_KEY_2": "commit.gpgsign",
            "GIT_CONFIG_VALUE_2": "false",
        })

        def git(cwd, *args):
            r = subprocess.run(
                [real_git, "-C", cwd, *args], env=env,
                capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(
                    "git " + " ".join(args) + " failed: " + (r.stderr or r.stdout))

        git(tmp, "init", "--bare", "-b", "main", origin)
        git(tmp, "init", "-b", "main", local)
        files = {
            "data/sandbox_closes/close.json": '{"v":0}\n',
            "data/sandbox_closes/boards.json": '{"v":0}\n',
            "data/sandbox_closes/watchdog.json": '{"v":0}\n',
            "data/settlement_mismatches.json": '{"markets":[]}\n',
            "data/sandbox_ledger.json": '{"quotes":[]}\n',
            "data/stages.json": "{}\n",
            "data/production_leads.json": "{}\n",
            "data/sandbox_archive/keep.json": "[]\n",
            "data/espn_history/keep.json": "{}\n",
            "public_site/index.html": "old\n",
            "public_site/sandbox.html": "old\n",
            "public_site/production.html": "old\n",
        }
        for rel, text in files.items():
            dest = os.path.join(local, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w") as fh:
                fh.write(text)
        git(local, "add", "-A")
        git(local, "commit", "-m", "base")
        git(local, "remote", "add", "origin", origin)
        git(local, "push", "origin", "main")
        added = _added_paths(_dedent_run(script))
        if mode == "conflict":
            # A second clone lands a different copy of the same paths on
            # origin/main before the step runs, so a later rebase conflicts.
            other = os.path.join(tmp, "other")
            git(tmp, "clone", origin, other)
            for rel in added:
                _rewrite(os.path.join(other, rel), "remote-side\n", '{"remote": true}\n')
            git(other, "add", "-A")
            git(other, "commit", "-m", "remote edit")
            git(other, "push", "origin", "main")
        # Only the paths this step stages. Other dirty files make `git pull --rebase`
        # fail for a reason other than the rejected push, which hides a loop that
        # exits 0 when the rebase itself succeeds. An empty diff leaves them clean.
        if mode != "empty":
            for rel in added:
                _dirty(os.path.join(local, rel))
        same = mode == "empty"
        with open(os.path.join(local, "site_root.py"), "w") as fh:
            fh.write(
                "import os\n"
                "os.makedirs('public_site', exist_ok=True)\n"
                "open('public_site/index.html','w').write(%r)\n"
                % ("old\n" if same else "rebuilt-site-root\n")
            )
        with open(os.path.join(local, "sandbox_close.py"), "w") as fh:
            if same:
                fh.write(
                    "import os, sys\n"
                    "writer = 'close'\n"
                    "if '--writer' in sys.argv:\n"
                    "    writer = sys.argv[sys.argv.index('--writer') + 1]\n"
                    "os.makedirs('data/sandbox_closes', exist_ok=True)\n"
                    "open('data/sandbox_closes/%s.json' % writer, 'w').write('{\"v\":0}\\n')\n"
                )
            else:
                fh.write(
                    "import os, sys\n"
                    "writer = 'close'\n"
                    "if '--writer' in sys.argv:\n"
                    "    writer = sys.argv[sys.argv.index('--writer') + 1]\n"
                    "os.makedirs('data/sandbox_closes', exist_ok=True)\n"
                    "open('data/sandbox_closes/%s.json' % writer, 'w').write("
                    "'{\"stub\":\"%s\"}\\n' % writer)\n"
                )
        runner = os.path.join(tmp, "runner")
        watch = os.path.join(runner, "settlement-watch")
        os.makedirs(watch)
        with open(os.path.join(watch, "settlement_mismatches.json"), "w") as fh:
            if same:
                fh.write('{"markets":[]}\n')
            else:
                fh.write(
                    '{"markets":[{"market_id":"m1","stored":"a",'
                    '"venue":"v","venue_result":"yes"}]}\n'
                )
        env["RUNNER_TEMP"] = runner
        env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
        return subprocess.run(
            ["bash", "-c", _dedent_run(script)],
            cwd=local, env=env, capture_output=True, text=True, timeout=60)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


print("\na rejected push fails the job")
_push_steps = []
for _path in _wf_paths:
    _raw = open(_path, encoding="utf-8").read()
    _rel = os.path.relpath(_path, ROOT)
    for _name, _script in _named_run_scripts(_raw):
        if "git push" in _script:
            _push_steps.append((_rel, _name, _script))
ok(bool(_push_steps), "at least one workflow step pushes")
for _need in (
        "sandbox-close.yml",
        "refresh-boards.yml",
        "backup-refresh.yml",
        "sandbox-audit.yml",
        "sandbox-tracker.yml",
):
    ok(any(_rel == os.path.join(".github", "workflows", _need) for _rel, _n, _s in _push_steps),
       f"push harness covers {_need}")
ok(sum(1 for _rel, _n, _s in _push_steps if _rel.endswith("backup-refresh.yml")) >= 2,
   "backup-refresh's snapshot push and its takeover push are both covered")
for _rel, _name, _script in _push_steps:
    _label = f"{_rel} step { _name or '(unnamed)' }"
    for _mode in ("reject", "conflict", "empty"):
        try:
            _ran = _push_rejected(_script, _mode)
        except Exception as _exc:
            ok(False, f"{_label} {_mode} harness error: {_exc}")
            continue
        _out = (_ran.stdout or "") + "\n" + (_ran.stderr or "")
        if _mode == "empty":
            _good = _ran.returncode == 0 and "hook-rejected-push" not in _out
            _why = f"{_label} exits 0 when the diff is empty"
        elif _mode == "conflict":
            _good = _ran.returncode != 0
            _why = f"{_label} exits non-zero when the rebase conflicts"
        else:
            _good = _ran.returncode != 0 and "hook-rejected-push" in _out
            _why = f"{_label} exits non-zero when the push is rejected"
        if not _good:
            _tail = [ln for ln in _out.splitlines() if ln.strip()][-12:]
            _why += f" (exit {_ran.returncode}; " + " | ".join(_tail) + ")"
        ok(_good, _why)

print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'all pull-request workflow checks passed'}")
for _f in FAILS:
    print("   -", _f)
sys.exit(1 if FAILS else 0)
