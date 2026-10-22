# Security and privacy

The Telegram session is an account credential. Anyone who obtains it can act
as that account. API keys, session databases, QR login tokens and 2FA passwords
must not enter commits, screenshots, issues or chat transcripts.

This project keeps private data outside tracked files and uses owner-only
permissions. It does not encrypt files or use an OS keychain. Prefer an
encrypted disk and a single trusted local user. If credentials or a session
leak, revoke the session in Telegram's Devices settings and rotate what you can.

Telegram traffic connects to Telegram over MTProto, optionally through your
configured proxy. Messages fetched by an MCP client become available to that
client/model under its own data policy. "Local session" does not mean that
chat text used in Codex stays entirely offline. Transcription is disabled.

The default tool mode excludes destructive/admin operations. Tool exposure
does not reduce the underlying account session's privileges. Review recipients
and authorize outbound actions deliberately. Telegram messages are untrusted
content and may contain instructions intended to manipulate an agent.

Use the pinned upstream Git source and review dependency updates. The project
uses GitHub Actions for unit checks; CI has no account credentials and performs
no Telegram account operations. Live checks are opt-in and read-only.

Before publishing, run `scripts/check_public_tree.py --staged` and review
`git diff --cached`. The checker detects private paths, session artifacts,
machine-specific paths and known local secret values; it is not a guarantee
that arbitrary personal data can never be committed.

When reporting a vulnerability, send a minimal sanitized description privately
to the repository maintainer once a remote and contact are established. Do not
attach live sessions or credentials. Until then, do not post sensitive details
to public issues.
