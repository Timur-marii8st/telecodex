# Development

Run `./setup.sh`, then `.venv/bin/python -m unittest discover -s tests -v`.
Unit tests use temporary directories and mock clients; no account is needed.
The optional `./run.sh check-mcp` uses your real account but only reads identity
and Saved Messages. It sends nothing. Stop the active MCP server before running it.

Keep account files out of tests and logs. Use the project `private/` directory
or an external `TELEGRAM_LOCAL_HOME`. Dependency changes must update both
`pyproject.toml` and `requirements.lock`, retain the pinned upstream Git revision,
and pass `pip check`.

For a clean-install check, clone the committed repository into a temporary
directory and run `setup.sh` there. Run unit tests and `doctor` with its empty
private directory; do not copy a real session into the clone. Run packaging with
`.venv/bin/python -m pip wheel --no-deps --wheel-dir dist .` and inspect the wheel
for private files. Test the original account read-only after runtime changes.

## Connect a remote repository

Create an empty repository on your Git hosting service, then from this project's
root use its actual URL:

```sh
git remote add origin YOUR_REMOTE_URL
git push -u origin main
```

If `origin` already exists, inspect `git remote -v` before changing it.
Do not include tokens/passwords in the URL. SSH or your Git credential manager
can handle authentication. No remote is created or pushed by the setup script.

Before the first push:

```sh
git status --short
python3 scripts/check_public_tree.py --staged
git diff --cached --stat
```

After committing, use `python3 scripts/check_public_tree.py` to scan tracked
files. The project starts on branch `main`. Its Git directory is independent
of any parent checkout. Add a real repository/homepage URL to plugin metadata
when the remote exists; no placeholder hosting identity is shipped.
