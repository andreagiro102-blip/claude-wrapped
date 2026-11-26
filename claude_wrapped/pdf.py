"""Save the HTML report as a PDF with a Chromium browser already on the machine (Chrome, Edge,
Chromium, Brave), run headless. Nothing is downloaded and nothing leaves the machine."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ENV = "CLAUDE_WRAPPED_BROWSER"      # full path to a browser, to override the search


def _candidates():
    if os.environ.get(ENV):
        yield os.environ[ENV]
    if sys.platform == "win32":
        roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        for root in filter(None, roots):
            for rel in (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe",
                        r"Chromium\Application\chrome.exe",
                        r"BraveSoftware\Brave-Browser\Application\brave.exe"):
                yield os.path.join(root, rel)
    elif sys.platform == "darwin":
        for app in ("Google Chrome", "Microsoft Edge", "Chromium", "Brave Browser"):
            yield f"/Applications/{app}.app/Contents/MacOS/{app}"
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                 "microsoft-edge", "microsoft-edge-stable", "brave-browser", "chrome", "msedge"):
        found = shutil.which(name)
        if found:
            yield found


def find_browser() -> str | None:
    return next((c for c in _candidates() if os.path.isfile(c)), None)


def html_to_pdf(html_path: str, pdf_path: str, browser: str | None = None) -> str | None:
    """Print `html_path` to `pdf_path`. Returns None on success, otherwise the reason it failed."""
    browser = browser or find_browser()
    if not browser:
        return ("no Chrome, Edge or Chromium found (set %s to its path), "
                "or open the report and click 'Save as PDF'" % ENV)
    pdf_path = os.path.abspath(pdf_path)
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    with tempfile.TemporaryDirectory(prefix="claude-wrapped-") as profile:   # never touch the user's profile
        cmd = [browser, "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               f"--user-data-dir={profile}", "--no-pdf-header-footer", "--print-to-pdf-no-header",
               f"--print-to-pdf={pdf_path}", Path(html_path).resolve().as_uri()]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as e:
            return f"{os.path.basename(browser)} failed: {e}"
    if not os.path.isfile(pdf_path) or os.path.getsize(pdf_path) == 0:
        return f"{os.path.basename(browser)} did not write the PDF"
    return None
