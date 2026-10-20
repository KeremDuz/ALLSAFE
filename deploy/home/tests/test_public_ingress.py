"""Exercise public-ingress opt-in and the boundary that keeps ALLSAFE private."""

import copy
import json
import re
import subprocess
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SPEC = spec_from_file_location(
    "public_ingress_home_server", ROOT / "scripts/home_server.py"
)
assert SPEC and SPEC.loader
HOME = module_from_spec(SPEC)
SPEC.loader.exec_module(HOME)

HOST = "host.tail123.ts.net"
PRIVATE_ORIGIN = f"https://{HOST}"
PUBLIC_ORIGIN = f"https://{HOST}:8443"


def private_config() -> dict[str, str]:
    return {"ALLSAFE_HOME_ORIGIN": PRIVATE_ORIGIN, "ALLSAFE_HOME_HTTP_PORT": "18180"}


def public_config() -> dict[str, str]:
    return {
        **private_config(),
        "PHISHCATCH_PUBLIC_ENABLED": "1",
        "PHISHCATCH_PUBLIC_ORIGIN": PUBLIC_ORIGIN,
    }


def approved_serve() -> dict[str, object]:
    return {
        "TCP": {"443": {"HTTPS": True}, "8443": {"HTTPS": True}},
        "Web": {
            f"{HOST}:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:18180"}}},
            f"{HOST}:8443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:18181"}}},
        },
        "AllowFunnel": {f"{HOST}:8443": True},
    }


def nginx_block(source: str, directive: str) -> str:
    """Read a known configuration block, including its nested limit_except block."""
    match = re.search(re.escape(directive) + r"\s*\{", source)
    if match is None:
        raise AssertionError(f"Missing configuration block: {directive}")
    start = match.end()
    depth = 1
    for position in range(start, len(source)):
        if source[position] == "{":
            depth += 1
        elif source[position] == "}":
            depth -= 1
            if depth == 0:
                return source[start:position]
    raise AssertionError(f"Unclosed configuration block: {directive}")


class PublicIngressGuardTests(unittest.TestCase):
    def inspect(self, config: dict[str, str], serve: dict[str, object]):
        state = {"BackendState": "Running", "Self": {"DNSName": HOST + "."}}
        results = [
            subprocess.CompletedProcess([], 0, json.dumps(state)),
            subprocess.CompletedProcess([], 0, json.dumps(serve)),
        ]
        with patch.object(HOME, "run", side_effect=results) as mocked:
            try:
                return HOME.inspect_serve(config)
            finally:
                self.assertEqual(
                    [call.args[0] for call in mocked.call_args_list],
                    [
                        ["tailscale", "status", "--json"],
                        ["tailscale", "serve", "status", "--json"],
                    ],
                )

    def test_only_explicit_opt_in_accepts_exact_separate_public_listener(self) -> None:
        serve = approved_serve()
        original = copy.deepcopy(serve)
        self.assertEqual(self.inspect(public_config(), serve), (serve, HOST, 443))
        self.assertEqual(serve, original)
        for flag in (None, "", "0", "true", "01"):
            config = public_config()
            if flag is None:
                del config["PHISHCATCH_PUBLIC_ENABLED"]
            else:
                config["PHISHCATCH_PUBLIC_ENABLED"] = flag
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                self.inspect(config, serve)

    def test_funnel_can_never_publish_private_443_or_any_other_target(self) -> None:
        for funnels in (
            {f"{HOST}:443": True},
            {f"{HOST}:8443": True, f"{HOST}:443": True},
            {f"{HOST}:10000": True},
            {"other.tail123.ts.net:8443": True},
        ):
            serve = approved_serve()
            serve["AllowFunnel"] = funnels
            for config in (private_config(), public_config()):
                with (
                    self.subTest(funnels=funnels, config=config),
                    self.assertRaises(ValueError),
                ):
                    self.inspect(config, serve)

    def test_public_funnel_requires_exact_proxy_https_and_origin(self) -> None:
        invalid_serve = []
        for proxy in (
            "http://127.0.0.1:18180",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:9000",
            "http://localhost:18181",
        ):
            serve = approved_serve()
            serve["Web"][f"{HOST}:8443"]["Handlers"]["/"]["Proxy"] = proxy
            invalid_serve.append(serve)
        serve = approved_serve()
        serve["Web"][f"{HOST}:8443"]["Handlers"]["/admin"] = {"Text": "extra"}
        invalid_serve.append(serve)
        for tcp in (
            {},
            {"HTTPS": False},
            {"HTTPS": True, "TCPForward": "127.0.0.1:8000"},
        ):
            serve = approved_serve()
            serve["TCP"]["8443"] = tcp
            invalid_serve.append(serve)
        for serve in invalid_serve:
            with self.subTest(serve=serve), self.assertRaises(ValueError):
                self.inspect(public_config(), serve)
        for field, value in (
            ("PHISHCATCH_PUBLIC_ORIGIN", PRIVATE_ORIGIN),
            ("PHISHCATCH_PUBLIC_ORIGIN", "https://other.tail123.ts.net:8443"),
            ("ALLSAFE_HOME_ORIGIN", PUBLIC_ORIGIN),
        ):
            config = {**public_config(), field: value}
            with self.subTest(config=config), self.assertRaises(ValueError):
                self.inspect(config, approved_serve())

    def test_private_serve_remains_valid_when_funnel_is_absent_or_false(self) -> None:
        for config in (private_config(), public_config()):
            for funnels in ({}, {f"{HOST}:443": False, f"{HOST}:8443": False}):
                serve = approved_serve()
                serve["AllowFunnel"] = funnels
                self.assertEqual(self.inspect(config, serve), (serve, HOST, 443))

    def test_compose_overlay_is_included_only_for_literal_enabled_flag(self) -> None:
        env_file = ROOT / ".local/test-public-ingress.env"
        for flag in (None, "", "0", "true", "01", "1"):
            config = {} if flag is None else {"PHISHCATCH_PUBLIC_ENABLED": flag}
            with (
                self.subTest(flag=flag),
                patch.object(HOME, "read_config", return_value=config),
                patch.object(HOME, "run") as mocked,
            ):
                HOME.compose(env_file, "config", "--quiet", capture=True)
            command = mocked.call_args.args[0]
            self.assertEqual(
                command[:4], ["docker", "compose", "--env-file", str(env_file)]
            )
            self.assertIn(str(ROOT / "compose.home.yaml"), command)
            self.assertEqual(str(ROOT / "compose.public.yaml") in command, flag == "1")
            self.assertEqual(command[-2:], ["config", "--quiet"])
            self.assertTrue(mocked.call_args.kwargs["capture"])


class PublicNginxBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (ROOT / "deploy/public/nginx.conf").read_text(encoding="utf-8")
        cls.analysis = nginx_block(cls.source, "location = /api/v1/public/analyze")

    def test_only_exact_anonymous_analysis_can_reach_a_backend(self) -> None:
        proxies = re.findall(r"\bproxy_pass\s+([^;]+);", self.source)
        self.assertEqual(proxies, ["http://127.0.0.1:9000/api/v1/public/analyze"])
        self.assertIn("limit_except POST { deny all; }", self.analysis)
        self.assertRegex(nginx_block(self.source, "location /"), r"^\s*return 404;\s*$")
        for prohibited in (
            "/api/auth",
            "/admin",
            "/api/v1/analyze",
            "/api/v1/integrations",
            "/health",
        ):
            self.assertNotRegex(
                self.source, r"location\s+(?:=\s+)?" + re.escape(prohibited) + r"\s*\{"
            )

    def test_anonymous_ingress_strips_identity_and_disables_url_access_logging(
        self,
    ) -> None:
        for header in (
            "Authorization",
            "Cookie",
            "X-Integration-Key",
            "X-CSRF-Token",
            "X-Forwarded-For",
        ):
            self.assertIn(f'proxy_set_header {header} "";', self.analysis)
        self.assertIn("proxy_hide_header Set-Cookie;", self.analysis)
        self.assertIn("access_log off;", self.source)
        self.assertIn("add_header Referrer-Policy no-referrer always;", self.source)
        self.assertIn("add_header Cache-Control no-store always;", self.source)

    def test_public_capacity_is_global_bounded_and_not_based_on_spoofable_ip(
        self,
    ) -> None:
        self.assertRegex(
            self.source,
            r"limit_req_zone\s+\$server_name\s+zone=consumer_rate:1m\s+rate=6r/m;",
        )
        self.assertRegex(
            self.source, r"limit_conn_zone\s+\$server_name\s+zone=consumer_active:1m;"
        )
        for directive in (
            "limit_req zone=consumer_rate burst=2 nodelay;",
            "limit_conn consumer_active 1;",
            "limit_req_status 429;",
            "limit_conn_status 429;",
            "proxy_connect_timeout 5s;",
            "proxy_read_timeout 90s;",
        ):
            self.assertIn(directive, self.analysis)
        body_limit = re.search(r"client_max_body_size\s+(\d+)k;", self.source)
        self.assertIsNotNone(body_limit)
        self.assertLessEqual(int(body_limit.group(1)), 16)
        self.assertIn("client_body_timeout 10s;", self.source)

    def test_download_and_static_routes_are_allowlisted_without_directory_index(
        self,
    ) -> None:
        download = nginx_block(
            self.source, "location = /downloads/PhishCatch-1.1.1.apk"
        )
        self.assertIn("disable_symlinks on;", download)
        self.assertIn("try_files $uri =404;", download)
        self.assertIn("application/vnd.android.package-archive", download)
        self.assertIn("autoindex off;", self.source)
        self.assertIn("location = / { try_files /index.html =404; }", self.source)
        self.assertIn("(?:assets|canvaskit|icons)", self.source)
        self.assertNotIn("try_files $uri /index.html", self.source)


if __name__ == "__main__":
    unittest.main()
