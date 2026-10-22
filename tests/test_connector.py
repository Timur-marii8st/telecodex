import asyncio
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram_local import cli
from telegram_local.config import (data_directory, prepare, proxy_options,
    server_environment, session_lock, settings, validate_credentials, write_private)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "data"
        prepare(self.directory)

    def test_fresh_install_is_direct_and_contains_no_credentials(self):
        config = settings(self.directory)
        self.assertEqual(config["mode"], "messaging")
        self.assertIsNone(proxy_options(config))
        with self.assertRaisesRegex(ValueError, "No credentials"):
            cli.credentials(self.directory)

    def test_atomic_private_file_and_directory_permissions(self):
        path = self.directory / "settings.json"
        write_private(path, {"mode": "read-only"})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(settings(self.directory)["mode"], "read-only")
        self.assertEqual(list(self.directory.glob(".tmp-*")), [])

    def test_file_root_symlink_is_rejected(self):
        files = self.directory / "files"
        files.rmdir()
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        files.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "must not be a symlink"):
            prepare(self.directory)

    def test_invalid_proxy_does_not_replace_working_config(self):
        original = {"proxy": {"type": "socks5", "host": "localhost", "port": 10808}}
        path = self.directory / "settings.json"
        write_private(path, original)
        args = cli.parser().parse_args(["--data-dir", str(self.directory), "proxy", "--port", "70000"])
        with self.assertRaises(ValueError):
            cli.run(args)
        self.assertEqual(json.loads(path.read_text()), original)

    def test_inherited_sessions_cannot_select_another_account(self):
        with patch.dict(os.environ, {"TELEGRAM_SESSION_STRING": "wrong", "TELEGRAM_SESSION_STRING_WORK": "wrong", "TELEGRAM_PROXY_PASSWORD": "wrong", "TELEGRAM_LOCAL_HOME": str(self.directory)}):
            config = {"mode": "read-only", "proxy": None}
            server_environment(self.directory, {"api_id": 123, "api_hash": "a" * 32}, config)
            self.assertNotIn("TELEGRAM_SESSION_STRING", os.environ)
            self.assertNotIn("TELEGRAM_SESSION_STRING_WORK", os.environ)
            self.assertNotIn("TELEGRAM_PROXY_PASSWORD", os.environ)
            self.assertEqual(os.environ["TELEGRAM_SESSION_NAME"], str(self.directory / "account"))
            self.assertEqual(os.environ["MCP_TRANSPORT"], "stdio")
            self.assertEqual(os.environ["PYTHON_DOTENV_DISABLED"], "1")
            self.assertEqual(os.environ["TELEGRAM_SERVER_ROOTS_ONLY"], "1")

    def test_client_roots_cannot_expand_read_or_write_access(self):
        script = '''
import asyncio, os, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from telegram_local.config import prepare, server_environment
async def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        private = root / "private"
        prepare(private)
        outside = root / "outside"
        outside.mkdir()
        sample = outside / "sample.txt"
        sample.write_text("synthetic sample")
        server_environment(private, {"api_id": 12345, "api_hash": "a" * 32},
                           {"mode": "messaging", "proxy": None})
        from telegram_mcp import runtime
        runtime._configure_allowed_roots_from_cli([])
        list_roots = AsyncMock(return_value=SimpleNamespace(roots=[SimpleNamespace(uri=outside.as_uri())]))
        ctx = SimpleNamespace(session=SimpleNamespace(list_roots=list_roots))
        path, error = await runtime._resolve_readable_file_path(raw_path=str(sample), ctx=ctx, tool_name="send_file")
        assert path is None and "outside allowed roots" in error.lower()
        path, error = await runtime._resolve_writable_file_path(raw_path=str(outside / "output.txt"), default_filename="output.txt", ctx=ctx, tool_name="download_media")
        assert path is None and "outside allowed roots" in error.lower()
        inside = private / "files" / "sample.txt"
        inside.write_text("allowed sample")
        path, error = await runtime._resolve_readable_file_path(raw_path=str(inside), ctx=ctx, tool_name="send_file")
        assert path == inside and error is None
        list_roots.assert_not_awaited()
asyncio.run(main())
'''
        result = subprocess.run([sys.executable, "-c", script], cwd=self.directory,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_proxy_route_is_identical_for_login_and_server(self):
        config = {"mode": "messaging", "proxy": {"type": "socks5", "host": "127.0.0.1", "port": 12345}}
        with patch.dict(os.environ):
            server_environment(self.directory, {"api_id": 123, "api_hash": "a" * 32}, config)
            proxy = proxy_options(config)
            self.assertEqual(proxy["addr"], os.environ["TELEGRAM_PROXY_HOST"])
            self.assertEqual(proxy["port"], int(os.environ["TELEGRAM_PROXY_PORT"]))

    def test_second_session_user_is_rejected_then_lock_is_released(self):
        with session_lock(self.directory):
            with self.assertRaisesRegex(ValueError, "Session is in use"):
                with session_lock(self.directory):
                    self.fail("Second process must not enter")
        with session_lock(self.directory):
            pass

    def test_malformed_credentials_are_rejected_before_connecting(self):
        for value in [{"api_id": 0, "api_hash": "a" * 32}, {"api_id": 123, "api_hash": "bad"}, []]:
            with self.assertRaises(ValueError):
                validate_credentials(value)

    def test_explicit_directory_overrides_environment(self):
        with patch.dict(os.environ, {"TELEGRAM_LOCAL_HOME": "/unused"}):
            self.assertEqual(data_directory(self.directory), self.directory)


class LoginTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_qr_refreshes_and_does_not_send(self):
        qr = SimpleNamespace(url="tg://login?token=dummy", wait=AsyncMock(side_effect=[asyncio.TimeoutError(), object()]), recreate=AsyncMock())
        client = SimpleNamespace(qr_login=AsyncMock(return_value=qr))
        image = MagicMock()
        with tempfile.TemporaryDirectory() as tmp, patch("qrcode.QRCode", return_value=image), patch("sys.stdout", new=io.StringIO()):
            await cli.qr_login(client, Path(tmp), refreshes=2)
        qr.recreate.assert_awaited_once()
        self.assertEqual(qr.wait.await_count, 2)

    async def test_unauthorized_status_cleans_marker_and_never_starts_login(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            marker = directory / "authorized.json"
            marker.write_text("{}")
            client = MagicMock()
            client.connect = AsyncMock()
            client.is_user_authorized = AsyncMock(return_value=False)
            client.disconnect = AsyncMock()
            client.start = AsyncMock()
            with patch("telethon.TelegramClient", return_value=client):
                with self.assertRaisesRegex(ValueError, "NOT_AUTHORIZED"):
                    await cli.account_action(SimpleNamespace(command="status"), directory,
                        {"proxy": None}, {"api_id": 123, "api_hash": "a" * 32})
            self.assertFalse(marker.exists())
            client.start.assert_not_awaited()
            client.disconnect.assert_awaited_once()


class PublicTreeTests(unittest.TestCase):
    def test_private_paths_and_known_values_are_blocked_without_disclosure(self):
        script = Path(__file__).resolve().parents[1] / "scripts/check_public_tree.py"
        spec = importlib.util.spec_from_file_location("public_tree", script)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        self.assertTrue(checker.violations("private/account.session", b"anything"))
        self.assertTrue(checker.violations(".env.production", b"anything"))
        self.assertEqual(checker.violations(".env.example", b"placeholder"), [])
        self.assertTrue(checker.violations("example.txt", b"example-secret", [b"example-secret"]))
        self.assertEqual(checker.violations("README.md", b"No credentials here"), [])


if __name__ == "__main__":
    unittest.main()
