"""Static renderer deployment guardrails; live network/sandbox checks are separate."""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def service_block(name: str) -> str:
    text = (ROOT / "compose.renderer.yaml").read_text(encoding="utf-8")
    match = re.search(
        rf"^  {name}:\n(.*?)(?=^  \w+:|^volumes:|\Z)", text, re.MULTILINE | re.DOTALL
    )
    if not match:
        raise AssertionError(f"Missing renderer service: {name}")
    return match.group(1)


class RendererBoundaryTests(unittest.TestCase):
    def test_browser_cannot_join_an_application_or_host_network(self) -> None:
        block = service_block("renderer")
        self.assertRegex(block, r"network_mode: none\b")
        self.assertNotRegex(
            block,
            r"(?m)^    (ports|networks|env_file|environment|devices|pid|ipc|privileged|cap_add):",
        )
        self.assertIn('user: "10001:10001"', block)
        self.assertIn("cap_drop: [ALL]", block)
        self.assertIn("no-new-privileges:true", block)
        self.assertIn("read_only: true", block)
        self.assertIn("pids_limit: 256", block)
        self.assertIn("mem_limit: 1536m", block)
        self.assertIn("restart: always", block)
        self.assertNotIn("docker.sock", block)
        self.assertNotIn("api-data", block)
        self.assertNotIn("phishcatch-data", block)

    def test_renderer_requires_explicit_profile_and_enabling(self) -> None:
        self.assertIn("profiles: [renderer]", service_block("renderer"))
        self.assertIn("profiles: [renderer]", service_block("renderer_init"))
        analyzer = service_block("phishcatch")
        self.assertIn("${PHISHCATCH_OFFLINE_RENDER_ENABLED:-0}", analyzer)
        self.assertIn("renderer-socket:/run/phishcatch-renderer:ro", analyzer)
        self.assertNotIn("renderer-socket", (ROOT / "compose.home.yaml").read_text())

    def test_seccomp_is_reviewed_default_deny_with_user_namespace_support(self) -> None:
        raw = (ROOT / "deploy/renderer/seccomp.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849",
        )
        profile = json.loads(raw)
        self.assertEqual(profile["defaultAction"], "SCMP_ACT_ERRNO")
        self.assertTrue(
            any(
                entry.get("action") == "SCMP_ACT_ALLOW"
                and {"clone", "setns", "unshare"}.issubset(entry.get("names", []))
                for entry in profile["syscalls"]
            )
        )

    def test_image_context_is_an_allowlist_without_models_or_private_data(self) -> None:
        ignored = (
            (ROOT / "deploy/renderer/Dockerfile.dockerignore").read_text().splitlines()
        )
        self.assertEqual(ignored[0], "**")
        self.assertTrue(any("offline_renderer*.py" in line for line in ignored))
        self.assertFalse(
            any(
                line.startswith("!")
                and any(
                    value in line
                    for value in (".local", ".env", "models", "data/", ".git")
                )
                for line in ignored
            )
        )
        dockerfile = (ROOT / "deploy/renderer/Dockerfile").read_text()
        self.assertIn("pip install --require-hashes", dockerfile)
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertNotIn("COPY . ", dockerfile)


if __name__ == "__main__":
    unittest.main()
