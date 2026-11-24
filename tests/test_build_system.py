#!/usr/bin/env python3
"""Unit tests for configuration, paths, and duplicate-safe accounting."""

from __future__ import annotations

import io
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pyco_build.build import _flag_tokens_applied, _flags_in_makefile  # noqa: E402
from pyco_build.config import ConfigError, load_config  # noqa: E402
from pyco_build.paths import BuildPaths  # noqa: E402
from pyco_build.source import SourceError, _safe_extract  # noqa: E402
from pyco_build.util import (  # noqa: E402
    duplicate_safe_size,
    is_elf,
    iter_unique_regular_files,
    sha256_file,
)


class ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(ROOT)

    def test_expected_profiles_exist(self) -> None:
        self.assertEqual(
            set(self.config.profiles),
            {"baseline", "size", "lto", "static", "clang-oz"},
        )

    def test_version_pin_is_immutable(self) -> None:
        version = self.config.versions["3.14"]
        self.assertEqual(version.version, "3.14.9")
        self.assertEqual(version.tag, "v3.14.9")
        self.assertEqual(len(version.sha256), 64)
        self.assertEqual(len(version.git_commit), 40)
        self.assertTrue(version.enabled)

    def test_resolve_accepts_key_version_and_tag(self) -> None:
        for value in ("3.14", "3.14.9", "v3.14.9"):
            spec = self.config.resolve(value, "baseline", "linux-x86_64")
            self.assertEqual(spec.version.version, "3.14.9")

    def test_unknown_profile_fails(self) -> None:
        with self.assertRaises(ConfigError):
            self.config.resolve("3.14", "does-not-exist", "linux-x86_64")

    def test_unknown_target_fails(self) -> None:
        with self.assertRaises(ConfigError):
            self.config.resolve("3.14", "baseline", "windows-x86_64")

    def test_static_and_lto_profiles(self) -> None:
        static = self.config.profiles["static"]
        lto = self.config.profiles["lto"]
        clang = self.config.profiles["clang-oz"]
        self.assertIn("--disable-shared", static.configure)
        self.assertIn("--with-lto", lto.configure)
        self.assertEqual(clang.cc, "clang")
        self.assertEqual(clang.cflags, "-Oz")

    def test_release_selection_is_not_approved(self) -> None:
        selections = self.config.release_selection
        self.assertTrue(selections)
        self.assertFalse(any(selection.approved for selection in selections))


class ProfileEnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(ROOT)
        cls.prefix = "/opt/conda"
        cls.contaminated = {
            "CONDA_PREFIX": cls.prefix,
            "PATH": "/usr/bin",
            "CFLAGS": "-O2 -ffunction-sections -pipe",
            "CPPFLAGS": "-DNDEBUG -D_FORTIFY_SOURCE=2 -O2",
            "CXXFLAGS": "-O2 -fvisibility-inlines-hidden",
            "LDFLAGS": "-Wl,--gc-sections -Wl,-rpath,/opt/conda/lib",
            "CPATH": "/opt/conda/include",
            "PKG_CONFIG_PATH": "/contaminated/pkgconfig",
        }

    def test_baseline_discards_conda_flags(self) -> None:
        env = self.config.profiles["baseline"].environment(self.contaminated)
        self.assertEqual(env["CFLAGS"], "")
        self.assertEqual(env["CPPFLAGS"], f"-I{self.prefix}/include")
        self.assertEqual(env["CXXFLAGS"], "")
        self.assertEqual(
            env["LDFLAGS"],
            f"-L{self.prefix}/lib -Wl,-rpath-link,{self.prefix}/lib",
        )
        self.assertNotIn("-O2", env["CPPFLAGS"])
        self.assertNotIn("-DNDEBUG", env["CPPFLAGS"])
        self.assertNotIn("--gc-sections", env["LDFLAGS"])
        self.assertNotIn("CPATH", env)
        self.assertEqual(env["PKG_CONFIG_PATH"], f"{self.prefix}/lib/pkgconfig")
        self.assertEqual(env["LIBRARY_PATH"], f"{self.prefix}/lib")
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_profile_flags_are_exact(self) -> None:
        expected = {
            "baseline": "",
            "size": "-Os",
            "lto": "-Os",
            "static": "-Os",
            "clang-oz": "-Oz",
        }
        for name, cflags in expected.items():
            with self.subTest(profile=name):
                env = self.config.profiles[name].environment(self.contaminated)
                self.assertEqual(env["CFLAGS"], cflags)
                self.assertEqual(env["CC"], self.config.profiles[name].cc)
                self.assertEqual(env["CXX"], self.config.profiles[name].cxx)

    def test_pyco_prefix_takes_precedence(self) -> None:
        base = {
            "CONDA_PREFIX": "/activated/prefix",
            "PYCO_CONDA_PREFIX": "/locked/prefix",
            "LDFLAGS": "-Wl,--gc-sections",
        }
        env = self.config.profiles["size"].environment(base)
        self.assertEqual(env["CPPFLAGS"], "-I/locked/prefix/include")
        self.assertEqual(
            env["LDFLAGS"],
            "-L/locked/prefix/lib -Wl,-rpath-link,/locked/prefix/lib",
        )
        self.assertNotIn("activated", env["CPPFLAGS"])

    def test_environment_does_not_mutate_base(self) -> None:
        base = dict(self.contaminated)
        self.config.profiles["size"].environment(base)
        self.assertEqual(base, self.contaminated)


class PathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(ROOT)

    def test_paths_are_distinct_for_each_profile(self) -> None:
        baseline = BuildPaths(self.config.resolve("3.14", "baseline", "linux-x86_64"))
        size = BuildPaths(self.config.resolve("3.14", "size", "linux-x86_64"))
        self.assertEqual(baseline.source, size.source)
        self.assertNotEqual(baseline.work_root, size.work_root)
        self.assertNotEqual(baseline.prefix, size.prefix)
        self.assertNotEqual(baseline.results_dir, size.results_dir)

    def test_paths_are_distinct_for_each_target(self) -> None:
        self.config.targets["linux-arm64"] = type(
            next(iter(self.config.targets.values()))
        )(
            name="linux-arm64",
            platform="linux",
            arch="aarch64",
            runner="ubuntu-24.04-arm",
            container_image="ubuntu:24.04",
            glibc_baseline="2.39",
            apt_packages=(),
            notes="test-only target",
        )
        x86 = BuildPaths(self.config.resolve("3.14", "baseline", "linux-x86_64"))
        arm = BuildPaths(self.config.resolve("3.14", "baseline", "linux-arm64"))
        self.assertNotEqual(x86.work_root, arm.work_root)
        self.assertNotEqual(x86.prefix, arm.prefix)


class AccountingTests(unittest.TestCase):
    def test_duplicate_safe_size_counts_hardlinks_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.py"
            original.write_bytes(b"x" * 128)
            hardlink = root / "hardlink.py"
            os.link(original, hardlink)
            symlink = root / "symlink.py"
            symlink.symlink_to(original)
            self.assertEqual(duplicate_safe_size([original, hardlink, symlink]), 128)
            unique = list(iter_unique_regular_files(root))
            self.assertEqual(len(unique), 1)

    def test_duplicate_safe_size_counts_distinct_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.py"
            second = root / "second.py"
            first.write_bytes(b"a" * 10)
            second.write_bytes(b"b" * 20)
            self.assertEqual(duplicate_safe_size([first, second]), 30)

    def test_sha256_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload"
            path.write_bytes(b"pyco")
            self.assertEqual(
                sha256_file(path),
                "4e104dfbea13954793fec37c0550346ff6fbbe544750303656592b5436eb9c14",
            )

    def test_is_elf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload"
            path.write_bytes(b"\x7fELF" + b"\x00" * 16)
            self.assertTrue(is_elf(path))
            path.write_bytes(b"not elf")
            self.assertFalse(is_elf(path))


class BuildFlagTests(unittest.TestCase):
    def test_effective_flags_are_read_and_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            makefile = Path(directory) / "Makefile"
            makefile.write_text(
                "PY_CFLAGS = -Os -pthread\nLDFLAGS = -Wl,--gc-sections\n",
                encoding="utf-8",
            )
            effective = _flags_in_makefile(makefile)
            self.assertIn("-Os", effective["PY_CFLAGS"])
            self.assertTrue(_flag_tokens_applied("-Os", effective))
            self.assertTrue(_flag_tokens_applied("-Wl,--gc-sections", effective))
            self.assertFalse(_flag_tokens_applied("-Oz", effective))


class SourceSafetyTests(unittest.TestCase):
    def test_safe_extract_rejects_parent_path(self) -> None:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            info = tarfile.TarInfo("../escape")
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
        buffer.seek(0)
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "bad.tar"
            archive_path.write_bytes(buffer.getvalue())
            with self.assertRaises(SourceError):
                _safe_extract(archive_path, Path(directory) / "out")


if __name__ == "__main__":
    unittest.main()
