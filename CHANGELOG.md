# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- One-line `install.sh` and `uninstall.sh` scripts for isolated installs from
  PyPI. The installer does not modify an active conda environment.
- English and Chinese READMEs. `README.md` is a symlink to `README_en.md`.

### Changed

- Reworked the README to lead with the compatibility-versus-size tradeoff and
  compare SnugPy with full CPython, MicroPython, PocketPy, and Monty using
  measured `linux-x86_64` artifacts.

## [0.1.0] - 2026-11-27

### Added

- First public release of the SnugPy build and measurement toolchain.
- Seven build profiles: `baseline`, `size`, `lto`, `static`, `clang-oz`,
  `lean`, and `static-lean`.
- Seven distribution variants from one stripped CPython installation:
  `headless`, `headed`, `test`, `micro`, `nano`, `runtime`, and
  `runtime-nano`.
- `runtime` keeps preinstalled `site-packages` without pip or `ensurepip`.
- `runtime-nano` also removes precompiled bytecode, so modules compile on first
  import.
- Debian slim, distroless, and `scratch` runtime images. The scratch
  `runtime-nano` image measured about 32 MiB in CI on `linux-x86_64`.
- External-library support for OpenSSL, SQLite, zlib, zstd, bz2, lzma, libffi,
  and libuuid.
- ABI verification, deterministic `tar.xz` packaging, external-library
  inventory, and size, startup, RSS, and workload measurements.
- GitHub Actions release workflow for PyPI, Docker Hub, and GitHub Releases.

### Changed

- Release profile is `static-lean` on `linux-x86_64` with CPython `3.14.9`.
- Release archives are named with `SNUGPY_RELEASE` when it is set.
- Python 3.10 remains the minimum version for the SnugPy tooling and `zerodep`.
  It is not a CPython build target.

### Fixed

- Clang `--no-default-config` flag spelling for the Clang profiles.
- Debian system-library linking for `static-lean`.
- `static-lean` now uses safe ICF. Aggressive ICF merged address-taken
  type-slot functions and caused CPython regression failures and crashes.
- Benchmark and release containers install `netbase`, so service-name
  resolution tests have `/etc/services` and `/etc/protocols`. The Debian slim
  runtime image includes `netbase` for the same reason.
- External-library ABI gate reports missing or unexpected SONAMEs.
- Packaging preserves deterministic archive metadata and verifies licenses.
- The Python wheel bundles TOML configuration, so the installed CLI works
  outside a repository checkout. The release workflow smoke-tests that path
  before publishing.
- The release build adds the locked conda environment to `PATH`, so `clang`
  and the other pinned tools resolve during the build.

### Known limitations

- Only CPython `3.14.9` on `linux-x86_64` is built and tested.
- `static-lean` is a non-PIE executable. Container or VM isolation must be the
  security boundary.
- Runtime variants do not include pip, `ensurepip`, headers, or build tools.
- Distribution archives do not bundle external C libraries. Use an image, or
  provide the documented sonames at runtime.
- `runtime-nano` compiles standard-library modules on first import. Use
  `runtime` when startup latency matters more than image size.
- macOS and Windows are not supported.
