# Telegram Local

A local Telegram **personal-account** connector for Codex and other stdio MCP
clients. Sign in with a QR code, read the chats your account can access, search
messages and send replies from your own account. Credentials and the MTProto
session stay on your machine.

[Русская инструкция](docs/README.ru.md) · [Security](SECURITY.md) ·
[Contributing](CONTRIBUTING.md)

## Requirements

- Linux or macOS, Python 3.11+ with `venv`/`pip`, and Git.
- Your own `api_id` and `api_hash` from <https://my.telegram.org/apps>.
- Telegram already signed in on your phone for QR login.
- The Codex CLI on PATH for automatic registration. Other clients can use the
  stdio command directly. No OpenAI API key is required by this connector.

Windows is not supported by the shell launchers and POSIX session lock in this
release. Use Linux/WSL with its own session. Network filtering may require an
explicit SOCKS/HTTP proxy.

## Quick start

Clone this repository and enter its root (the directory containing `setup.sh`):

```sh
./setup.sh
./run.sh login
./run.sh register-codex
```

`setup.sh` installs a project-local `.venv`, the pinned upstream MCP source and
locked runtime dependencies. To choose an interpreter:

```sh
PYTHON=python3.12 ./setup.sh
```

Enter your keys in the local terminal. Scan the QR with Telegram → Settings →
Devices → Link Desktop Device. Enter a 2FA password locally if Telegram asks.
Phone/code fallback: `./run.sh login --phone`.

Restart/reconnect Codex after registration. Then ask it to read a chosen chat or
send a message to a named recipient. To install the optional Codex skill:

```sh
./install-skill.sh
```

This creates a symlink to `skills/telegram-local`; keep your checkout in place.
The MCP provides live tools; the skill provides setup and usage instructions.

## Verify the connection

```sh
./run.sh doctor              # config, package provenance, dependency version
./run.sh doctor --network    # TCP reachability using the selected route
./run.sh status              # live authorization and one dialog read
./run.sh check-mcp           # MCP handshake, tool discovery, identity, Saved Messages read
```

These checks send **no messages**. `status` and `check-mcp` need exclusive access
to the session: stop the active MCP connection first. `doctor` can run while
MCP is active. Each subprocess exits after the check. A TCP success alone does
not prove authorization or MTProto availability.

## Optional proxy

Direct connections are the default; the connector does not guess your system
proxy. If direct Telegram connections time out:

```sh
./run.sh proxy --type socks5 --host 127.0.0.1 --port 10808
./run.sh doctor --network
./run.sh login
```

The proxy is used consistently by login, diagnostics and MCP. Keep the proxy
application running. `--type http` and `--type socks4` are also supported. For
authentication, add `--username NAME --password-prompt`; passwords are never
placed on the command line. To return to a direct connection:

```sh
./run.sh proxy --off
```

## Tool modes and data

```sh
./run.sh mode read-only
./run.sh mode messaging     # default: reading, send/reply, file transfers
./run.sh mode full          # all upstream tools, including destructive/admin actions
```

Reconnect MCP after changing the mode or proxy. These modes narrow the exposed
tool surface; the underlying Telegram session still has your account's access.
Secret Chats and other people's inaccessible private conversations are not
exposed. This connector does not schedule autonomous messages by itself.

Repository launchers use `./private/`, which Git ignores. Set
`TELEGRAM_LOCAL_HOME=/absolute/private/path` to use another location. The
installed `telegram-local` command defaults to
`${XDG_DATA_HOME:-~/.local/share}/telegram-local`. The CLI also accepts
`--data-dir PATH` **before** the subcommand.

Private files include `credentials.json`, `settings.json`, `account.session`,
the login verification marker and downloaded files. Data directories are 0700
and credential/session files are 0600. This is filesystem protection, not
encryption. The `files/` subdirectory is the allowed upload/download root.
No external transcription service is enabled.

## Other MCP clients and plugin packaging

After installation and login, configure one stdio server using an absolute path:

```json
{
  "mcpServers": {
    "telegram-personal": {
      "command": "/absolute/path/to/telegram-local/serve.sh",
      "args": []
    }
  }
}
```

The repository also includes a portable `plugin.json`, `mcp.json` and onboarding
skill, following the [OpenAI plugin packaging format](https://developers.openai.com/plugins/build/plugins).
The plugin launcher uses `${PLUGIN_ROOT}`; run setup and login in the installed
plugin directory before using its MCP server. When supplied by the host,
`PLUGIN_DATA` is used for private data. Do not enable both the plugin server
and a separate CLI registration for the same account. The CLI installation is
the tested path; marketplace installation/public submission is not claimed.

## Troubleshooting

- **Timeout before a QR appears:** run `doctor --network`, configure a working
  proxy if needed, then retry login. Increasing a timeout does not fix a blocked
  route. HTTP_PROXY/ALL_PROXY alone are insufficient for Telethon.
- **QR expired:** the login command refreshes it up to ten times; scan from
  Telegram's Devices page. A cloud password may still be required.
- **Session in use / database locked:** stop the other client using the session.
  Do not copy a live SQLite session or run it through multiple external IPs.
- **NOT_AUTHORIZED:** sign in again. A previous-login marker is only a local
  startup check; `status` verifies Telegram's current authorization.
- **Missing tools after installation:** restart/reconnect Codex, check
  `codex mcp get telegram-personal`, then run `check-mcp` while MCP is stopped.
- **Flood wait:** respect Telegram's wait period; do not loop login requests.

Revoke access in Telegram → Settings → Devices → Codex Telegram Local.
Remove registration with `codex mcp remove telegram-personal`. Private files are
not removed automatically, so that reinstalling does not silently lose access.

## Development and remote Git

```sh
.venv/bin/python -m unittest discover -s tests -v
./run.sh check-mcp           # optional live read-only integration check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for clean-install tests and the commands
to connect your own remote. The wrapper is MIT licensed; upstream MCP tools
and dependency attribution are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
