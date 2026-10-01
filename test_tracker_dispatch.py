#!/usr/bin/env python3
"""The hourly watchdog starts sandbox-tracker.yml when its last success is stale.

GitHub drops scheduled slots of that workflow. production_leads.json goes stale
for an external reader once it is more than 8h old, so the watch job cannot
wait for the next cron. tracker_dispatch.decide is the rule. A failed or
unreadable run history is an error, not an empty history and not a dispatch.

No network. The workflow step is executed with a fake gh on PATH.
"""
import inspect
import json
import os
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

FAILS = []
ROOT = os.path.dirname(os.path.abspath(__file__))
WF = os.path.join(ROOT, ".github", "workflows", "backup-refresh.yml")
NOW = datetime(2026, 10, 1, 16, 0, tzinfo=timezone.utc)
TOKEN = "ghp_SHOULD_NOT_APPEAR"
MISSING = object()


def ok(cond, why):
    print(f"  {'ok  ' if cond else 'FAIL'} {why}")
    if not cond:
        FAILS.append(why)


def eq(got, want, why):
    ok(got == want, why if got == want else f"{why} — got {got!r}, want {want!r}")


try:
    import tracker_dispatch as TD
except ImportError:
    TD = None


def _ago(**kwargs):
    return NOW - timedelta(**kwargs)


def _call_decide(last, statuses, event="schedule"):
    if TD is None or not hasattr(TD, "decide"):
        return MISSING
    try:
        return TD.decide(last, statuses, NOW, event)
    except Exception as exc:
        return exc


def _is_dispatch(got):
    return isinstance(got, tuple) and len(got) == 2 and got[0] is True and isinstance(got[1], str)


def _is_hold(got):
    return (
        isinstance(got, tuple) and len(got) == 2 and got[0] is False
        and isinstance(got[1], str) and not got[1].startswith("dispatching")
    )


def assert_dispatch(last, statuses, why, event="schedule", parts=()):
    got = _call_decide(last, statuses, event)
    if got is MISSING:
        ok(False, why + " — tracker_dispatch.decide is missing")
        return
    if not _is_dispatch(got):
        ok(False, f"{why} — got {got!r}")
        return
    ok(True, why)
    for part in parts:
        ok(part in got[1], f"{why} — the line contains {part!r}")


def assert_hold(last, statuses, why, event="schedule"):
    got = _call_decide(last, statuses, event)
    if got is MISSING:
        ok(False, why + " — tracker_dispatch.decide is missing")
        return
    ok(_is_hold(got), why if _is_hold(got) else f"{why} — got {got!r}")


def assert_error(last, statuses, why, event="schedule"):
    got = _call_decide(last, statuses, event)
    if got is MISSING:
        ok(False, why + " — tracker_dispatch.decide is missing")
        return
    leaked = isinstance(got, Exception) and TOKEN in str(got)
    ok(isinstance(got, Exception) and not leaked, why if isinstance(got, Exception) and not leaked
       else f"{why} — got {got!r}")


print("dispatch rule")

ok(TD is not None and hasattr(TD, "decide"),
   "tracker_dispatch.decide is the watchdog's dispatch rule")
eq(getattr(TD, "DISPATCH_AFTER_HOURS", None), 3.5,
   "the dispatch threshold is 3.5 hours")
eq(set(getattr(TD, "OPEN_STATUSES", ())),
   {"queued", "in_progress", "pending", "waiting", "requested"},
   "unfinished means queued, in_progress, pending, waiting, or requested")

_stale = _ago(hours=4)
_fresh = _ago(hours=1)
_dispatch_line = ("4.0h", "3.5", "unfinished", "sandbox-tracker.yml", "main")

assert_dispatch(_stale, [], "stale with nothing queued: dispatch", parts=_dispatch_line)
assert_hold(_stale, ["in_progress"], "stale with a run in progress: no dispatch")
assert_hold(_stale, ["queued"], "stale with a run queued: no dispatch")
assert_hold(_stale, ["pending"], "stale with a run pending: no dispatch")
assert_hold(_stale, ["waiting"], "stale with a run waiting: no dispatch")
assert_hold(_stale, ["requested"], "stale with a run requested: no dispatch")
assert_hold(_stale, ["completed", "queued"],
            "stale with a queued run among completed ones: no dispatch")
assert_hold(_fresh, [], "fresh: no dispatch")
assert_hold(_ago(hours=3), [], "a 3h gap is inside 3.5h: no dispatch")
assert_dispatch(_stale, ["completed"],
                "a completed run is not unfinished, so a stale tracker still dispatches",
                parts=("4.0h",))
assert_dispatch(None, [], "no successful run on record, and nothing unfinished: dispatch",
                parts=("no successful run", "sandbox-tracker.yml"))
assert_hold(None, ["in_progress"],
            "no successful run, but a run is in progress: no dispatch")
assert_dispatch(_stale, [], "a manual workflow_dispatch may dispatch when the tracker is stale",
                event="workflow_dispatch", parts=("4.0h", "3.5"))
assert_hold(_fresh, [], "a manual workflow_dispatch does not dispatch a fresh tracker",
            event="workflow_dispatch")

print("\n3.5h boundary")

assert_hold(_ago(hours=3, minutes=30), [], "exactly 3.5h old: no dispatch")
assert_hold(_ago(hours=3, minutes=29, seconds=59), [], "one second under 3.5h: no dispatch")
assert_dispatch(_ago(hours=3, minutes=30, seconds=1), [],
                "one second past 3.5h: dispatch", parts=("3.5", "sandbox-tracker.yml"))

print("\nbad history is an error, not a dispatch")

assert_error("2026-10-01T12:00:00Z", [], "a last-success string is malformed")
assert_error(_ago(hours=4).replace(tzinfo=None), [], "a naive timestamp is malformed")
assert_error(_stale, None, "missing open-run history is malformed")
assert_error(_stale, "queued", "a bare status string is not an empty queue")
assert_error(_stale, ["queued", ""], "a blank status is malformed")
assert_error(_stale, ["not-a-status"], "an unrecognised status is malformed")
assert_error(_stale, [], "pull_request is not a trusted trigger", event="pull_request")
assert_error(_stale, [], "pull_request_target is not a trusted trigger",
             event="pull_request_target")
assert_error(_stale, [], "an empty event name is not a trusted trigger", event="")
_injected = "schedule; echo PWNED"
_got_injected = _call_decide(_stale, [], _injected)
ok(isinstance(_got_injected, Exception) and "PWNED" not in str(_got_injected)
   and not _is_dispatch(_got_injected),
   "an event name cannot inject shell text or count as schedule")


def _calls_of(fn):
    calls = []

    def gh(args):
        calls.append(list(args))
        return 0, json.dumps({"workflow_runs": []})

    return calls, gh


def _expect_history_error(fn, why, gh):
    if TD is None or not hasattr(TD, fn):
        ok(False, why + f" — tracker_dispatch.{fn} is missing")
        return None
    try:
        got = getattr(TD, fn)("aliu2298/edge-machine", gh=gh) if fn == "fetch_history" else getattr(TD, fn)(gh=gh)
    except Exception as exc:
        name = getattr(TD, "HistoryError", None)
        leaked = TOKEN in str(exc)
        ok(name is not None and isinstance(exc, name) and not leaked, why if not leaked
           else f"{why} — {exc!r}")
        return exc
    ok(False, f"{why} — returned {got!r}")
    return None


print("\nAPI reads fail closed")

if TD is None or not hasattr(TD, "fetch_history"):
    ok(False, "tracker_dispatch.fetch_history reads run history for decide")
else:
    _calls, _gh = _calls_of("fetch_history")

    def _gh_ok(args):
        _calls.append(list(args))
        url = args[1] if len(args) > 1 else ""
        if "status=success" in url:
            body = {"workflow_runs": [{
                "status": "completed",
                "conclusion": "success",
                "created_at": "2026-10-01T12:00:00Z",
            }]}
        elif "status=queued" in url:
            body = {"workflow_runs": [{"status": "queued"}]}
        else:
            body = {"workflow_runs": []}
        return 0, json.dumps(body)

    _calls = []
    last, statuses = TD.fetch_history("aliu2298/edge-machine", gh=_gh_ok)
    eq(last, datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
       "fetch_history keeps the success created_at")
    eq(statuses, ["queued"], "fetch_history keeps a queued run and drops empty queries")
    _paths = [c[1] for c in _calls if c and c[0] == "api"]
    ok(all(c[0] == "api" for c in _calls), "fetch_history only calls the runs API")
    ok(len(_paths) == 6 and all("per_page=1" in p and "sandbox-tracker.yml" in p for p in _paths),
       "one success read and one read per unfinished status")
    for _status in ("success", "queued", "in_progress", "pending", "waiting", "requested"):
        ok(any(f"status={_status}" in p for p in _paths),
           f"fetch_history queries status={_status}")
    ok(all(p.startswith("/repos/aliu2298/edge-machine/") for p in _paths),
       "the runs API is this repo's sandbox-tracker.yml")

    def _gh_rc(args):
        return 1, TOKEN

    _expect_history_error("fetch_history",
                          "an API error is not an empty history", _gh_rc)

    def _gh_queued_fails(args):
        url = args[1]
        if "status=queued" in url:
            return 1, TOKEN
        return 0, json.dumps({"workflow_runs": []})

    _expect_history_error("fetch_history",
                          "a later status query failing is not 'nothing queued'",
                          _gh_queued_fails)

    def _gh_bad_json(args):
        return 0, TOKEN

    _expect_history_error("fetch_history",
                          "malformed API data is not an empty history", _gh_bad_json)

    def _gh_no_key(args):
        return 0, json.dumps({"message": "Not Found"})

    _expect_history_error("fetch_history",
                          "a payload without workflow_runs is not an empty history",
                          _gh_no_key)

    def _gh_bad_time(args):
        url = args[1]
        if "status=success" in url:
            return 0, json.dumps({"workflow_runs": [{
                "status": "completed", "conclusion": "success", "created_at": "yesterday",
            }]})
        return 0, json.dumps({"workflow_runs": []})

    _expect_history_error("fetch_history",
                          "an unparseable created_at is not stale", _gh_bad_time)

    def _gh_not_success(args):
        url = args[1]
        if "status=success" in url:
            return 0, json.dumps({"workflow_runs": [{
                "status": "completed", "conclusion": "failure",
                "created_at": "2026-10-01T12:00:00Z",
            }]})
        return 0, json.dumps({"workflow_runs": []})

    _expect_history_error("fetch_history",
                          "a non-success row in the success query is malformed",
                          _gh_not_success)

    def _gh_wrong_open(args):
        url = args[1]
        if "status=success" in url:
            return 0, json.dumps({"workflow_runs": []})
        if "status=queued" in url:
            return 0, json.dumps({"workflow_runs": [{"status": "completed"}]})
        return 0, json.dumps({"workflow_runs": []})

    _expect_history_error("fetch_history",
                          "a completed row in the queued query is malformed",
                          _gh_wrong_open)

    _calls = []

    def _gh_reject(args):
        _calls.append(list(args))
        return 0, json.dumps({"workflow_runs": []})

    try:
        if hasattr(TD, "fetch_history"):
            TD.fetch_history("aliu2298/edge-machine; echo PWNED", gh=_gh_reject)
            ok(False, "a repository value with shell text is rejected")
        else:
            ok(False, "a repository value with shell text is rejected — fetch_history is missing")
    except Exception as exc:
        ok(TOKEN not in str(exc) and "PWNED" not in str(exc) and _calls == [],
           "a repository value with shell text makes no API call and is not echoed")


print("\nstart_tracker dispatches once, on main")

if TD is None or not hasattr(TD, "start_tracker"):
    ok(False, "tracker_dispatch.start_tracker is how the workflow starts a run")
else:
    _calls = []

    def _gh_dispatch(args):
        _calls.append(list(args))
        return 0, TOKEN

    TD.start_tracker(gh=_gh_dispatch)
    eq(_calls, [["workflow", "run", "sandbox-tracker.yml", "--ref", "main"]],
       "the dispatch is gh workflow run sandbox-tracker.yml --ref main, once")
    _src = inspect.getsource(TD.start_tracker)
    ok("GITHUB_REF" not in _src and "github.ref" not in _src and "shell=True" not in _src,
       "the ref is the literal main, not a shell interpolation")

    def _gh_dispatch_fails(args):
        return 1, TOKEN

    try:
        TD.start_tracker(gh=_gh_dispatch_fails)
        ok(False, "a failed dispatch is an error")
    except Exception as exc:
        ok(isinstance(exc, TD.HistoryError) and TOKEN not in str(exc),
           "a failed dispatch is an error and does not include the token")


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _run_scripts(text):
    lines = text.splitlines()
    found = []
    i = 0
    while i < len(lines):
        stripped = lines[i].lstrip(" ")
        indent = _indent(lines[i])
        if not stripped.startswith("run:"):
            i += 1
            continue
        name = ""
        for k in range(i - 1, -1, -1):
            prev = lines[k].strip()
            if prev.startswith("name:") and _indent(lines[k]) <= indent:
                name = prev.split(":", 1)[1].strip().strip("'\"")
                break
            if lines[k].strip() and _indent(lines[k]) < indent and not lines[k].lstrip().startswith("-"):
                break
        rest = stripped.split(":", 1)[1].strip()
        if rest in {"|", "|-", "|+", ">", ">-", ">+"}:
            i += 1
            body = []
            while i < len(lines):
                if lines[i].strip() == "":
                    body.append("")
                    i += 1
                    continue
                if _indent(lines[i]) <= indent:
                    break
                body.append(lines[i])
                i += 1
            found.append((name, "\n".join(body)))
        else:
            found.append((name, rest))
            i += 1
    return found


def _dedent(script):
    lines = script.split("\n")
    indents = [_indent(line) for line in lines if line.strip()]
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


def _job(text, name):
    marker = f"\n  {name}:"
    start = text.find(marker)
    if start < 0:
        return ""
    lines = text[start + 1:].splitlines()
    out = [lines[0]]
    for line in lines[1:]:
        if line.startswith("  ") and not line.startswith("   ") and line.strip():
            break
        out.append(line)
    return "\n".join(out)


def _block(text, key, indent):
    prefix = " " * indent + key + ":"
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(prefix) and line[len(prefix):].strip() in ("",) or (
                line.startswith(prefix) and not line[len(prefix):].strip().startswith("|")):
            # only a mapping key, not `run: |`
            if line.split("#", 1)[0].strip() != f"{key}:":
                continue
            body = []
            j = i + 1
            while j < len(lines):
                if lines[j].strip() == "":
                    j += 1
                    continue
                if _indent(lines[j]) <= indent:
                    break
                body.append(lines[j].split("#", 1)[0].strip())
                j += 1
            return [item for item in body if item]
    return None


_wf = open(WF, encoding="utf-8").read() if os.path.isfile(WF) else ""
_watch = _job(_wf, "watch")
_takeover = _job(_wf, "takeover")
_top = _wf.split("\njobs:", 1)[0]
_on = _top.split("\non:", 1)[-1].split("\npermissions:", 1)[0] if "\non:" in _top else ""
_scripts = _run_scripts(_wf)
_dispatch_scripts = [(name, body) for name, body in _scripts if "tracker_dispatch" in body]
_dispatch_script = _dedent(_dispatch_scripts[0][1]) if len(_dispatch_scripts) == 1 else ""

print("\nwatch job wiring")

ok("schedule:" in _on and "workflow_dispatch:" in _on and "pull_request" not in _on,
   "backup-refresh runs on schedule and workflow_dispatch only")
_top_perms = _block(_top, "permissions", 0)
ok(_top_perms is not None and any(item.startswith("actions: read") for item in _top_perms)
   and not any(item.startswith("actions: write") for item in _top_perms),
   "workflow permissions stay actions: read and do not gain actions: write")
_watch_perms = _block(_watch, "permissions", 4)
eq(_watch_perms, ["contents: write", "actions: write"],
   "the watch job, and only that scope list, has actions: write plus the contents write it already needed")
ok(_block(_takeover, "permissions", 4) is None,
   "takeover keeps the workflow permissions and does not gain actions: write")
ok("group: refresh-boards" not in _watch and "\n    concurrency:" not in _watch,
   "watch stays out of the refresh-boards concurrency group")
ok("group: refresh-boards" in _takeover, "takeover still joins refresh-boards")
ok('[ "$TAGE" -gt "${FAIL_AFTER_HOURS}" ]' in _watch,
   "the 7h tracker alarm is unchanged")
ok('FAIL_AFTER_HOURS: 7' in _top and 'STALE_AFTER_HOURS: 5' in _top,
   "takeover stays at 5h and the job still fails at 7h")
ok("|| true" not in _wf, "a failed gh api call is not discarded")
ok(len(_dispatch_scripts) == 1, "one watch step calls tracker_dispatch")
ok("from tracker_dispatch import" in _dispatch_script and "decide(" in _dispatch_script,
   "that step calls tracker_dispatch.decide")
ok("fetch_history(" in _dispatch_script and "start_tracker(" in _dispatch_script,
   "that step reads history and starts the tracker through the tested helpers")
ok(bool(_dispatch_script) and "${{" not in _dispatch_script,
   "the dispatch script does not interpolate ${{ }}")
ok("<<" in _dispatch_script and "'PY'" in _dispatch_script,
   "the dispatch script's Python is a quoted heredoc")
ok(bool(_dispatch_script) and "GH_TOKEN" not in _dispatch_script and "github.token" not in _dispatch_script,
   "the dispatch script never reads the token itself")
ok(bool(_dispatch_script) and "pull_request" not in _dispatch_script and "github.event" not in _dispatch_script,
   "the dispatch script does not read the event payload")
ok(all("${{" not in _dedent(body) for _name, body in _scripts),
   "no run script in backup-refresh.yml interpolates ${{ }}")
_dispatch_step = ""
if _dispatch_scripts:
    _name = _dispatch_scripts[0][0]
    _at = _watch.find(f"name: {_name}")
    _dispatch_step = _watch[_at:_watch.find("\n      - ", _at + 1)] if _at >= 0 else ""
ok("!cancelled()" in _dispatch_step,
   "the 7h alarm failing does not skip the dispatch")
ok("EVENT_NAME:" in _dispatch_step and "github.event_name" in _dispatch_step,
   "the event name reaches the script through env")
ok("tracker_dispatch" not in _takeover, "takeover does not dispatch the tracker")


_FAKE_GH = r"""#!/usr/bin/env python3
import os, sys
log = os.environ["GH_ARGS_LOG"]
with open(log, "a", encoding="utf-8") as fh:
    fh.write("\t".join(sys.argv[1:]) + "\n")
args = sys.argv[1:]
token = os.environ.get("GH_TOKEN", "")
if args[:1] == ["api"] and len(args) == 2 and os.environ.get("GH_FAIL_ALL") == "1":
    sys.stderr.write(token + "\n")
    sys.exit(1)
if args[:3] == ["workflow", "run", "sandbox-tracker.yml"] and args[3:] == ["--ref", "main"]:
    if os.environ.get("GH_FAIL_DISPATCH") == "1":
        sys.stderr.write(token + "\n")
        sys.exit(1)
    sys.exit(0)
if args[:1] != ["api"] or len(args) != 2:
    sys.stderr.write("unexpected\n")
    sys.exit(2)
url = args[1]
table = {
    "status=success": "GH_BODY_SUCCESS",
    "status=queued": "GH_BODY_QUEUED",
    "status=in_progress": "GH_BODY_IN_PROGRESS",
    "status=pending": "GH_BODY_PENDING",
    "status=waiting": "GH_BODY_WAITING",
    "status=requested": "GH_BODY_REQUESTED",
}
for key, var in table.items():
    if key in url:
        sys.stdout.write(os.environ.get(var, '{"workflow_runs":[]}'))
        sys.exit(0)
sys.stderr.write("unmatched\n")
sys.exit(2)
"""

_EMPTY = '{"workflow_runs":[]}'
_SUCCESS_OLD = json.dumps({"workflow_runs": [{
    "status": "completed", "conclusion": "success", "created_at": "2020-01-01T00:00:00Z",
}]})
_IN_PROGRESS = json.dumps({"workflow_runs": [{"status": "in_progress"}]})


def _run_step(extra):
    if not _dispatch_script:
        return None
    tmp = tempfile.mkdtemp(prefix="dispatch-gh-")
    log = os.path.join(tmp, "args")
    gh_path = os.path.join(tmp, "gh")
    with open(gh_path, "w", encoding="utf-8") as fh:
        fh.write(_FAKE_GH)
    os.chmod(gh_path, os.stat(gh_path).st_mode | stat.S_IEXEC)
    env = os.environ.copy()
    env["PATH"] = tmp + os.pathsep + env.get("PATH", "")
    env["GH_ARGS_LOG"] = log
    env["GH_TOKEN"] = TOKEN
    env["GITHUB_REF"] = "refs/heads/not-main"
    env["GITHUB_HEAD_REF"] = "not-main"
    env.setdefault("GITHUB_REPOSITORY", "aliu2298/edge-machine")
    env.setdefault("EVENT_NAME", "schedule")
    env.update(extra)
    ran = subprocess.run(
        ["bash", "-c", _dispatch_script],
        cwd=ROOT, env=env, capture_output=True, text=True)
    try:
        args = open(log, encoding="utf-8").read().splitlines()
    except OSError:
        args = []
    return ran, args


def _ran_clean(ran):
    if ran is None:
        return False
    blob = (ran.stdout or "") + (ran.stderr or "")
    return TOKEN not in blob and "PWNED" not in blob


print("\nthe workflow step")

if not _dispatch_script:
    ok(False, "there is no dispatch step to run")
else:
    _cases = []

    def _case(why, extra, want_rc, want_dispatch):
        ran, args = _run_step(extra)
        dispatches = [line for line in args if line.startswith("workflow\t")]
        blob = (ran.stdout or "") + "\n" + (ran.stderr or "")
        good_rc = (ran.returncode == 0) if want_rc == 0 else (ran.returncode != 0)
        good_n = (len(dispatches) == 1) if want_dispatch else (dispatches == [])
        clean = _ran_clean(ran)
        detail = ""
        if not (good_rc and good_n and clean):
            detail = f" — exit {ran.returncode}, dispatches {dispatches!r}, out {blob!r}"
        ok(good_rc and good_n and clean, why + detail)
        if want_dispatch and good_n:
            eq(dispatches, ["workflow\trun\tsandbox-tracker.yml\t--ref\tmain"],
               why + " — the only dispatch is sandbox-tracker.yml on main")
            ok("dispatching" in ran.stdout and "3.5" in ran.stdout and "h" in ran.stdout,
               why + " — logs the age and the reason")
        if not want_dispatch:
            ok(not any(line.startswith("dispatching") for line in (ran.stdout or "").splitlines()),
               why + " — does not log a dispatch")
        return ran

    _case("stale with nothing queued: the step dispatches once",
          {"GH_BODY_SUCCESS": _SUCCESS_OLD, "EVENT_NAME": "schedule"}, 0, True)
    _case("stale with a run in progress: the step does not dispatch",
          {"GH_BODY_SUCCESS": _SUCCESS_OLD, "GH_BODY_IN_PROGRESS": _IN_PROGRESS}, 0, False)
    _fresh_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _case("fresh: the step does not dispatch",
          {"GH_BODY_SUCCESS": json.dumps({"workflow_runs": [{
              "status": "completed", "conclusion": "success", "created_at": _fresh_at,
          }]})}, 0, False)
    _case("API error: no dispatch, non-zero exit, token stays out of the log",
          {"GH_FAIL_ALL": "1", "GH_BODY_SUCCESS": _SUCCESS_OLD}, 1, False)
    _case("malformed data: no dispatch and a non-zero exit",
          {"GH_BODY_SUCCESS": "{"}, 1, False)
    _case("a pull_request event does not dispatch",
          {"EVENT_NAME": "pull_request", "GH_BODY_SUCCESS": _SUCCESS_OLD}, 1, False)
    _case("shell text in the event name is not executed",
          {"EVENT_NAME": "schedule; echo PWNED", "GH_BODY_SUCCESS": _SUCCESS_OLD}, 1, False)
    _case("shell text in the repository name is not executed",
          {"GITHUB_REPOSITORY": "aliu2298/edge-machine; echo PWNED",
           "GH_BODY_SUCCESS": _SUCCESS_OLD}, 1, False)
    _case("workflow_dispatch dispatches a stale tracker on main, ignoring GITHUB_REF",
          {"EVENT_NAME": "workflow_dispatch", "GH_BODY_SUCCESS": _SUCCESS_OLD}, 0, True)
    for _status, _var in (
            ("queued", "GH_BODY_QUEUED"),
            ("pending", "GH_BODY_PENDING"),
            ("waiting", "GH_BODY_WAITING"),
            ("requested", "GH_BODY_REQUESTED"),
    ):
        _case(f"stale with a run {_status}: the step does not dispatch",
              {"GH_BODY_SUCCESS": _SUCCESS_OLD, _var: json.dumps({"workflow_runs": [{"status": _status}]})},
              0, False)


print(f"\n{'FAILED: ' + str(len(FAILS)) if FAILS else 'all tracker dispatch tests passed'}")
for _f in FAILS:
    print("   -", _f)
sys.exit(1 if FAILS else 0)
