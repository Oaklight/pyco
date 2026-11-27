#!/usr/bin/env python3
"""Unit tests for configuration, paths, and duplicate-safe accounting."""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from snugpy_build.build import _flag_tokens_applied, _flags_in_makefile  # noqa: E402
from snugpy_build.config import ConfigError, load_config  # noqa: E402
from snugpy_build.distributions import (  # noqa: E402
    DistributionError,
    load_distributions,
)
from snugpy_build.metrics import (  # noqa: E402
    _distribution_metrics,
    _parse_hyperfine,
)
from snugpy_build.package import (  # noqa: E402
    PackageError,
    _build_archive,
    _elf_type,
    _install_license_files,
)
from snugpy_build.paths import BuildPaths  # noqa: E402
from snugpy_build.report import _row, _write_report  # noqa: E402
from snugpy_build.source import SourceError, _safe_extract  # noqa: E402
from snugpy_build.validate import (  # noqa: E402
    _MULTIPROCESSING_SOCKET_BUDGET,
    _REGRTEST_TMPDIR_BUDGET,
    _SUN_PATH_MAX,
    _regression_temp_dir,
)
from snugpy_build.util import (  # noqa: E402
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
            {"baseline", "size", "lto", "static", "clang-oz", "lean", "static-lean"},
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
        lean = self.config.profiles["lean"]
        static_lean = self.config.profiles["static-lean"]
        self.assertIn("--disable-shared", static.configure)
        self.assertIn("--with-lto", lto.configure)
        self.assertEqual(clang.cc, "clang")
        self.assertEqual(clang.cflags, "-Oz")
        self.assertIn("--without-doc-strings", lean.configure)
        self.assertIn("-ffunction-sections", lean.cflags)
        self.assertIn("--gc-sections", lean.ldflags)
        self.assertIn("--disable-shared", static_lean.configure)
        self.assertIn("--without-doc-strings", static_lean.configure)
        self.assertEqual(static_lean.cc, "clang")
        self.assertIn("-fno-unwind-tables", static_lean.cflags)
        self.assertIn("-fvisibility=hidden", static_lean.cflags)
        self.assertIn("-no-pie", static_lean.ldflags)
        self.assertIn("-Wl,--icf=all", static_lean.ldflags)
        self.assertEqual(static_lean.external_libs, "system")

    def test_release_selection_is_not_approved(self) -> None:
        selections = self.config.release_selection
        self.assertTrue(selections)
        self.assertFalse(any(selection.approved for selection in selections))


class DistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.distributions = load_distributions(ROOT)

    def test_expected_variants_exist(self) -> None:
        names = {variant.name for variant in self.distributions.variants}
        self.assertEqual(
            names, {"headless", "headed", "test", "micro", "nano", "runtime"}
        )
        self.assertEqual(self.distributions.default, "headless")

    def test_headless_excludes_matched_tree(self) -> None:
        headless = self.distributions.get("headless")
        self.assertTrue(headless.matches_exclude("lib/python3.14/test/test_abc.py"))
        self.assertTrue(headless.matches_exclude("lib/python3.14/tkinter/__init__.py"))
        self.assertTrue(
            headless.matches_exclude(
                "lib/python3.14/lib-dynload/_tkinter.cpython-314-x86_64-linux-gnu.so"
            )
        )
        self.assertTrue(headless.matches_exclude("bin/idle3.14"))
        self.assertTrue(
            headless.matches_exclude("lib/python3.14/config-3.14-x86_64/python.o")
        )
        self.assertTrue(headless.matches_exclude("lib/libpython3.14.a"))
        self.assertTrue(
            headless.matches_exclude(
                "lib/python3.14/lib-dynload/_testcapi.cpython-314-x86_64-linux-gnu.so"
            )
        )
        self.assertFalse(
            headless.matches_exclude(
                "lib/python3.14/lib-dynload/math.cpython-314-x86_64-linux-gnu.so"
            )
        )
        self.assertFalse(headless.matches_exclude("lib/python3.14/json/__init__.py"))
        self.assertFalse(
            headless.matches_exclude("lib/python3.14/site-packages/test_helper.py")
        )

    def test_micro_drops_installer_docs_and_dev_files(self) -> None:
        micro = self.distributions.get("micro")
        self.assertTrue(
            micro.matches_exclude("lib/python3.14/site-packages/pip/__init__.py")
        )
        self.assertTrue(micro.matches_exclude("lib/python3.14/ensurepip/__init__.py"))
        self.assertTrue(micro.matches_exclude("include/python3.14/Python.h"))
        self.assertTrue(micro.matches_exclude("bin/pip3.14"))
        self.assertTrue(micro.matches_exclude("bin/python3.14-config"))
        self.assertTrue(
            micro.matches_exclude(
                "lib/python3.14/lib-dynload/_tkinter.cpython-314-x86_64-linux-gnu.so"
            )
        )
        self.assertFalse(
            micro.matches_exclude("lib/python3.14/__pycache__/json.cpython-314.pyc")
        )
        self.assertFalse(micro.matches_exclude("lib/python3.14/json/__init__.py"))
        self.assertFalse(
            micro.matches_exclude(
                "lib/python3.14/lib-dynload/_ssl.cpython-314-x86_64-linux-gnu.so"
            )
        )

    def test_nano_also_drops_precompiled_bytecode(self) -> None:
        nano = self.distributions.get("nano")
        self.assertTrue(
            nano.matches_exclude("lib/python3.14/__pycache__/json.cpython-314.pyc")
        )
        self.assertTrue(
            nano.matches_exclude("lib/python3.14/site-packages/pip/__init__.py")
        )
        self.assertFalse(nano.matches_exclude("lib/python3.14/json/__init__.py"))

    def test_runtime_keeps_third_party_packages_without_pip(self) -> None:
        runtime = self.distributions.get("runtime")
        self.assertFalse(
            runtime.matches_exclude("lib/python3.14/site-packages/numpy/__init__.py")
        )
        self.assertFalse(
            runtime.matches_exclude("lib/python3.14/site-packages/pandas/__init__.py")
        )
        self.assertFalse(
            runtime.matches_exclude(
                "lib/python3.14/site-packages/numpy/core/_multiarray_umath.so"
            )
        )
        self.assertTrue(
            runtime.matches_exclude("lib/python3.14/site-packages/pip/__init__.py")
        )
        self.assertTrue(
            runtime.matches_exclude(
                "lib/python3.14/site-packages/pip-26.2.2.dist-info/METADATA"
            )
        )
        self.assertTrue(runtime.matches_exclude("lib/python3.14/ensurepip/__init__.py"))
        self.assertTrue(runtime.matches_exclude("bin/pip3.14"))

    def test_headed_keeps_tkinter_but_drops_tests(self) -> None:
        headed = self.distributions.get("headed")
        self.assertFalse(headed.matches_exclude("lib/python3.14/tkinter/__init__.py"))
        self.assertTrue(headed.matches_exclude("lib/python3.14/test/test_abc.py"))

    def test_test_variant_excludes_nothing(self) -> None:
        full = self.distributions.get("test")
        self.assertFalse(full.matches_exclude("lib/python3.14/test/test_abc.py"))
        self.assertEqual(full.exclude, ())

    def test_unknown_distribution_fails(self) -> None:
        with self.assertRaises(DistributionError):
            self.distributions.get("does-not-exist")

    def test_trailing_slash_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configs = root / "configs"
            configs.mkdir()
            (configs / "distributions.toml").write_text(
                "\n".join(
                    [
                        "schema_version = 1",
                        'default = "plain"',
                        "[variants.plain]",
                        'exclude = ["lib/python*/test/"]',
                    ]
                ),
                encoding="utf-8",
            )
            variant = load_distributions(root).get("plain")
            self.assertTrue(variant.matches_exclude("lib/python3.14/test/test_abc.py"))

    def test_parent_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configs = root / "configs"
            configs.mkdir()
            (configs / "distributions.toml").write_text(
                "\n".join(
                    [
                        "schema_version = 1",
                        'default = "plain"',
                        "[variants.plain]",
                        'exclude = ["../escape"]',
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(DistributionError):
                load_distributions(root)


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
            "LD_LIBRARY_PATH": "/custom/lib",
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
        self.assertEqual(env["LD_LIBRARY_PATH"], f"{self.prefix}/lib:/custom/lib")
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_profile_flags_are_exact(self) -> None:
        lean_cflags = (
            "-Oz -ffunction-sections -fdata-sections "
            "-fno-asynchronous-unwind-tables -fno-ident"
        )
        static_lean_cflags = (
            "-no-default-config --gcc-toolchain=/usr -Oz "
            "-ffunction-sections -fdata-sections "
            "-fno-asynchronous-unwind-tables -fno-unwind-tables "
            "-fno-ident -fvisibility=hidden -fno-semantic-interposition"
        )
        expected = {
            "baseline": "",
            "size": "-Os",
            "lto": "-Os",
            "static": "-Os",
            "clang-oz": "-Oz",
            "lean": lean_cflags,
            "static-lean": static_lean_cflags,
        }
        for name, cflags in expected.items():
            with self.subTest(profile=name):
                env = self.config.profiles[name].environment(self.contaminated)
                self.assertEqual(env["CFLAGS"], cflags)
                self.assertEqual(env["CC"], self.config.profiles[name].cc)
                self.assertEqual(env["CXX"], self.config.profiles[name].cxx)

    def test_system_external_libs_drop_conda_search_paths(self) -> None:
        env = self.config.profiles["static-lean"].environment(self.contaminated)
        self.assertEqual(
            env["PKG_CONFIG_LIBDIR"],
            "/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/lib/pkgconfig:/usr/share/pkgconfig",
        )
        self.assertNotIn(f"-I{self.prefix}/include", env["CPPFLAGS"])
        self.assertNotIn(f"-L{self.prefix}/lib", env["LDFLAGS"])
        self.assertIn("-L/usr/lib/x86_64-linux-gnu", env["LDFLAGS"])
        self.assertIn("-L/lib/x86_64-linux-gnu", env["LDFLAGS"])
        self.assertNotIn("LIBRARY_PATH", env)
        self.assertEqual(env["LD_LIBRARY_PATH"], "/custom/lib")
        self.assertEqual(env["PKG_CONFIG"], "/usr/bin/pkg-config")
        self.assertEqual(env["PKG_CONFIG_DONT_DEFINE_PREFIX"], "1")

    def test_system_external_libs_ignore_conda_sysroot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            (prefix / "x86_64-conda-linux-gnu" / "sysroot" / "usr" / "lib").mkdir(
                parents=True
            )
            env = self.config.profiles["static-lean"].environment(
                {
                    "CONDA_PREFIX": str(prefix),
                    "LD_LIBRARY_PATH": f"{prefix}/lib:/custom/lib",
                }
            )
        ldflags = env["LDFLAGS"]
        self.assertNotIn("-Wl,--sysroot", ldflags)
        self.assertNotIn(str(prefix), ldflags)
        self.assertNotIn(f"-I{prefix}/include", env["CPPFLAGS"])
        self.assertNotIn(f"-L{prefix}/lib", ldflags)
        self.assertEqual(env["LD_LIBRARY_PATH"], "/custom/lib")

    def test_snugpy_prefix_takes_precedence(self) -> None:
        base = {
            "CONDA_PREFIX": "/activated/prefix",
            "SNUGPY_CONDA_PREFIX": "/locked/prefix",
            "LDFLAGS": "-Wl,--gc-sections",
        }
        env = self.config.profiles["size"].environment(base)
        self.assertEqual(env["CPPFLAGS"], "-I/locked/prefix/include")
        self.assertEqual(
            env["LDFLAGS"],
            "-L/locked/prefix/lib -Wl,-rpath-link,/locked/prefix/lib",
        )
        self.assertEqual(env["LD_LIBRARY_PATH"], "/locked/prefix/lib")
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

    def test_package_archive_uses_xz(self) -> None:
        baseline = BuildPaths(self.config.resolve("3.14", "baseline", "linux-x86_64"))
        self.assertTrue(baseline.package_archive.name.endswith("-headless.tar.xz"))
        headed = baseline.package_archive_for("headed")
        self.assertTrue(headed.name.endswith("-headed.tar.xz"))
        self.assertNotEqual(baseline.package_archive, headed)

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


class PackageTests(unittest.TestCase):
    def test_elf_type_recognizes_executables_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload"
            header = bytearray(20)
            header[:4] = b"\x7fELF"
            header[4] = 2
            header[5] = 1
            header[16:18] = (2).to_bytes(2, "little")
            path.write_bytes(header)
            self.assertEqual(_elf_type(path), 2)
            header[16:18] = (1).to_bytes(2, "little")
            path.write_bytes(header)
            self.assertEqual(_elf_type(path), 1)
            path.write_bytes(b"not elf")
            self.assertIsNone(_elf_type(path))

    def test_xz_archive_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix"
            prefix.mkdir()
            (prefix / "payload.txt").write_text("snugpy\n", encoding="utf-8")
            (prefix / "empty").mkdir()
            first = root / "first.tar.xz"
            second = root / "second.tar.xz"
            _build_archive(prefix, first, "snugpy-root")
            _build_archive(prefix, second, "snugpy-root")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first, "r:*") as archive:
                names = archive.getnames()
                self.assertIn("snugpy-root/payload.txt", names)
                member = archive.extractfile("snugpy-root/payload.txt")
                assert member is not None
                self.assertEqual(member.read(), b"snugpy\n")

    def test_archive_excludes_matched_trees(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix"
            (prefix / "lib" / "python3.14" / "test").mkdir(parents=True)
            (prefix / "lib" / "python3.14" / "json").mkdir(parents=True)
            (prefix / "lib" / "python3.14" / "test" / "test_abc.py").write_text(
                "x\n", encoding="utf-8"
            )
            (prefix / "lib" / "python3.14" / "json" / "__init__.py").write_text(
                "y\n", encoding="utf-8"
            )
            archive_path = root / "variant.tar.xz"
            _build_archive(
                prefix,
                archive_path,
                "snugpy-root",
                exclude=lambda relative: relative.startswith("lib/python3.14/test/"),
            )
            with tarfile.open(archive_path, "r:*") as archive:
                names = archive.getnames()
            self.assertIn("snugpy-root/lib/python3.14/json/__init__.py", names)
            self.assertNotIn("snugpy-root/lib/python3.14/test/test_abc.py", names)

    def test_license_files_are_staged_from_project_and_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            (project / "licenses").mkdir(parents=True)
            (project / "LICENSE").write_text("mit\n", encoding="utf-8")
            (project / "THIRD_PARTY_LICENSES.md").write_text(
                "third-party\n", encoding="utf-8"
            )
            (project / "licenses" / "CPython-PSF-LICENSE.txt").write_text(
                "vendored\n", encoding="utf-8"
            )
            source = root / "source"
            (source / "Doc").mkdir(parents=True)
            (source / "LICENSE").write_text("psf\n", encoding="utf-8")
            (source / "Doc" / "license.rst").write_text("inventory\n", encoding="utf-8")
            staging = root / "staging"
            staging.mkdir()

            installed = _install_license_files(staging, project, source)

            self.assertEqual((staging / "LICENSE").read_text(), "mit\n")
            self.assertEqual(
                (staging / "THIRD_PARTY_LICENSES.md").read_text(),
                "third-party\n",
            )
            self.assertEqual(
                (staging / "licenses" / "CPython-PSF-LICENSE.txt").read_text(),
                "psf\n",
            )
            self.assertEqual(
                (staging / "licenses" / "CPython-third-party-licenses.rst").read_text(),
                "inventory\n",
            )
            self.assertEqual(len(installed), len(set(installed)))

    def test_missing_license_inventory_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            (project / "licenses").mkdir(parents=True)
            (project / "LICENSE").write_text("mit\n", encoding="utf-8")
            (project / "licenses" / "CPython-PSF-LICENSE.txt").write_text(
                "psf\n", encoding="utf-8"
            )
            staging = root / "staging"
            staging.mkdir()

            with self.assertRaises(PackageError):
                _install_license_files(staging, project, root / "source")


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
            path.write_bytes(b"snugpy")
            self.assertEqual(
                sha256_file(path),
                "e64774089588feb2af4ee084af742d89e7fddf7a8791a74f8c3b66782c8c9046",
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


class HyperfineParseTests(unittest.TestCase):
    def _parse(self, payload: dict[str, object], runs: int = 5) -> dict[str, float]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hyperfine.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return _parse_hyperfine(path, ["python", "-c", "pass"], runs)

    def test_hyperfine_2_schema(self) -> None:
        payload = {
            "primary_metric": "time_wall_clock",
            "results": [
                {
                    "measurements": [{"time_wall_clock": {"value": 0.1}}] * 3,
                    "summary": {
                        "time_wall_clock": {
                            "median": 0.5,
                            "mean": 0.6,
                            "min": 0.4,
                            "max": 0.7,
                            "stddev": 0.1,
                        }
                    },
                }
            ],
        }
        parsed = self._parse(payload)
        self.assertEqual(parsed["median_ms"], 500.0)
        self.assertEqual(parsed["mean_ms"], 600.0)
        self.assertEqual(parsed["min_ms"], 400.0)
        self.assertEqual(parsed["max_ms"], 700.0)
        self.assertEqual(parsed["stddev_ms"], 100.0)
        self.assertEqual(parsed["runs"], 3)

    def test_legacy_hyperfine_schema(self) -> None:
        payload = {
            "results": [
                {
                    "median": 0.25,
                    "mean": 0.3,
                    "min": 0.2,
                    "max": 0.4,
                    "stddev": 0.05,
                }
            ]
        }
        parsed = self._parse(payload, runs=7)
        self.assertEqual(parsed["median_ms"], 250.0)
        self.assertEqual(parsed["runs"], 7)


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(ROOT)

    def test_failure_reason_string_is_not_split(self) -> None:
        row = _row(
            {
                "profile": "baseline",
                "failure_reasons": "zerodep full tests not run",
            }
        )
        self.assertEqual(row["failure_reasons"], "zerodep full tests not run")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.md"
            _write_report(path, [row], self.config)
            text = path.read_text(encoding="utf-8")
        self.assertIn("- baseline: zerodep full tests not run", text)
        self.assertNotIn("z; e", text)

    def test_failure_reason_list_is_preserved(self) -> None:
        row = _row(
            {
                "profile": "size",
                "failure_reasons": ["full CPython suite not run", "network disabled"],
            }
        )
        self.assertEqual(
            row["failure_reasons"], "full CPython suite not run; network disabled"
        )

    def test_packaged_size_and_archive_are_reported(self) -> None:
        row = _row(
            {
                "profile": "baseline",
                "installed_total_bytes": 100,
                "packaged_installed_bytes": 80,
                "archive_bytes": 50,
                "archive_format": "xz",
                "package_smoke_result": "pass",
            }
        )
        self.assertEqual(row["installed_total_bytes"], 80)
        self.assertEqual(row["installed_prefix_bytes"], 100)
        self.assertEqual(row["archive_bytes"], 50)
        self.assertEqual(row["package_smoke_result"], "pass")

    def test_distribution_variants_are_reported(self) -> None:
        row = _row(
            {
                "profile": "baseline",
                "cpython_version": "3.14.9",
                "default_distribution": "headless",
                "distributions": {
                    "headless": {
                        "installed_bytes": 80,
                        "archive_bytes": 50,
                        "status": "pass",
                    },
                    "test": {
                        "installed_bytes": 200,
                        "archive_bytes": 70,
                        "status": "pass",
                    },
                },
            }
        )
        self.assertEqual(row["default_distribution"], "headless")
        parsed = json.loads(row["distribution_metrics"])
        self.assertEqual(parsed["headless"]["archive_bytes"], 50)
        self.assertEqual(parsed["test"]["installed_bytes"], 200)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.md"
            _write_report(path, [row], self.config)
            text = path.read_text(encoding="utf-8")
        self.assertIn("## Distribution variants", text)
        self.assertIn("| headless (default) | 80 | 50 | pass |", text)
        self.assertIn("| test | 200 | 70 | pass |", text)

    def test_distribution_metadata_is_normalized(self) -> None:
        normalized = _distribution_metrics(
            {
                "variants": {
                    "headless": {
                        "archive": "/tmp/headless.tar.xz",
                        "archive_bytes": 50,
                        "installed_bytes": 80,
                        "status": "pass",
                    },
                    "ignored": "not-a-table",
                }
            }
        )
        self.assertEqual(
            normalized["headless"],
            {
                "description": "",
                "archive": "/tmp/headless.tar.xz",
                "archive_format": None,
                "archive_bytes": 50,
                "archive_sha256": None,
                "installed_bytes": 80,
                "status": "pass",
            },
        )
        self.assertNotIn("ignored", normalized)


class RegressionTempDirTests(unittest.TestCase):
    def test_tmpdir_stays_below_sun_path_limit(self) -> None:
        path = _regression_temp_dir()
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        self.assertTrue(path.is_dir())
        self.assertEqual(path.parent, Path("/tmp"))
        self.assertLessEqual(len(str(path)), 39)
        self.assertLess(
            len(str(path)) + _REGRTEST_TMPDIR_BUDGET + _MULTIPROCESSING_SOCKET_BUDGET,
            _SUN_PATH_MAX,
        )


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
