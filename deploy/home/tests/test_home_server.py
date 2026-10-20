"""Guard the private ingress and secret-file boundaries without touching Docker/Tailscale."""

import os
import tempfile
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SPEC = spec_from_file_location(
    "home_server", Path(__file__).resolve().parents[3] / "scripts/home_server.py"
)
assert SPEC and SPEC.loader
HOME = module_from_spec(SPEC)
SPEC.loader.exec_module(HOME)


class HomeServerTests(unittest.TestCase):
    def test_old_config_gets_only_the_default_public_download_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / ".local/home-server/home.env"
            with patch.object(HOME, "ROOT", root):
                target = HOME.prepare_downloads(env_file, {})
            self.assertEqual(target, root / ".local/home-server/downloads")
            self.assertTrue(target.is_dir())
            self.assertEqual(list(target.iterdir()), [])
            self.assertFalse(env_file.exists())
            if os.name != "nt":
                self.assertEqual(HOME.stat.S_IMODE(target.stat().st_mode), 0o755)

    def test_public_download_preflight_rejects_secrets_and_missing_custom_directories(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / ".local/home-server/home.env"
            with patch.object(HOME, "ROOT", root):
                custom = root / "do-not-create/private"
                with self.assertRaises(ValueError):
                    HOME.prepare_downloads(
                        env_file, {"ALLSAFE_HOME_DOWNLOAD_DIR": str(custom)}
                    )
                self.assertFalse(custom.exists())
                target = HOME.prepare_downloads(env_file, {})
                (target / ".env").write_text("test-only-secret", encoding="utf-8")
                with self.assertRaises(ValueError):
                    HOME.prepare_downloads(env_file, {})
                (target / ".env").unlink()
                (target / HOME.APK_NAME).write_bytes(b"test-apk-placeholder")
                self.assertEqual(HOME.prepare_downloads(env_file, {}), target)

    def test_failed_serve_enable_can_be_retried_without_overwriting_snapshots(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "home.env"
            args = SimpleNamespace(env_file=path)
            config = {"ALLSAFE_HOME_HTTP_PORT": "18180"}
            failed = HOME.subprocess.CalledProcessError(1, ["tailscale", "serve"])
            with (
                patch("builtins.print"),
                patch.object(HOME, "read_config", return_value=config),
                patch.object(
                    HOME, "inspect_serve", return_value=({}, "host.tail.ts.net", 443)
                ),
                patch.object(
                    HOME,
                    "run",
                    side_effect=[failed, HOME.subprocess.CompletedProcess([], 0)],
                ) as mocked,
            ):
                with self.assertRaises(HOME.subprocess.CalledProcessError):
                    HOME.enable_serve(args)
                first = list(Path(directory).glob("tailscale-serve-before-*.json"))
                self.assertEqual(len(first), 1)
                original = first[0].read_bytes()
                HOME.enable_serve(args)
            self.assertEqual(
                len(list(Path(directory).glob("tailscale-serve-before-*.json"))), 2
            )
            self.assertEqual(first[0].read_bytes(), original)
            self.assertEqual(mocked.call_count, 2)

    def test_start_recreates_api_namespace_analyzer_and_proxy_together_after_preflight(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web = root / "build/home-client/web"
            web.mkdir(parents=True)
            (web / "index.html").write_text("test", encoding="utf-8")
            models = root / "models"
            models.mkdir()
            for name in HOME.MODEL_NAMES:
                (models / name).write_text("test-only-placeholder", encoding="utf-8")
            config = {
                "ALLSAFE_HOME_MODEL_DIR": str(models),
                "ALLSAFE_HOME_HTTP_PORT": "18180",
            }
            args = SimpleNamespace(env_file=root / "home.env")
            with (
                patch.object(HOME, "ROOT", root),
                patch.object(HOME, "read_config", return_value=config),
                patch.object(
                    HOME,
                    "compose",
                    return_value=HOME.subprocess.CompletedProcess(
                        [], 0, "existing-edge"
                    ),
                ) as mocked,
            ):
                HOME.start(args)
            operations = [call.args[1:] for call in mocked.call_args_list]
            self.assertEqual(operations[1], ("config", "--quiet"))
            self.assertEqual(operations[2], ("stop", "edge", "phishcatch", "api"))
            self.assertEqual(operations[3][0], "up")
            self.assertIn("--force-recreate", operations[3])
            self.assertIn("--wait", operations[3])
            # No selected service subset: migrations and all three runtimes stay in one project.
            self.assertEqual(operations[3][-2:], ("--wait-timeout", "240"))

    def test_serve_preflight_rejects_wrong_node_and_public_funnel(self) -> None:
        config = {"ALLSAFE_HOME_ORIGIN": "https://host.tail.ts.net"}
        for state, serve in (
            ({"BackendState": "Stopped", "Self": {"DNSName": "host.tail.ts.net."}}, {}),
            (
                {"BackendState": "Running", "Self": {"DNSName": "other.tail.ts.net."}},
                {},
            ),
            (
                {"BackendState": "Running", "Self": {"DNSName": "host.tail.ts.net."}},
                {"AllowFunnel": {"host.tail.ts.net:443": True}},
            ),
        ):
            responses = [
                HOME.subprocess.CompletedProcess([], 0, HOME.json.dumps(state)),
                HOME.subprocess.CompletedProcess([], 0, HOME.json.dumps(serve)),
            ]
            with (
                self.subTest(state=state, serve=serve),
                patch.object(HOME, "run", side_effect=responses) as mocked,
            ):
                with self.assertRaises(ValueError):
                    HOME.inspect_serve(config)
                self.assertTrue(
                    all("--bg" not in call.args[0] for call in mocked.call_args_list)
                )

    def test_only_verified_https_tailnet_origins_are_accepted(self) -> None:
        for value in (
            "http://host.tail123.ts.net",
            "https://host.example.com",
            "https://user@host.tail123.ts.net",
            "https://host.tail123.ts.net/path",
            "https://host.tail123.ts.net?x=y",
            "https://host.tail123.ts.net:8000",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                HOME.validate_origin(value)
        self.assertEqual(
            HOME.validate_origin("https://host.tail123.ts.net/"),
            "https://host.tail123.ts.net",
        )
        self.assertEqual(
            HOME.validate_origin("https://host.tail123.ts.net:8443"),
            "https://host.tail123.ts.net:8443",
        )

    def test_occupied_routes_are_rejected_without_any_mutation(self) -> None:
        config = {"ALLSAFE_HOME_HTTP_PORT": "18180"}
        for state in (
            {"TCP": {"443": {"HTTPS": True}}},
            {
                "Web": {
                    "host.tail.ts.net:443": {
                        "Handlers": {"/": {"Proxy": "http://127.0.0.1:80"}}
                    }
                }
            },
            {
                "TCP": {"443": {"HTTPS": True}},
                "Web": {
                    "host.tail.ts.net:443": {
                        "Handlers": {
                            "/": {"Proxy": "http://127.0.0.1:18180"},
                            "/other": {"Text": "keep"},
                        }
                    }
                },
            },
        ):
            with self.subTest(state=state), self.assertRaises(ValueError):
                HOME.ensure_serve_available(config, state, "host.tail.ts.net", 443)

    def test_exact_existing_route_is_idempotent_and_other_ports_are_preserved(
        self,
    ) -> None:
        config = {"ALLSAFE_HOME_HTTP_PORT": "18180"}
        state = {
            "TCP": {"443": {"HTTPS": True}, "8443": {"HTTPS": True}},
            "Web": {
                "host.tail.ts.net:443": {
                    "Handlers": {"/": {"Proxy": "http://127.0.0.1:18180"}}
                },
                "host.tail.ts.net:8443": {"Handlers": {"/": {"Text": "keep"}}},
            },
        }
        self.assertTrue(
            HOME.ensure_serve_available(config, state, "host.tail.ts.net", 443)
        )
        self.assertFalse(
            HOME.ensure_serve_available(config, {}, "host.tail.ts.net", 443)
        )
        self.assertEqual(
            state["Web"]["host.tail.ts.net:8443"]["Handlers"]["/"]["Text"], "keep"
        )

    def test_config_rejects_interpolation_and_insecure_file_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "home.env"
            content = (
                "ALLSAFE_HOME_ORIGIN=https://host.tail.ts.net\n"
                "ALLSAFE_HOME_PROJECT_NAME=allsafe-home\nALLSAFE_HOME_HTTP_PORT=18180\n"
            )
            path.write_text(content, encoding="utf-8")
            path.chmod(0o600)
            self.assertEqual(HOME.read_config(path)["ALLSAFE_HOME_HTTP_PORT"], "18180")
            path.write_text(content + "SECRET=$(unexpected)\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                HOME.read_config(path)
            if os.name != "nt":
                path.write_text(content, encoding="utf-8")
                path.chmod(0o644)
                with self.assertRaises(ValueError):
                    HOME.read_config(path)


if __name__ == "__main__":
    unittest.main()
