# Security review — 22 October 2026

Reviewed published `main` commit `69a92135b0f94e851e86ac6b42995709af67ebe4`,
the separate original local commit, wrapper code, launchers, CI, dependency
metadata and the upstream file-path policy. Remediation is version **0.1.1**.
This is a targeted review with automated checks, not a guarantee of absence
of vulnerabilities or a full audit of every upstream Telegram tool.

## Findings

### High: the advertised file boundary could be overridden by client roots

`server_environment()` configured `TELEGRAM_ALLOWED_ROOTS`, but upstream's
policy prefers roots returned by the MCP client unless server-only roots are
explicitly enabled. A client advertising the workspace/home as a root could
therefore make `send_file` accept a file outside `private/files`. This could
expose account files or other local data if an agent was induced to send them.
An unauthenticated remote attacker cannot directly call this stdio server;
exploitation requires access through the MCP client/tool workflow.

Confirmed before remediation with a synthetic file outside the configured
directory: the resolver returned that file with no error. No real private
file was uploaded and no Telegram message was sent during this audit.

Fixed in `src/telegram_local/config.py` by forcing
`TELEGRAM_SERVER_ROOTS_ONLY=1`. A regression test now supplies broader client
roots, verifies that reads and writes outside the server root are rejected,
confirms that a file inside the root remains readable, and checks that the
client roots callback is not used. Startup also rejects a symlink at the
private file root and enforces 0700 permissions on that directory.

### Medium: the bootstrap environment retained vulnerable pip 25.0.1

The initial virtual environment inherited pip 25.0.1. Its runtime was not part
of `requirements.lock`. A separate audit found six distinct advisory IDs
(the service returned duplicate records for some IDs):

- PYSEC-2026-1795
- PYSEC-2026-1796
- PYSEC-2026-196
- PYSEC-2026-2875
- PYSEC-2026-2876
- PYSEC-2026-3721

These concern installing/extracting crafted packages or malicious index data,
not reading ordinary Telegram messages. The environment was updated to
pip 26.2.2; `setup.sh` now upgrades to that pinned version before installing
project dependencies. Re-auditing that version found no known advisories.
Maintainers still need to review future installer updates.

### Low: mutable CI action tags and retained checkout credentials

Actions used floating `@v4`/`@v5` tags. They are now pinned to commit SHAs
resolved from the official action repositories during this review, and checkout
uses `persist-credentials: false`. The workflow already had read-only repository
permissions, used GitHub-hosted runners, and referenced no account secrets.
SHA pinning follows [GitHub's secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use).

### Low: publication checks missed named environment files

`.gitignore` excluded `.env.*`, but the scanner would not reject an explicitly
force-added `.env.production`. It now rejects such filenames while allowing
the documented `.env.example` template. A regression test covers both cases.

## Evidence

- All 3 reachable local commits checked; 53 file revisions / 26 distinct blobs.
  No known local API hash or account ID, private/session artifact paths,
  private keys, recognized GitHub token formats or Telegram bot token formats
  were found. Git author name/email are intentionally public metadata.
- Local private directory permissions were 0700; credentials, configuration,
  authorization marker, session and lock files were 0600.
- pip-audit 2.10.1 checked all **46 pinned PyPI runtime packages** with no known
  advisories. pip 26.2.2 was checked separately, also with no known advisories.
  Checks used the already pinned package list with dependency resolution
  disabled; they did not install or execute dependencies to resolve them.
- The Git-pinned upstream `telegram-mcp` was deliberately excluded from the
  PyPI advisory query: that PyPI name belongs to a different project. Its
  selected source policy was reviewed directly. Build-isolation dependencies
  are not covered by the 46-package result.
- Bandit 1.9.4 found no medium/high results in wrapper/publication code.
  Five low results concern subprocess imports/calls: reviewed calls use argv
  lists without a shell. Git/Codex executables still depend on a trusted PATH.
- A Bandit high result in upstream's SHA-1 use was reviewed: it derives a
  session-pool lock filename, not Telegram authentication/signature data. The
  wrapper clears inherited session pools and uses a file session; that branch
  is not active in this configuration. No cryptographic bypass was established.
- **13 tests pass**, including file-boundary and symlink regression tests.
  Dependency consistency and whitespace checks pass.

## Remaining limits and operational requirements

Credentials/session files are not encrypted. Filesystem permissions do not
protect against malware running as the same local user. Telegram session access
can act as the account; revoke it through Telegram Devices if compromised.
Reading a message into Codex shares that content with the configured client/model
under its data policy. Prompt injection in received messages remains a reason
to require explicit recipient/action authorization. The tool mode narrows the
surface but does not reduce the Telegram session's underlying privileges.

Dependencies are version/commit pinned, but PyPI artifacts are not hash-locked,
and isolated build tools are not fully pinned. This review did not verify GitHub
account security, branch protection, Actions organization policies, every
dependency's source, or the user's host/proxy integrity. No release to a public
plugin marketplace was tested.

Restart the MCP connection to activate the file policy fix. Install version
0.1.1 rather than the earlier 0.1.0 source archive. Local remediations are not
automatically published by this review; compare the remote branch before
announcing the fixed version publicly.
