import asyncio
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
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
        self.assertTrue(checker.violations("example.txt", b"example-secret", [b"example-secret"]))
        self.assertEqual(checker.violations("README.md", b"No credentials here"), [])


if __name__ == "__main__":
    unittest.main()
