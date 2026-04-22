# SPDX-License-Identifier: GPL-2.0

import unittest
from pathlib import Path

from packaging import version

from tests.integration.test_utils import RunSubprocessMixin
from tests.integration.test_utils import get_podman_version


class TestPodmanComposeIncludeLongForm(unittest.TestCase, RunSubprocessMixin):
    @unittest.skipIf(get_podman_version() >= version.parse("5.0.0"), "Breaks as of podman-5.4.2.")
    def test_include_long_form(self) -> None:
        """
        Test long-form include syntax: dict with ``path`` and ``env_file`` keys.
        Both services (web-commons via explicit env_file, web-extra via default lookup)
        must be created under the expected project label.
        """
        main_path = Path(__file__).parent.parent.parent.parent
        compose_file = str(
            main_path / "tests" / "integration" / "include_long_form" / "docker-compose.yaml"
        )

        command_up = [
            "coverage",
            "run",
            str(main_path / "podman_compose.py"),
            "-f",
            compose_file,
            "up",
            "-d",
        ]

        command_check = [
            "podman",
            "ps",
            "-a",
            "--filter",
            "label=io.podman.compose.project=include_long_form",
            "--format",
            '"{{.Image}}"',
        ]

        command_ids = [
            "podman",
            "ps",
            "-a",
            "--filter",
            "label=io.podman.compose.project=include_long_form",
            "--format",
            '"{{.ID}}"',
        ]

        command_down = ["podman", "rm", "--force"]

        self.run_subprocess_assert_returncode(command_up)

        out, _ = self.run_subprocess_assert_returncode(command_check)
        expected_output = b'"localhost/nopush/podman-compose-test:latest"\n' * 2
        self.assertEqual(out, expected_output)

        out, _ = self.run_subprocess_assert_returncode(command_ids)
        self.assertNotEqual(out, b"")
        container_ids = [cid.strip('" \n') for cid in out.decode().strip().splitlines()]
        self.run_subprocess_assert_returncode(command_down + container_ids)

        out, _ = self.run_subprocess_assert_returncode(command_check)
        self.assertEqual(out, b"")
