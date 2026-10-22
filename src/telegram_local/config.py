"""Private configuration; no account-specific values belong in source control."""
import contextlib
import json
import os
from pathlib import Path
import re
import tempfile

MODES = {
    "read-only": "read-only",
    "messaging": "read-only+send_message,reply_to_message,send_file,download_media",
    "full": "all",
}


def data_directory(value=None):
    if value:
        return Path(value).expanduser().resolve()
    if os.environ.get("TELEGRAM_LOCAL_HOME"):
        return Path(os.environ["TELEGRAM_LOCAL_HOME"]).expanduser().resolve()
    root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return (root / "telegram-local").expanduser().resolve()


def prepare(directory):
    os.umask(0o077)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    files = directory / "files"
    if files.is_symlink():
        raise ValueError("The private files directory must not be a symlink.")
    files.mkdir(mode=0o700, exist_ok=True)
    files.chmod(0o700)


def read_json(path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ValueError(f"Cannot read {path.name}; check its JSON syntax and permissions.") from exc


def write_private(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_credentials(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid credentials; run login --replace-credentials.")
    api_id = str(value.get("api_id", ""))
    api_hash = value.get("api_hash", "")
    if not api_id.isdecimal() or int(api_id) <= 0 or not isinstance(api_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", api_hash):
        raise ValueError("api_id must be a positive integer; api_hash must be 32 hexadecimal characters.")
    return {"api_id": int(api_id), "api_hash": api_hash}


def settings(directory):
    result = read_json(directory / "settings.json", {})
    if not isinstance(result, dict):
        raise ValueError("settings.json must contain an object.")
    mode = result.get("mode", "messaging")
    if mode not in MODES:
        raise ValueError("Unknown tool mode; choose read-only, messaging, or full.")
    proxy = result.get("proxy")
    if proxy is not None:
        if not isinstance(proxy, dict) or proxy.get("type") not in {"socks5", "socks4", "http"}:
            raise ValueError("Proxy type must be socks5, socks4, or http.")
        port = proxy.get("port")
        if not isinstance(proxy.get("host"), str) or not proxy["host"].strip() or not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError("Proxy requires a host and port between 1 and 65535.")
    return {**result, "mode": mode, "proxy": proxy}


def proxy_options(config):
    proxy = config["proxy"]
    if proxy is None:
        return None
    return {"proxy_type": proxy["type"], "addr": proxy["host"],
            "port": proxy["port"], "rdns": True,
            **{key: proxy[key] for key in ("username", "password") if proxy.get(key)}}


def server_environment(directory, keys, config):
    # Isolate this one configured account from inherited upstream account pools,
    # proxy settings and session strings (which otherwise override file sessions).
    for key in list(os.environ):
        if key.startswith("TELEGRAM_") and not key.startswith("TELEGRAM_LOCAL_"):
            del os.environ[key]
    os.environ.update({
        "TELEGRAM_API_ID": str(keys["api_id"]),
        "TELEGRAM_API_HASH": keys["api_hash"],
        "TELEGRAM_SESSION_NAME": str(directory / "account"),
        "TELEGRAM_DEVICE_MODEL": "Codex Telegram Local",
        "TELEGRAM_TRANSCRIBE": "off",
        "TELEGRAM_EXPOSED_TOOLS": MODES[config["mode"]],
        "TELEGRAM_ALLOWED_ROOTS": str(directory / "files"),
        # Upstream otherwise prefers roots supplied by the MCP client, which
        # can include the workspace or home directory and override this boundary.
        "TELEGRAM_SERVER_ROOTS_ONLY": "1",
        "XDG_STATE_HOME": str(directory / "state"),
        "TELEGRAM_TRANSCRIPT_CACHE_DIR": str(directory / "transcripts"),
        "MCP_TRANSPORT": "stdio",
        "PYTHON_DOTENV_DISABLED": "1",
    })
    if config["proxy"]:
        for key, value in config["proxy"].items():
            os.environ["TELEGRAM_PROXY_" + key.upper()] = str(value)


@contextlib.contextmanager
def session_lock(directory):
    # POSIX desktop release: hold a single lock for login/status/serve so SQLite
    # sessions cannot be opened concurrently by these commands.
    import fcntl
    with (directory / "session.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Session is in use. Stop the other Telegram Local process first; doctor can run while MCP is active.") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
