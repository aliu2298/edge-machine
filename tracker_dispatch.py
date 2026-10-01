#!/usr/bin/env python3
"""Whether the hourly watchdog should start sandbox-tracker.yml.

GitHub's scheduler drops slots of that workflow (cron 11 2-23/3) and starts
others late. data/production_leads.json is a live dependency: an external bot
drops it once updated_at is more than 8h old, so a missed slot cannot wait
for the next cron. backup-refresh.yml's watch job (cron 53 * * * *) calls
decide() and, when it says so, dispatches one run on main.

A failed or unreadable run history is not "no runs" and it is not stale.
decide() and fetch_history() raise HistoryError in that case. The workflow
exits non-zero and does not dispatch.
"""
import json
import re
from datetime import datetime, timezone

# One missed 3h slot, plus a little slack so a run that started a few
# minutes late does not get a second copy. Strictly greater than this.
DISPATCH_AFTER_HOURS = 3.5
# cancel-in-progress is false on the tracker's refresh-boards group, but a
# newer pending run still replaces one that is already queued. Anything not
# finished blocks a dispatch.
OPEN_STATUSES = ("queued", "in_progress", "pending", "waiting", "requested")
_KNOWN_STATUSES = frozenset(OPEN_STATUSES) | {"completed"}
_ALLOWED_EVENTS = frozenset({"schedule", "workflow_dispatch"})
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_MALFORMED = "GitHub API returned malformed run history"
_API_FAILED = "GitHub API failed reading sandbox-tracker.yml run history"
_WORKFLOW = "sandbox-tracker.yml"
_REF = "main"


class HistoryError(Exception):
    """Run history could not be read. Do not dispatch."""


def decide(last_success, open_statuses, now, event_name):
    """(dispatch, message).

    last_success is the created_at of the newest successful sandbox-tracker
    run, or None when that query's workflow_runs list is empty. open_statuses
    are status strings. now is an aware clock. event_name must be schedule
    or workflow_dispatch.

    dispatch is True only when the last success is more than
    DISPATCH_AFTER_HOURS old (a genuine empty history counts as overdue) and
    no status is unfinished. The message is one line: on a dispatch it names
    the age and why.

    Raises HistoryError when an input is unusable. That is not a dispatch.
    The exception text does not repeat the bad value.
    """
    if event_name not in _ALLOWED_EVENTS:
        raise HistoryError("refusing to dispatch sandbox-tracker.yml for this event")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise HistoryError(_MALFORMED)
    now = now.astimezone(timezone.utc)
    if last_success is not None:
        if not isinstance(last_success, datetime) or last_success.tzinfo is None:
            raise HistoryError(_MALFORMED)
        last_success = last_success.astimezone(timezone.utc)
    if isinstance(open_statuses, (str, bytes)) or not isinstance(open_statuses, (list, tuple)):
        raise HistoryError(_MALFORMED)
    statuses = []
    for status in open_statuses:
        if not isinstance(status, str) or status not in _KNOWN_STATUSES:
            raise HistoryError(_MALFORMED)
        statuses.append(status)

    blocking = [status for status in statuses if status in OPEN_STATUSES]
    if last_success is None:
        age_text = None
        overdue = True
    else:
        hours = (now - last_success).total_seconds() / 3600.0
        age_text = f"{hours:.1f}h"
        overdue = hours > DISPATCH_AFTER_HOURS
    if blocking:
        detail = "no successful run on record" if age_text is None else f"last success is {age_text} old"
        return False, (
            f"not dispatching sandbox-tracker.yml: {detail}, but a run is {blocking[0]}"
        )
    if not overdue:
        return False, f"not dispatching sandbox-tracker.yml: last success is {age_text} old"
    if age_text is None:
        return True, (
            "dispatching sandbox-tracker.yml --ref main: no successful run on record, "
            "and no run is unfinished"
        )
    return True, (
        f"dispatching sandbox-tracker.yml --ref main: last success is {age_text} old, "
        f"past {DISPATCH_AFTER_HOURS:g}h, and no run is unfinished"
    )


def _runs_path(repo, status):
    return (
        f"/repos/{repo}/actions/workflows/{_WORKFLOW}/runs"
        f"?status={status}&per_page=1"
    )


def _call(gh, args):
    try:
        result = gh(list(args))
    except Exception:
        raise HistoryError(_API_FAILED) from None
    if not isinstance(result, tuple) or not result or isinstance(result[0], bool) or not isinstance(result[0], int):
        raise HistoryError(_API_FAILED)
    out = result[1] if len(result) > 1 else ""
    if not isinstance(out, str):
        out = ""
    return result[0], out


def _real_gh(args):
    import subprocess
    proc = subprocess.run(["gh", *list(args)], capture_output=True, text=True)
    return proc.returncode, proc.stdout


def _payload(out):
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        raise HistoryError(_MALFORMED) from None
    if not isinstance(payload, dict) or "workflow_runs" not in payload:
        raise HistoryError(_MALFORMED)
    runs = payload["workflow_runs"]
    if not isinstance(runs, list):
        raise HistoryError(_MALFORMED)
    return runs


def _created_at(value):
    if not isinstance(value, str):
        raise HistoryError(_MALFORMED)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise HistoryError(_MALFORMED) from None
    if parsed.tzinfo is None:
        raise HistoryError(_MALFORMED)
    return parsed.astimezone(timezone.utc)


def _parse_success(runs):
    if not runs:
        return None
    run = runs[0]
    if (not isinstance(run, dict) or run.get("conclusion") != "success"
            or run.get("status") != "completed"):
        raise HistoryError(_MALFORMED)
    return _created_at(run.get("created_at"))


def _parse_open(runs, expected):
    found = []
    for run in runs:
        if not isinstance(run, dict) or run.get("status") != expected:
            raise HistoryError(_MALFORMED)
        found.append(expected)
    return found


def fetch_history(repo, gh=None):
    """(last_success, open_statuses) from the sandbox-tracker.yml runs API.

    last_success is an aware datetime, or None when the success query is a
    real empty list. open_statuses lists unfinished runs. Raises HistoryError
    when repo is not owner/name, gh fails, or a body is not a run list.
    stderr from gh is discarded and is not part of the error.
    """
    if gh is None:
        gh = _real_gh
    if not isinstance(repo, str) or _REPO.fullmatch(repo) is None:
        raise HistoryError("GITHUB_REPOSITORY is missing or not owner/name")
    rc, out = _call(gh, ["api", _runs_path(repo, "success")])
    if rc != 0:
        raise HistoryError(_API_FAILED)
    last = _parse_success(_payload(out))
    statuses = []
    for status in OPEN_STATUSES:
        rc, out = _call(gh, ["api", _runs_path(repo, status)])
        if rc != 0:
            raise HistoryError(_API_FAILED)
        statuses.extend(_parse_open(_payload(out), status))
    return last, statuses


def start_tracker(gh=None):
    """Dispatch sandbox-tracker.yml on main. Raises HistoryError if gh fails.

    The workflow file and the ref are literals. gh's output is discarded.
    """
    if gh is None:
        gh = _real_gh
    rc, _out = _call(gh, ["workflow", "run", _WORKFLOW, "--ref", _REF])
    if rc != 0:
        raise HistoryError("could not dispatch sandbox-tracker.yml")
