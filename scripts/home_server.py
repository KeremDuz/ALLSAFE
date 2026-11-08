#!/usr/bin/env python3
"""Operate the named home-lab project with separate opt-in consumer ingress."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import secrets
import socket
import stat
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT / ".local" / "home-server" / "home.env"
MODEL_NAMES = ("phishcatch_url_model.pkl", "phishcatch_html_model.pkl")
APK_NAME = "PhishCatch-ALLSAFE-1.1.0.apk"


def prepare_downloads(env_file: Path, config: dict[str, str]) -> Path:
    """Prepare only our public artifact directory, separate from private state."""
    default = ROOT / ".local" / "home-server" / "downloads"
    target = Path(config.get("ALLSAFE_HOME_DOWNLOAD_DIR") or str(default))
    if not target.is_absolute():
        target = ROOT / target
    if target.is_symlink():
        raise ValueError("The public download directory must not be a symbolic link.")
    if not target.exists():
        allowed = {default.resolve(), (env_file.parent / "downloads").resolve()}
        if target.resolve() not in allowed:
            raise ValueError("Custom public artifact directory must already exist.")
        target.mkdir(parents=True, mode=0o755)
        target.chmod(0o755)
    if not target.is_dir():
        raise ValueError("Public artifact path must be a directory.")
    for item in target.iterdir():
        if (
            item.is_symlink()
            or not item.is_file()
            or item.name
            not in {
                APK_NAME,
                APK_NAME + ".sha256",
            }
        ):
            raise ValueError(
                "Public download directory may contain only the APK and its SHA-256 file."
            )
    return target


def run(
    arguments: list[str], *, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    """Use argv arrays: no shell parsing or secret expansion in command text."""
    return subprocess.run(
        arguments, check=True, text=True, capture_output=capture, cwd=ROOT
    )


def validate_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".ts.net")
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.port not in (None, 443, 8443)
    ):
        raise ValueError(
            "Use the verified https://device.tailnet.ts.net origin (443 or 8443)."
        )
    return value.rstrip("/")


def read_config(path: Path) -> dict[str, str]:
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError(
            "Secret configuration must be owner-only: chmod 600 <home.env>."
        )
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        name, value = line.split("=", 1)
        # The generated format deliberately avoids shell quoting/interpolation.
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or any(
            c in value for c in "\r\n$'\"\\"
        ):
            raise ValueError(
                "Unsupported configuration syntax; do not source this file."
            )
        result[name] = value
    validate_origin(result["ALLSAFE_HOME_ORIGIN"])
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,40}", result["ALLSAFE_HOME_PROJECT_NAME"]):
        raise ValueError("Invalid Compose project name.")
    port = int(result["ALLSAFE_HOME_HTTP_PORT"])
    if not 1024 <= port <= 65535:
        raise ValueError("Host port must be between 1024 and 65535.")
    return result


def compose(
    env_file: Path, *arguments: str, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    config = read_config(env_file)
    files = ["-f", str(ROOT / "compose.home.yaml")]
    if config.get("PHISHCATCH_PUBLIC_ENABLED") == "1":
        files += ["-f", str(ROOT / "compose.public.yaml")]
    # An explicit env file prevents the ordinary development .env from being selected.
    return run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            *files,
            *arguments,
        ],
        capture=capture,
    )


def initialize(args: argparse.Namespace) -> None:
    origin = validate_origin(args.origin)
    model_dir = Path(args.models).resolve(strict=True)
    if any(not (model_dir / name).is_file() for name in MODEL_NAMES):
        raise ValueError("Model directory must contain both configured .pkl files.")
    if any(c in str(model_dir) for c in "\r\n$'\"\\"):
        raise ValueError(
            "Use a Linux model path without quotes, backslashes or dollar signs."
        )
    if not re.fullmatch(r"[A-Za-z0-9._+@-]{3,254}", args.admin_email):
        raise ValueError("Invalid administrator email.")
    if not 1024 <= args.port <= 65535:
        raise ValueError("Host port must be between 1024 and 65535.")
    password = (
        sys.stdin.readline().rstrip("\r\n")
        if args.password_stdin
        else secrets.token_urlsafe(24)
    )
    if len(password) < 12 or not re.fullmatch(r"[A-Za-z0-9_.!@-]+", password):
        raise ValueError(
            "Password must contain >=12 safe characters (letters/digits/_.!@-)."
        )
    values = {
        "ALLSAFE_HOME_PROJECT_NAME": "allsafe-home",
        "ALLSAFE_HOME_RELEASE": "local",
        "ALLSAFE_HOME_ORIGIN": origin,
        "ALLSAFE_HOME_HTTP_PORT": str(args.port),
        "ALLSAFE_HOME_MODEL_DIR": str(model_dir),
        "ALLSAFE_HOME_PROVIDER_ENV": str(args.env_file.parent / "phishcatch.env"),
        "ALLSAFE_HOME_DOWNLOAD_DIR": str(args.env_file.parent / "downloads"),
        "ALLSAFE_HOME_ADMIN_EMAIL": args.admin_email.lower(),
        "ALLSAFE_HOME_ADMIN_PASSWORD": password,
        "ALLSAFE_HOME_SESSION_SECRET": secrets.token_urlsafe(48),
        "ALLSAFE_HOME_INTEGRATION_KEY": secrets.token_urlsafe(48),
    }
    args.env_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    provider_file = args.env_file.parent / "phishcatch.env"
    if args.env_file.exists() or provider_file.exists():
        raise ValueError(
            "Private configuration already exists; it will not be overwritten."
        )
    prepare_downloads(args.env_file, values)
    descriptor = os.open(args.env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
        output.write(
            "# Private ALLSAFE laboratory configuration; never commit or print.\n"
        )
        output.write("".join(f"{key}={value}\n" for key, value in values.items()))
    provider_descriptor = os.open(
        provider_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    with os.fdopen(provider_descriptor, "w", encoding="utf-8", newline="\n") as output:
        output.write(
            "# Optional server-side reputation provider keys. Never copy to clients.\n"
        )
        output.write(
            "VIRUSTOTAL_API_KEYS=\nGOOGLE_SAFE_BROWSING_API_KEY=\nGOOGLE_WEB_RISK_API_KEY=\nURLHAUS_AUTH_KEY=\n"
        )
    print(f"Private configuration created: {args.env_file}")
    print("Initial login is stored there. Values are deliberately not printed.")


def inspect_serve(config: dict[str, str]) -> tuple[dict[str, object], str, int]:
    state = json.loads(run(["tailscale", "status", "--json"], capture=True).stdout)
    expected = urlsplit(config["ALLSAFE_HOME_ORIGIN"])
    actual_name = str(state.get("Self", {}).get("DNSName", "")).rstrip(".")
    if state.get("BackendState") != "Running" or actual_name != expected.hostname:
        raise ValueError(
            "Configured origin does not match this connected Tailscale node."
        )
    served = json.loads(
        run(["tailscale", "serve", "status", "--json"], capture=True).stdout or "{}"
    )
    allowed_public = f"{actual_name}:8443"
    funnels = {key for key, value in served.get("AllowFunnel", {}).items() if value}
    expected_public = {"Handlers": {"/": {"Proxy": "http://127.0.0.1:18181"}}}
    if funnels and not (
        config.get("PHISHCATCH_PUBLIC_ENABLED") == "1"
        and expected.port in (None, 443)
        and funnels == {allowed_public}
        and served.get("Web", {}).get(allowed_public) == expected_public
        and served.get("TCP", {}).get("8443") == {"HTTPS": True}
        and config.get("PHISHCATCH_PUBLIC_ORIGIN") == f"https://{allowed_public}"
    ):
        raise ValueError(
            "Existing public Funnel detected; stop and review without changing it."
        )
    return served, actual_name, expected.port or 443


def ensure_serve_available(
    config: dict[str, str], served: dict[str, object], name: str, port: int
) -> bool:
    """Return True only for our exact mapping; reject all occupied/conflicting routes."""
    key = f"{name}:{port}"
    expected_proxy = f"http://127.0.0.1:{config['ALLSAFE_HOME_HTTP_PORT']}"
    endpoint = served.get("Web", {}).get(key)
    tcp = served.get("TCP", {}).get(str(port))
    if endpoint is None and tcp is None:
        return False
    if endpoint == {"Handlers": {"/": {"Proxy": expected_proxy}}} and tcp == {
        "HTTPS": True
    }:
        return True
    raise ValueError(
        "Selected HTTPS port already has a Serve route; no existing route was changed."
    )


def enable_serve(args: argparse.Namespace) -> None:
    config = read_config(args.env_file)
    served, name, port = inspect_serve(config)
    if ensure_serve_available(config, served, name, port):
        print("Exact private Serve mapping already exists; unchanged.")
        return
    # Save the entire pre-change Serve state privately. No reset/set-raw is used.
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = args.env_file.parent / (
        "tailscale-serve-before-" + timestamp + "-" + secrets.token_hex(4) + ".json"
    )
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(served, output, indent=2)
    run(
        [
            "tailscale",
            "serve",
            "--bg",
            f"--https={port}",
            f"http://127.0.0.1:{config['ALLSAFE_HOME_HTTP_PORT']}",
        ]
    )
    print("Private HTTPS route enabled. Funnel was not enabled.")


def check(args: argparse.Namespace) -> None:
    config = read_config(args.env_file)
    compose(args.env_file, "config", "--quiet")
    served, name, port = inspect_serve(config)
    if not ensure_serve_available(config, served, name, port):
        raise ValueError("The private Serve route has not been enabled.")
    with urlopen(
        config["ALLSAFE_HOME_ORIGIN"] + "/health/ready", timeout=15
    ) as response:
        if json.load(response).get("status") != "ready":
            raise ValueError("Core API readiness failed.")
    for path in ("/", "/admin/"):
        with urlopen(config["ALLSAFE_HOME_ORIGIN"] + path, timeout=15) as response:
            if "text/html" not in response.headers.get("Content-Type", ""):
                raise ValueError("Client route did not return HTML.")
    program = (
        "import json,urllib.request; "
        "d=json.load(urllib.request.urlopen('http://127.0.0.1:9000/health/layers',timeout=15)); "
        "s={x['name']:x for l in d['layers'] for x in l.get('scanners',[])}; "
        "assert s['MLModelScanner']['model_loaded'] and s['MLModelScanner']['probabilities_available']; "
        "assert s['HtmlScraper']['model_loaded']; "
        "assert not s['HtmlScraper']['browser_render_enabled']; "
        "print(json.dumps({'url_model_loaded':True,'html_model_loaded':True,"
        "'browser_render_enabled':False,'layer_status':d['status']}))"
    )
    compose(args.env_file, "exec", "-T", "phishcatch", "python", "-c", program)
    compose(args.env_file, "ps")
    print(
        "Infrastructure checks passed. Physical phone/camera and authenticated scan acceptance are separate."
    )


def enable_public(args: argparse.Namespace) -> None:
    """Publish only the reviewed consumer listener; never the ALLSAFE listener."""
    config = read_config(args.env_file)
    served, name, private_port = inspect_serve(config)
    origin = config.get("PHISHCATCH_PUBLIC_ORIGIN", "")
    if (
        config.get("PHISHCATCH_PUBLIC_ENABLED") != "1"
        or private_port != 443
        or origin != f"https://{name}:8443"
        or not ensure_serve_available(config, served, name, private_port)
    ):
        raise ValueError(
            "Prepare the separate consumer deployment before enabling public HTTPS."
        )
    key = f"{name}:8443"
    expected = {"Handlers": {"/": {"Proxy": "http://127.0.0.1:18181"}}}
    if key in served.get("Web", {}) and served["Web"][key] != expected:
        raise ValueError("Port 8443 belongs to another service; no route was changed.")
    if "8443" in served.get("TCP", {}) and served["TCP"]["8443"] != {"HTTPS": True}:
        raise ValueError("Port 8443 belongs to another TCP listener.")
    with urlopen("http://127.0.0.1:18181/", timeout=10) as response:
        if response.status != 200 or "text/html" not in response.headers.get(
            "Content-Type", ""
        ):
            raise ValueError("Consumer web is not ready.")
    for path in (
        "/admin/",
        "/api/v1/auth/me",
        "/api/v1/analyze",
        "/api/v1/integrations/allsafe/health",
        "/health/layers",
        "/openapi.json",
    ):
        try:
            with urlopen("http://127.0.0.1:18181" + path, timeout=5):
                raise ValueError("Consumer ingress exposed an unapproved route.")
        except HTTPError as error:
            if error.code != 404:
                raise ValueError("Consumer ingress route boundary failed.") from None
    if served.get("AllowFunnel", {}).get(key):
        print("Exact public consumer mapping already exists; unchanged.")
        return
    snapshot = args.env_file.parent / (
        "tailscale-before-public-" + secrets.token_hex(8) + ".json"
    )
    with os.fdopen(
        os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as output:
        json.dump(served, output, indent=2)
    run(
        [
            "tailscale",
            "funnel",
            "--bg",
            "--https=8443",
            "--yes",
            "http://127.0.0.1:18181",
        ]
    )
    after, _, _ = inspect_serve(config)
    if (
        not ensure_serve_available(config, after, name, 443)
        or after.get("Web", {}).get(key) != expected
        or not after.get("AllowFunnel", {}).get(key)
    ):
        raise ValueError(
            "Verify public mapping and preserved private mapping before use."
        )
    print("Public PhishCatch HTTPS enabled on 8443; ALLSAFE 443 remains private.")


def backup(args: argparse.Namespace) -> None:
    config = read_config(args.env_file)
    metadata = json.loads(
        compose(args.env_file, "config", "--format", "json", capture=True).stdout
    )
    running = compose(
        args.env_file, "ps", "--services", "--status", "running", capture=True
    ).stdout.splitlines()
    running = [
        service
        for service in running
        if service in {"edge", "public_edge", "phishcatch", "api"}
    ]
    destination = (
        args.env_file.parent
        / "backups"
        / dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    )
    destination.mkdir(parents=True, mode=0o700)
    if running:
        compose(args.env_file, "stop", *running)
    try:
        for volume, filename in (
            ("api-data", "allsafe.db"),
            ("phishcatch-data", "phishcatch_training.sqlite3"),
        ):
            source = metadata["volumes"][volume]["name"]
            program = (
                "import pathlib,sqlite3,os; "
                f"p=pathlib.Path('/data/{filename}'); "
                "assert p.is_file(),'Expected database missing'; "
                f"out=pathlib.Path('/backup/{filename}'); "
                "src=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True); dst=sqlite3.connect(out); "
                "src.backup(dst); assert dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; "
                "dst.close(); src.close(); os.chmod(out,0o600); "
                f"os.chown(out,{os.getuid()},{os.getgid()})"
            )
            run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--read-only",
                    "--user",
                    "0:0",
                    "--cap-drop",
                    "ALL",
                    "--cap-add",
                    "CHOWN",
                    "--cap-add",
                    "DAC_OVERRIDE",
                    "--security-opt",
                    "no-new-privileges:true",
                    "--mount",
                    f"type=volume,src={source},dst=/data,readonly",
                    "--mount",
                    f"type=bind,src={destination},dst=/backup",
                    "--entrypoint",
                    "python",
                    metadata["services"]["api"]["image"],
                    "-c",
                    program,
                ]
            )
        manifest = {
            "origin": config["ALLSAFE_HOME_ORIGIN"],
            "release": config["ALLSAFE_HOME_RELEASE"],
            "project": config["ALLSAFE_HOME_PROJECT_NAME"],
            "databases": ["allsafe.db", "phishcatch_training.sqlite3"],
        }
        (destination / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
    finally:
        if running:
            compose(args.env_file, "start", *running)
    print(f"Consistent database snapshots: {destination}")
    print(
        "Copy this private directory and home.env to a separate encrypted backup destination."
    )


def verify_backup(args: argparse.Namespace) -> None:
    """Restore copies into our own disposable volume, never into live volumes."""
    config = read_config(args.env_file)
    source = args.backup_dir.resolve(strict=True)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("project") != config["ALLSAFE_HOME_PROJECT_NAME"]:
        raise ValueError("Backup belongs to a different Compose project.")
    filenames = ["allsafe.db", "phishcatch_training.sqlite3"]
    if manifest.get("databases") != filenames:
        raise ValueError(
            "Backup manifest does not describe the complete database pair."
        )
    for filename in filenames:
        path = source / filename
        if path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError("Backup database missing, empty or a symbolic link.")
    metadata = json.loads(
        compose(args.env_file, "config", "--format", "json", capture=True).stdout
    )
    volume = (
        config["ALLSAFE_HOME_PROJECT_NAME"] + "-restore-check-" + secrets.token_hex(8)
    )
    run(
        [
            "docker",
            "volume",
            "create",
            "--label",
            "allsafe.temporary-restore=true",
            volume,
        ],
        capture=True,
    )
    try:
        program = "\n".join(
            [
                "import pathlib,sqlite3,json",
                f"files={filenames!r}",
                "report=[]",
                "for name in files:",
                "    source=pathlib.Path('/backup')/name",
                "    src=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)",
                "    dst=sqlite3.connect(str(pathlib.Path('/restore')/name))",
                "    src.backup(dst)",
                "    assert dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'",
                "    tables=dst.execute(\"SELECT count(*) FROM sqlite_master WHERE type='table'\").fetchone()[0]",
                "    assert tables>0",
                "    if name=='allsafe.db':",
                "        assert dst.execute('SELECT version_num FROM alembic_version').fetchone()",
                "    report.append({'database':name,'integrity':'ok','table_count':tables})",
                "    dst.close(); src.close()",
                "print(json.dumps(report))",
            ]
        )
        run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--user",
                "0:0",
                "--cap-drop",
                "ALL",
                "--cap-add",
                "DAC_READ_SEARCH",
                "--security-opt",
                "no-new-privileges:true",
                "--mount",
                f"type=volume,src={volume},dst=/restore",
                "--mount",
                f"type=bind,src={source},dst=/backup,readonly",
                "--entrypoint",
                "python",
                metadata["services"]["api"]["image"],
                "-c",
                program,
            ]
        )
    finally:
        # Only the unpredictable volume created by this invocation is removed.
        run(["docker", "volume", "rm", volume], capture=True)
    print(
        "Both snapshots restored and verified in an isolated temporary volume; live data unchanged."
    )


def start(args: argparse.Namespace) -> None:
    config = read_config(args.env_file)
    if not (ROOT / "build/home-client/web/index.html").is_file():
        raise ValueError(
            "Stage the managed Flutter release in build/home-client/web first."
        )
    model_dir = Path(config["ALLSAFE_HOME_MODEL_DIR"])
    if any(not (model_dir / name).is_file() for name in MODEL_NAMES):
        raise ValueError("Both configured model files must exist before starting.")
    prepare_downloads(args.env_file, config)
    runtime = ["edge", "phishcatch", "api"]
    if config.get("PHISHCATCH_PUBLIC_ENABLED") == "1":
        public_origin = validate_origin(config.get("PHISHCATCH_PUBLIC_ORIGIN", ""))
        private = urlsplit(config["ALLSAFE_HOME_ORIGIN"])
        public = urlsplit(public_origin)
        if (
            public.hostname != private.hostname
            or public.port != 8443
            or private.port not in (None, 443)
        ):
            raise ValueError(
                "Public PhishCatch must use the separate 8443 HTTPS listener."
            )
        if not (ROOT / "build/public-client/web/index.html").is_file():
            raise ValueError("Stage the consumer Flutter release first.")
        downloads = Path(config["PHISHCATCH_PUBLIC_DOWNLOAD_DIR"])
        if (
            downloads.is_symlink()
            or not downloads.is_dir()
            or any(
                item.is_symlink()
                or not item.is_file()
                or item.name
                not in {"PhishCatch-1.1.1.apk", "PhishCatch-1.1.1.apk.sha256"}
                for item in downloads.iterdir()
            )
        ):
            raise ValueError(
                "Consumer downloads may contain only the signed APK and hash."
            )
        runtime.insert(0, "public_edge")
        public_existing = compose(
            args.env_file, "ps", "-q", "public_edge", capture=True
        ).stdout.strip()
        if not public_existing:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 18181))
    # Reject an occupied port unless it belongs to this existing Compose edge.
    existing = compose(args.env_file, "ps", "-q", "edge", capture=True).stdout.strip()
    if not existing:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", int(config["ALLSAFE_HOME_HTTP_PORT"])))
    compose(args.env_file, "config", "--quiet")
    # Stop only our runtime services before migrations touch the persistent DB.
    # Recreate the namespace owner, its analyzer companion and the resolving proxy
    # as one project; neither the analyzer nor Nginx may retain an old API address.
    compose(args.env_file, "stop", *runtime)
    compose(
        args.env_file,
        "up",
        "-d",
        "--build",
        "--force-recreate",
        "--wait",
        "--wait-timeout",
        "240",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    actions = parser.add_subparsers(dest="action", required=True)
    init = actions.add_parser(
        "init", help="Create unique private server secrets without printing them"
    )
    init.add_argument("--origin", required=True)
    init.add_argument("--models", required=True)
    init.add_argument("--admin-email", default="admin@allsafe.local")
    init.add_argument("--port", type=int, default=18180)
    init.add_argument("--password-stdin", action="store_true")
    verify = actions.add_parser(
        "verify-backup", help="Test restores in a disposable isolated Docker volume"
    )
    verify.add_argument("--backup-dir", type=Path, required=True)
    for name in (
        "start",
        "stop",
        "status",
        "logs",
        "backup",
        "check",
        "serve-enable",
        "public-enable",
        "validate",
    ):
        actions.add_parser(name)
    args = parser.parse_args()
    args.env_file = args.env_file.resolve()
    try:
        if args.action == "init":
            initialize(args)
        elif args.action == "serve-enable":
            enable_serve(args)
        elif args.action == "public-enable":
            enable_public(args)
        elif args.action == "check":
            check(args)
        elif args.action == "backup":
            backup(args)
        elif args.action == "verify-backup":
            verify_backup(args)
        elif args.action == "start":
            start(args)
        elif args.action == "validate":
            compose(args.env_file, "config", "--quiet")
            print("Compose configuration is valid; secrets were not printed.")
        elif args.action == "stop":
            compose(args.env_file, "stop")
        elif args.action == "status":
            compose(args.env_file, "ps")
        elif args.action == "logs":
            # Nginx access logs contain request paths; do not share unredacted logs.
            compose(args.env_file, "logs", "--tail", "100", "api", "phishcatch", "edge")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        # Subprocess exceptions contain argv but never environment values.
        print(f"Operation stopped: {type(error).__name__}. {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
