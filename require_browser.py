"""Shared skip for browser checks that import playwright.sync_api.

CI sets REQUIRE_BROWSER=1, and a missing Playwright then fails the test.
A local run without the flag still warns and continues. The warning text
starts with "Playwright is not installed; browser checks" so the pull-request
workflow can fail a test that has not adopted this helper yet.
"""
import os
import sys


def require_browser(where):
    """Return sync_playwright, or None when the caller should skip.

    `where` is the test file name, so the message names which checks did not run.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        message = f"Playwright is not installed; browser checks in {where} were not run"
        if os.environ.get("REQUIRE_BROWSER") == "1":
            print(f"::error::{message}")
            sys.exit(1)
        print(f"::warning::{message}")
        print("  skipped: playwright is not installed; browser check not run")
        return None
    return sync_playwright
