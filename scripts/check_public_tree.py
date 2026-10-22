#!/usr/bin/env python3
"""Reject private account artifacts and machine paths without printing secrets."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DENIED_PARTS = {"private", ".venv", "__pycache__", ".git"}
DENIED_NAMES = {"network.json", "REPORT.txt", "credentials.json", "authorized.json", "login-qr.png", "installed-versions.txt"}


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def violations(name, data, secrets=()):
    path = Path(name)
    found = []
    if (set(path.parts) & DENIED_PARTS or path.name in DENIED_NAMES
            or ".session" in path.name or path.name == ".env"
            or (path.name.startswith(".env.") and path.name != ".env.example")
            or path.suffix == ".log"):
        found.append("private/generated artifact")
    if re.search(rb"/(?:home|Users)/[A-Za-z0-9_.-]+/", data):
        found.append("machine-specific home path")
    if any(secret and secret in data for secret in secrets):
        found.append("local account credential/identity value")
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="Read file contents from the Git index.")
    args = parser.parse_args()
    secrets = []
    for file, keys in [("credentials.json", ["api_hash"]), ("authorized.json", ["user_id"])]:
        path = ROOT / "private" / file
        if path.exists():
            value = json.loads(path.read_text())
            secrets.extend(str(value[key]).encode() for key in keys if value.get(key))
    names = git("ls-files", "-z").decode().split("\0")
    failures = []
    for name in filter(None, names):
        if args.staged:
            data = git("show", ":" + name)
        else:
            path = ROOT / name
            if not path.is_file():
                failures.append((name, ["missing tracked file"]))
                continue
            data = path.read_bytes()
        reasons = violations(name, data, secrets)
        if reasons:
            failures.append((name, reasons))
    if failures:
        for name, reasons in failures:
            print(f"BLOCKED {name}: {', '.join(reasons)}", file=sys.stderr)
        return 1
    print(f"Public-tree check passed ({sum(bool(name) for name in names)} tracked files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
