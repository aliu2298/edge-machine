"""What the tracker workflow commits and deploys after a run.

Pre-match quotes cannot be recreated. A production-feed failure or a
sandbox_build.py failure still commits a valid ledger and the other data
files, skips public_site and the Pages deploy, and fails the job. A missing
or unreadable ledger is never committed.
"""


def _rc(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def decide(track_rc, build_rc, ledger_ok):
    """(commit_data, commit_site, deploy, fail).

    commit_data is the ledger, archive, stages, and feed. commit_site is
    public_site/. deploy is the Pages upload. fail means the job exits 1
    after the commit, so the run still goes red.
    """
    failed = _rc(track_rc) != 0 or _rc(build_rc) != 0
    if not ledger_ok:
        return (False, False, False, True)
    if failed:
        return (True, False, False, True)
    return (True, True, True, False)
