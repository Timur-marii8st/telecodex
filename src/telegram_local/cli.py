"""Setup, login, diagnostics and stdio entrypoint for a local account."""
import argparse
import asyncio
import getpass
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from . import __version__
from .config import (MODES, data_directory, prepare, proxy_options, read_json,
                     server_environment, session_lock, settings, validate_credentials,
                     write_private)


def credentials(directory, interactive=False, replace=False):
    path = directory / "credentials.json"
    existing = read_json(path)
    if existing is not None and not replace:
        path.chmod(0o600)
        return validate_credentials(existing)
    if not interactive:
        raise ValueError("No credentials. Run login first; get your own keys at https://my.telegram.org/apps.")
    print("Get your own api_id/api_hash at https://my.telegram.org/apps")
    value = validate_credentials({"api_id": input("api_id: ").strip(),
                                  "api_hash": getpass.getpass("api_hash (hidden): ").strip()})
    write_private(path, value)
    return value


async def qr_login(client, directory, refreshes=10):
    import qrcode
    from telethon import errors
    qr = await client.qr_login()
    for attempt in range(refreshes):
        image = qrcode.QRCode(border=2)
        image.add_data(qr.url)
        image.print_ascii(invert=True)
        image.make_image().save(directory / "login-qr.png")
        print("Telegram → Settings → Devices → Link Desktop Device", flush=True)
        print(f"QR image: {directory / 'login-qr.png'}", flush=True)
        try:
            await qr.wait()
            return
        except asyncio.TimeoutError:
            if attempt == refreshes - 1:
                raise ValueError("QR login expired. Run login again.") from None
            await qr.recreate()
        except errors.SessionPasswordNeededError:
            for password_attempt in range(3):
                try:
                    await client.sign_in(password=getpass.getpass("Telegram 2FA password (hidden): "))
                    return
                except errors.PasswordHashInvalidError:
                    print("Incorrect password.", file=sys.stderr)
            raise ValueError("Too many incorrect passwords. Run login again.")


async def account_action(args, directory, config, keys):
    from telethon import TelegramClient
    client = TelegramClient(str(directory / "account"), keys["api_id"], keys["api_hash"],
                            device_model="Codex Telegram Local", connection_retries=2,
                            timeout=12, proxy=proxy_options(config))
    try:
        await asyncio.wait_for(client.connect(), 40)
        if not await client.is_user_authorized():
            (directory / "authorized.json").unlink(missing_ok=True)
            if args.command == "status":
                raise ValueError("NOT_AUTHORIZED: run login.")
            if args.phone:
                await client.start(phone=lambda: input("Phone (+...): "),
                                   code_callback=lambda: getpass.getpass("Telegram code (hidden): "),
                                   password=lambda: getpass.getpass("2FA password (hidden): "))
            else:
                await qr_login(client, directory)
        me = await asyncio.wait_for(client.get_me(), 20)
        dialogs = await asyncio.wait_for(client.get_dialogs(limit=1), 20)
        write_private(directory / "authorized.json", {"user_id": me.id})
        print(json.dumps({"authorized": True, "user_id": me.id, "username": me.username,
                          "dialogs_readable": bool(dialogs)}, ensure_ascii=False))
    finally:
        await client.disconnect()
        (directory / "login-qr.png").unlink(missing_ok=True)
        for path in directory.glob("*.session*"):
            path.chmod(0o600)


async def network_check(config):
    host, port = "149.154.167.51", 443
    if config["proxy"]:
        from python_socks.async_.asyncio import Proxy
        proxy = config["proxy"]
        scheme = {"socks5": "socks5", "socks4": "socks4", "http": "http"}[proxy["type"]]
        from urllib.parse import quote
        auth = ""
        if proxy.get("username"):
            auth = quote(proxy["username"], safe="") + ":" + quote(proxy.get("password", ""), safe="") + "@"
        address = proxy["host"]
        if ":" in address:
            address = f"[{address}]"
        endpoint = Proxy.from_url(f"{scheme}://{auth}{address}:{proxy['port']}")
        sock = await endpoint.connect(dest_host=host, dest_port=port, timeout=12)
        sock.close()
    else:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 12)
        writer.close()
        await writer.wait_closed()


def doctor(args, directory, config):
    result = {"version": __version__, "python": sys.version.split()[0],
              "data_directory": str(directory), "mode": config["mode"],
              "credentials_present": (directory / "credentials.json").exists(),
              "session_present": (directory / "account.session").exists(),
              "previous_login_verified": (directory / "authorized.json").exists(),
              "route": "proxy" if config["proxy"] else "direct",
              "codex_available": shutil.which("codex") is not None}
    from telegram_mcp.install_guard import assert_safe_distribution
    assert_safe_distribution()
    result["upstream_version"] = metadata.version("telegram-mcp")
    if args.network:
        asyncio.run(network_check(config))
        result["telegram_tcp"] = "ok (TCP only; run status/check-mcp to verify MTProto)"
    print(json.dumps(result, indent=2))


def register_codex(args, directory):
    codex = shutil.which("codex")
    if not codex:
        raise ValueError("codex is not on PATH. Install the Codex CLI or configure its MCP settings manually.")
    command = [codex, "mcp", "add", args.name, "--env", f"TELEGRAM_LOCAL_HOME={directory}",
               "--", sys.executable, "-m", "telegram_local", "serve"]
    subprocess.run(command, check=True)


async def check_mcp(directory):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    parameters = StdioServerParameters(command=sys.executable,
        args=["-m", "telegram_local", "--data-dir", str(directory), "serve"],
        env={**os.environ, "TELEGRAM_LOCAL_HOME": str(directory)})
    def text(result):
        if result.isError:
            raise ValueError("MCP tool returned an error; inspect server diagnostics.")
        return "\n".join(item.text for item in result.content if getattr(item, "type", "") == "text")
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            await client.initialize()
            tools = await client.list_tools()
            me = json.loads(text(await client.call_tool("get_me", {})))
            if not isinstance(me.get("id"), int):
                raise ValueError("MCP get_me did not return an account ID.")
            history = text(await client.call_tool("get_messages", {"chat_id": me["id"], "page_size": 1}))
            if history.startswith("Error") or "[API_ERROR]" in history:
                raise ValueError("MCP could not read Saved Messages.")
            print(json.dumps({"mcp": "ok", "tools": len(tools.tools), "get_me": "ok",
                              "saved_messages_read": "ok", "messages_sent": 0}))


def parser():
    root = argparse.ArgumentParser(description="Local Telegram personal-account connector for Codex.")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--data-dir", help="Private data directory (or TELEGRAM_LOCAL_HOME).")
    commands = root.add_subparsers(dest="command", required=True)
    login = commands.add_parser("login", help="Interactive QR login, with optional phone fallback.")
    login.add_argument("--phone", action="store_true")
    login.add_argument("--replace-credentials", action="store_true")
    commands.add_parser("status", help="Verify authorization and read one dialog; sends nothing.")
    commands.add_parser("serve", help="Run the stdio MCP server.")
    diagnostics = commands.add_parser("doctor", help="Local diagnostics; optional network probe.")
    diagnostics.add_argument("--network", action="store_true")
    commands.add_parser("check-mcp", help="Verify the MCP protocol and read Saved Messages; sends nothing.")
    proxy = commands.add_parser("proxy", help="Configure an optional SOCKS/HTTP proxy.")
    proxy.add_argument("--type", choices=["socks5", "socks4", "http"], default="socks5")
    proxy.add_argument("--host", default="127.0.0.1")
    proxy.add_argument("--port", type=int, default=10808)
    proxy.add_argument("--username")
    proxy.add_argument("--password-prompt", action="store_true")
    proxy.add_argument("--off", action="store_true")
    mode = commands.add_parser("mode", help="Select exposed tools.")
    mode.add_argument("value", choices=list(MODES))
    register = commands.add_parser("register-codex", help="Register the MCP server using the installed interpreter.")
    register.add_argument("--name", default="telegram-personal")
    return root


def run(args):
    directory = data_directory(args.data_dir)
    prepare(directory)
    config = settings(directory)
    if args.command == "proxy":
        config["proxy"] = None if args.off else {"type": args.type, "host": args.host, "port": args.port}
        if not args.off and args.username:
            config["proxy"]["username"] = args.username
        if not args.off and args.password_prompt:
            config["proxy"]["password"] = getpass.getpass("Proxy password (hidden): ")
        # Validate before overwriting a working configuration.
        proxy = config["proxy"]
        if proxy and (not proxy["host"].strip() or not 1 <= proxy["port"] <= 65535):
            raise ValueError("Proxy requires a host and port between 1 and 65535.")
        write_private(directory / "settings.json", config)
        print("Proxy configuration saved. Run doctor --network to check connectivity.")
    elif args.command == "mode":
        config["mode"] = args.value
        write_private(directory / "settings.json", config)
        print(f"Mode: {args.value}. Restart the MCP connection to apply.")
    elif args.command == "doctor":
        doctor(args, directory, config)
    elif args.command == "register-codex":
        register_codex(args, directory)
    elif args.command == "check-mcp":
        asyncio.run(asyncio.wait_for(check_mcp(directory), timeout=60))
    else:
        with session_lock(directory):
            keys = credentials(directory, interactive=args.command == "login",
                               replace=getattr(args, "replace_credentials", False))
            if args.command in {"login", "status"}:
                asyncio.run(account_action(args, directory, config, keys))
            else:
                if not (directory / "authorized.json").exists():
                    raise ValueError("Run login or status to verify this session before serving MCP.")
                server_environment(directory, keys, config)
                os.chdir(directory)
                from telegram_mcp.runner import main as serve
                # The upstream runner owns its CLI. Do not pass this wrapper's
                # command/data-directory flags through to its argument parser.
                sys.argv = ["telegram-mcp"]
                serve()


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        run(args)
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        raise SystemExit(130) from None
    except (TimeoutError, ConnectionError, OSError) as exc:
        print(f"Connection/file error ({type(exc).__name__}). Run doctor --network; check your proxy and file permissions.", file=sys.stderr)
        raise SystemExit(1) from None
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
