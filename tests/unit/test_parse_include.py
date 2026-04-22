# SPDX-License-Identifier: GPL-2.0
# pylint: disable=protected-access

import os
import tempfile
import textwrap
import unittest

from podman_compose import PodmanCompose


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content))


class TestProcessIncludeEntry(unittest.TestCase):
    """Unit tests for PodmanCompose._process_include_entry."""

    def setUp(self) -> None:
        self.pc = PodmanCompose()
        self.tmpdir = tempfile.mkdtemp()

    def _path(self, *parts: str) -> str:
        return os.path.join(self.tmpdir, *parts)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _make_compose(self, relpath: str, content: str) -> str:
        """Write a compose file and return its absolute path."""
        full = self._path(relpath)
        _write(full, content)
        return full

    def _make_env(self, relpath: str, mapping: dict) -> str:
        full = self._path(relpath)
        _write(full, "\n".join(f"{k}={v}" for k, v in mapping.items()) + "\n")
        return full

    # ------------------------------------------------------------------
    # short syntax
    # ------------------------------------------------------------------

    def test_short_syntax_returns_services(self) -> None:
        target = self._make_compose(
            "sub/compose.yaml",
            """\
            services:
              svc-a:
                image: busybox
            """,
        )
        parent_file = self._make_compose(
            "main.yaml",
            "services: {}",
        )
        result = self.pc._process_include_entry(
            os.path.relpath(target, self.tmpdir),
            {},
            parent_file,
        )
        self.assertIn("svc-a", result["services"])

    def test_short_syntax_loads_default_dotenv(self) -> None:
        """Default .env next to the included file is loaded for variable substitution."""
        self._make_env("sub/.env", {"MY_IMAGE": "busybox"})
        self._make_compose(
            "sub/compose.yaml",
            """\
            services:
              svc-a:
                image: ${MY_IMAGE}
            """,
        )
        parent_file = self._make_compose("main.yaml", "services: {}")

        result = self.pc._process_include_entry("sub/compose.yaml", {}, parent_file)
        self.assertEqual(result["services"]["svc-a"]["image"], "busybox")

    def test_parent_env_overrides_dotenv(self) -> None:
        """Parent environment takes precedence over the included file's .env."""
        self._make_env("sub/.env", {"MY_IMAGE": "from-dotenv"})
        self._make_compose(
            "sub/compose.yaml",
            """\
            services:
              svc-a:
                image: ${MY_IMAGE}
            """,
        )
        parent_file = self._make_compose("main.yaml", "services: {}")

        result = self.pc._process_include_entry(
            "sub/compose.yaml",
            {"MY_IMAGE": "from-parent"},
            parent_file,
        )
        self.assertEqual(result["services"]["svc-a"]["image"], "from-parent")

    # ------------------------------------------------------------------
    # long syntax — path variants
    # ------------------------------------------------------------------

    def test_long_syntax_path_string(self) -> None:
        """Long form with path as a plain string."""
        self._make_compose(
            "sub/compose.yaml",
            """\
            services:
              svc-b:
                image: busybox
            """,
        )
        parent_file = self._make_compose("main.yaml", "services: {}")

        result = self.pc._process_include_entry(
            {"path": "sub/compose.yaml"},
            {},
            parent_file,
        )
        self.assertIn("svc-b", result["services"])

    def test_long_syntax_path_list_merges_files(self) -> None:
        """Long form with path as a list merges all listed files into one model."""
        self._make_compose(
            "sub/base.yaml",
            """\
            services:
              svc-base:
                image: busybox
            """,
        )
        self._make_compose(
            "sub/extra.yaml",
            """\
            services:
              svc-extra:
                image: alpine
            """,
        )
        parent_file = self._make_compose("main.yaml", "services: {}")

        result = self.pc._process_include_entry(
            {"path": ["sub/base.yaml", "sub/extra.yaml"]},
            {},
            parent_file,
        )
        self.assertIn("svc-base", result["services"])
        self.assertIn("svc-extra", result["services"])

    # ------------------------------------------------------------------
    # long syntax — env_file variants
    # ------------------------------------------------------------------

    def test_long_syntax_explicit_env_file_string(self) -> None:
        """env_file as a string path loads variables for the included compose."""
        self._make_env("envs/custom.env", {"CUSTOM_IMAGE": "alpine"})
        self._make_compose(
            "sub/compose.yaml",
            """\
            services:
              svc-c:
                image: ${CUSTOM_IMAGE}
            """,
        )
        parent_file = self._make_compose("main.yaml", "services: {}")

        result = self.pc._process_include_entry(
            {"path": "sub/compose.yaml", "env_file": "../envs/custom.env"},
            {},
            parent_file,
        )
        self.assertEqual(result["services"]["svc-c"]["image"], "alpine")

    def test_long_syntax_explicit_env_file_list(self) -> None:
        """env_file as a list of paths — later files override earlier ones."""
        self._make_env("envs/base.env", {"IMG": "busybox", "TAG": "stable"})
        self._make_env("envs/override.env", {"TAG": "latest"})
        self._make_compose(
            "sub/compose.yaml",
            """\
            services:
              svc-d:
                image: ${IMG}:${TAG}
            """,
        )
        parent_file = self._make_compose("main.yaml", "services: {}")

        result = self.pc._process_include_entry(
            {
                "path": "sub/compose.yaml",
                "env_file": ["../envs/base.env", "../envs/override.env"],
            },
            {},
            parent_file,
        )
        self.assertEqual(result["services"]["svc-d"]["image"], "busybox:latest")

    def test_long_syntax_explicit_env_file_does_not_load_default_dotenv(self) -> None:
        """When env_file is explicit the default .env is NOT loaded automatically."""
        self._make_env("sub/.env", {"IMG": "should-not-be-used"})
        self._make_env("envs/explicit.env", {"IMG": "correct-image"})
        self._make_compose(
            "sub/compose.yaml",
            """\
            services:
              svc-e:
                image: ${IMG}
            """,
        )
        parent_file = self._make_compose("main.yaml", "services: {}")

        result = self.pc._process_include_entry(
            {"path": "sub/compose.yaml", "env_file": "../envs/explicit.env"},
            {},
            parent_file,
        )
        self.assertEqual(result["services"]["svc-e"]["image"], "correct-image")

    # ------------------------------------------------------------------
    # long syntax — project_directory
    # ------------------------------------------------------------------

    def test_long_syntax_project_directory_changes_default_dotenv_location(self) -> None:
        """project_directory shifts where the default .env is looked up."""
        self._make_env("projdir/.env", {"IMG": "from-projdir-env"})
        self._make_compose(
            "sub/compose.yaml",
            """\
            services:
              svc-f:
                image: ${IMG}
            """,
        )
        parent_file = self._make_compose("main.yaml", "services: {}")

        result = self.pc._process_include_entry(
            {"path": "sub/compose.yaml", "project_directory": "projdir"},
            {},
            parent_file,
        )
        self.assertEqual(result["services"]["svc-f"]["image"], "from-projdir-env")

    # ------------------------------------------------------------------
    # recursive / nested includes
    # ------------------------------------------------------------------

    def test_nested_include_is_resolved(self) -> None:
        """An included file that itself contains an include is handled recursively."""
        self._make_compose(
            "deep/compose.yaml",
            """\
            services:
              svc-deep:
                image: busybox
            """,
        )
        self._make_compose(
            "mid/compose.yaml",
            """\
            include:
              - ../deep/compose.yaml
            services:
              svc-mid:
                image: alpine
            """,
        )
        parent_file = self._make_compose("main.yaml", "services: {}")

        result = self.pc._process_include_entry("mid/compose.yaml", {}, parent_file)
        self.assertIn("svc-mid", result["services"])
        self.assertIn("svc-deep", result["services"])

    # ------------------------------------------------------------------
    # variable substitution in the include path itself
    # ------------------------------------------------------------------

    def test_variable_in_include_path_is_substituted(self) -> None:
        """
        Variables embedded in an include path (short form) are substituted before
        the path is resolved — the substitution happens via rec_subs in _parse_compose_file
        before _process_include_entry is called, so this test verifies that an
        already-substituted absolute path string is handled correctly.
        """
        target = self._make_compose(
            "sub/compose.yaml",
            """\
            services:
              svc-g:
                image: busybox
            """,
        )
        parent_file = self._make_compose("main.yaml", "services: {}")

        # Simulate a path that was already variable-substituted (absolute)
        result = self.pc._process_include_entry(target, {}, parent_file)
        self.assertIn("svc-g", result["services"])
