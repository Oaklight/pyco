# SnugPy

[![CI](https://github.com/Oaklight/snugpy/actions/workflows/ci.yml/badge.svg)](https://github.com/Oaklight/snugpy/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/snugpy.svg)](https://pypi.org/project/snugpy/)
[![Python versions](https://img.shields.io/pypi/pyversions/snugpy.svg)](https://pypi.org/project/snugpy/)
[![Docker pulls](https://img.shields.io/docker/pulls/oaklight/snugpy.svg)](https://hub.docker.com/r/oaklight/snugpy)
[![License](https://img.shields.io/github/license/Oaklight/snugpy.svg)](LICENSE)

English | [中文](README_zh.md)

**Whole Python. Small footprint.**

SnugPy turns CPython into a deployable runtime. It starts from pinned CPython
3.14.9, keeps the language, core standard library, and CPython C-extension ABI,
then removes deployment-only files and builds a smaller interpreter. The
smallest runtime variant, `runtime-nano`, is 16.4 MiB installed and 3.5 MiB
compressed. The full CPython `test` build from the same `static-lean` pipeline is
242.3 MiB installed and 26.0 MiB compressed.

Use SnugPy when an agent sandbox or Linux service needs full CPython
compatibility. Use MicroPython or PocketPy when a small Python subset is enough.
Use Monty when the goal is a strict, low-latency sandbox with no ambient
filesystem or network.

**Status:** 0.1.0. `static-lean` on `linux-x86_64` passed the full CPython
3.14.9 regression suite and the `zerodep` tests with network access. The other
profiles remain experimental. GitHub Actions is the build, verification, and
release path. Native CI jobs also build `linux-arm64`, `macos-arm64`,
`macos-x86_64`, and `windows-x86_64`; those artifacts stay outside the release
selection until their workflows pass.

## At a glance

| Property | SnugPy 0.1.0 |
| --- | --- |
| Implementation | CPython 3.14.9 |
| Compatibility | Full CPython language and C-extension ABI |
| Smallest runtime | `runtime-nano`: 16.4 MiB installed, 3.5 MiB archive |
| Reduction from full CPython | 93.2% installed, 86.4% archive |
| Agent sandbox image | 31.95 MiB `scratch` image |
| Release target | `linux-x86_64` |
| Native build targets | `linux-arm64`, `macos-arm64`, `macos-x86_64`, `windows-x86_64` |

## How SnugPy compares

The comparison below uses the measured artifacts in this repository and builds
of the comparison projects on `linux-x86_64`. Sizes are not feature-normalized.

| Runtime | Approach | Compatibility | Deployment size | Main tradeoff |
| --- | --- | --- | --- | --- |
| CPython 3.14.9 (full `test` build) | Reference C implementation, packaged by SnugPy | Full CPython language, standard library, and C-extension ABI | 242.3 MiB installed / 26.0 MiB `tar.xz` (`test`) | Largest footprint |
| **SnugPy 0.1.0** | **CPython 3.14.9, trimmed and optimized** | **Full CPython language and C-extension ABI; runtime variants remove installer, headers, test, and UI files** | **16.4 MiB installed / 3.5 MiB `tar.xz` (`runtime-nano`); 31.95 MiB `scratch` image** | **Linux-x86_64 release target; native archives build on four additional targets; runtime variants have no pip or headers** |
| MicroPython 1.29.0 | Independent C implementation | Python 3.4 syntax with select later features; subset standard library | 0.82 MiB stripped Unix binary | Not full CPython; no CPython C-extension ABI |
| PocketPy 2.2.0 | Independent C11 implementation | Python 3 subset | 0.59 MiB stripped CLI | Game-scripting focus; not full CPython |
| Monty 1.7.0 | Independent Rust implementation | Partial Python 3.14 subset with a sandbox API | 34.7 MiB installed binary / 16.3 MiB wheel | No ambient filesystem or network; capabilities are supplied by the host |

Measurement basis: SnugPy and CPython numbers come from
`docs/version-matrix.md`; MicroPython 1.29.0 and PocketPy 2.2.0 were built from
tagged source on 2026-11-28; Monty 1.7.0 is the manylinux x86-64 runtime wheel
from PyPI. MicroPython and PocketPy are single stripped executables, while the
CPython and SnugPy figures are installed trees and compressed archives.

The compressed SnugPy archive is still 4.3 times the MicroPython binary and 6.0
times the PocketPy binary. That gap is the cost of shipping full CPython.
SnugPy's installed tree is 47% of the Monty 1.7.0 installed binary size, but
Monty provides VM-level resource limits and a sandbox that exposes only
host-provided capabilities.

## Why not use a smaller interpreter?

MicroPython and PocketPy achieve their size by implementing a Python subset with
their own standard-library and native-module APIs. Monty does the same for a
sandbox with host-provided capabilities. Those are the right choices when the
deployment does not need full CPython.

SnugPy keeps the CPython implementation. The runtime variants keep the core
standard library modules used by services and agents, including `ssl`,
`sqlite3`, `ctypes`, `json`, and `asyncio`. The `runtime` variants also keep
`site-packages`, so numpy, pandas, and other packages installed at image-build
time survive. Native extensions need a build for CPython 3.14 and the matching
external libraries at runtime.

The size reduction comes from removing files that deployment does not need:
tests, headers, `config-*`, static archives, `ensurepip`, pip, IDLE/Tk, docs,
`pydoc_data`, and in `runtime-nano`, `__pycache__`. It does not come from
reimplementing Python.

## What SnugPy is not

- It is not a new Python implementation. CPython remains the source of language
  semantics and the C-extension ABI.
- It is not a security sandbox by itself. `static-lean` is non-PIE; use a
  container or VM as the security boundary.
- It is not yet released beyond `linux-x86_64`. Native builds for Linux ARM64,
  macOS ARM64, macOS Intel, and Windows x86_64 are available as CI artifacts,
  not as approved release artifacts.
- It is not a package installer in runtime variants. `runtime` and
  `runtime-nano` keep preinstalled packages but remove pip and `ensurepip`.

## Install

The `snugpy` package on PyPI is the build and measurement tool, not the
interpreter runtime. Use a distribution archive or a Docker image for the
runtime.

### One-line install

The installer requires Python 3.10 or newer. It creates an isolated virtual
environment under `${XDG_DATA_HOME:-$HOME/.local/share}/snugpy` and links the
CLI at `${XDG_BIN_HOME:-$HOME/.local/bin}/snugpy`.

```bash
curl -fsSL https://raw.githubusercontent.com/Oaklight/snugpy/main/install.sh | bash
snugpy --version
```

Pin a PyPI version:

```bash
curl -fsSL https://raw.githubusercontent.com/Oaklight/snugpy/main/install.sh |
  SNUGPY_VERSION=0.1.0 bash
```

Choose another prefix or executable directory:

```bash
curl -fsSL https://raw.githubusercontent.com/Oaklight/snugpy/main/install.sh |
  SNUGPY_PREFIX="$HOME/.local/share/snugpy" \
  SNUGPY_BIN_DIR="$HOME/.local/bin" bash
```

The installer refuses to reuse an unmarked non-empty directory. It also refuses
to replace an unrelated `snugpy` executable. Set `SNUGPY_FORCE=1` for the
executable conflict. Set `SNUGPY_PYTHON` to choose the Python used to create the
venv. Rerun the same command to update the managed venv.

The installed CLI reads configuration bundled in the wheel and writes build
outputs under the current directory. Running from a clone uses that clone's
`configs/` instead.

### Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/Oaklight/snugpy/main/uninstall.sh | bash
```

For a custom prefix or executable directory, pass the same values to both
scripts:

```bash
curl -fsSL https://raw.githubusercontent.com/Oaklight/snugpy/main/uninstall.sh |
  SNUGPY_PREFIX="$HOME/.local/share/snugpy" \
  SNUGPY_BIN_DIR="$HOME/.local/bin" bash
```

The uninstaller removes only a venv with a valid `.snugpy-install` marker and a
symlink that points to that venv. It does not remove an unmarked directory. A
`pip` installation in a conda environment is removed with
`python -m pip uninstall snugpy`.

### Conda

PyPI installation is environment-independent. `python -m pip` installs into the
Python environment that is active, including a conda environment:

```bash
conda activate myenv
python -m pip install snugpy
```

The one-line installer detects `CONDA_PREFIX`, reports it, and leaves the conda
environment unchanged. Use the installer when `snugpy` should be available
outside conda environments. Use `python -m pip install snugpy` when it should be
part of one conda environment.

### Docker Hub

Runtime images are published at
[`oaklight/snugpy`](https://hub.docker.com/r/oaklight/snugpy). They are
`linux/amd64` only.

| Tag | Distribution | Base | Shell | pip |
| --- | --- | --- | --- | --- |
| `0.1.0`, `latest` | `runtime-nano` | `scratch` | no | no |
| `0.1.0-runtime` | `runtime` | `scratch` | no | no |
| `0.1.0-distroless` | `runtime` | distroless `cc-debian12` | no | no |
| `0.1.0-debian` | `runtime` | Debian 12 slim | yes | no |

`runtime` keeps preinstalled `site-packages` and precompiled bytecode.
`runtime-nano` removes precompiled bytecode, so it starts smaller but compiles
modules on first import. The scratch images run as UID 65532 and contain no
shell or package manager.

```bash
docker run --rm --entrypoint python3.14 oaklight/snugpy:0.1.0 \
  -c 'import ssl, sqlite3; print("runtime-ok")'

docker run --rm --entrypoint python3.14 oaklight/snugpy:0.1.0-debian \
  -c 'import ssl, sqlite3; print("runtime-ok")'
```

The release workflow builds, smoke-tests, and pushes these tags. It does not
publish multi-architecture manifests.

## Build from source

The toolchain is a conda-forge environment. It contains Python 3.12, GCC 16,
Clang 23, `lld`, binutils, `patchelf`, `hyperfine`, GNU `time`, ShellCheck,
`go-shfmt`, and the libraries needed by CPython's optional extensions.

```bash
git clone git@github.com:Oaklight/snugpy.git
cd snugpy

# New prefixes are created from the exact lock file when it exists.
./scripts/setup-conda.sh "$HOME/ml_lab/envs/snugpy"

source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$HOME/ml_lab/envs/snugpy"

./scripts/check-deps.sh
./scripts/fetch.sh 3.14 --zerodep
./scripts/build.sh 3.14 baseline linux-x86_64
./scripts/test.sh 3.14 baseline linux-x86_64 --smoke
./scripts/package.sh 3.14 baseline linux-x86_64
./scripts/measure.sh 3.14 baseline linux-x86_64 --runs 10
./scripts/report.sh
```

`scripts/setup-conda.sh` prefers `conda-linux-64.lock` for a new prefix. It
falls back to `environment.yml`, and it updates an existing prefix from
`environment.yml`. Set `SNUGPY_CONDA_USE_LOCK=0` to force the YAML path.

`scripts/package.sh` copies the install prefix once, strips debug symbols from
ELF binaries, relocatable objects, and static archives in the staging tree, and
writes deterministic `tar.xz` archives for every configured distribution. The
original `out/` prefix keeps its symbols for debugging. Run packaging before
measurement so the report can record archive and stripped installation sizes.
Use `--distribution runtime-nano` to build one variant while iterating; repeated
flags select several.

To use the environment without activating it, which is how CI runs builds:

```bash
export SNUGPY_CONDA_PREFIX="$HOME/ml_lab/envs/snugpy"
export PATH="$SNUGPY_CONDA_PREFIX/bin:$PATH"
```

`SNUGPY_CONDA_PREFIX` takes precedence over `CONDA_PREFIX`. Conda activation
exports optimized and hardened `CFLAGS`, `CPPFLAGS`, and `LDFLAGS`; SnugPy
discards those values and supplies only the selected profile flags plus the
conda include and library paths. This keeps `baseline` and the size profiles
comparable.

Regenerate the lock after an intentional environment change:

```bash
./scripts/lock-conda.sh "$HOME/ml_lab/envs/snugpy"
```

## Profiles

| Profile | Compiler | Configuration | Purpose |
| --- | --- | --- | --- |
| `baseline` | GCC | upstream default optimization, shared libpython | Reference build |
| `size` | GCC `-Os` | shared libpython | Size-oriented code generation |
| `lto` | GCC `-Os` | `--with-lto`, shared libpython | Size plus link-time optimization |
| `static` | GCC `-Os` | `--disable-shared` | Static libpython linkage; not a fully static system binary |
| `clang-oz` | Clang `-Oz` | shared libpython | Aggressive size experiment |
| `lean` | Clang `-Oz` | shared libpython, `--without-doc-strings`, `--gc-sections` | Smallest shared experiment; removes C docstrings and unwind tables |
| `static-lean` | Clang `-Oz` | `--disable-shared`, `--without-doc-strings`, non-PIE, safe LLD ICF, Debian 12 system libraries | Smallest deployment core; non-PIE link, hidden symbols, no unwind tables, section GC |

`static-lean` links the interpreter as a non-PIE executable. This removes
dynamic relocations and shrinks the core, but it disables address-space layout
randomization for the interpreter process. Use it only where container or VM
isolation is the security boundary. It is also the only profile linked against
Debian 12 system libraries instead of conda-forge libraries.

The consolidated profile and distribution sizes are in
`docs/version-matrix.md`. External library and image details are in
`docs/runtime-libraries.md`.

Each profile has a separate work tree, install prefix, logs, and result
directory. A profile is release-eligible only after full CPython regression
tests, zerodep tests, ABI checks, stdlib inventory checks, and measurements
pass. Measurement reports a Pareto frontier; the smallest build is not selected
automatically.

## Distributions

Every profile produces a complete install prefix. Packaging derives seven
archives from one stripped staging tree, so the profile result and all variants
stay consistent.

| Distribution | Excludes | Smoke imports | Intended use |
| --- | --- | --- | --- |
| `headless` (default) | tests, test-only extensions, IDLE, Tk, `config-*/libpython*.a`, `config-*/python.o` | `ssl`, `sqlite3`, `ctypes` | Servers and general containers |
| `headed` | tests, test-only extensions, development archives and objects | `ssl`, `sqlite3`, `ctypes`, `tkinter` | Workstations that need Tk/IDLE |
| `test` | nothing | `ssl`, `sqlite3`, `ctypes`, `test` | Full CPython comparison and compatibility testing |
| `micro` | installer, docs, tests, headers, development files, Tk, curses, dbm, readline | `ssl`, `sqlite3`, `ctypes`, `json`, `asyncio` | Stdlib-only agent sandboxes |
| `nano` | `micro` plus `__pycache__` | `ssl`, `sqlite3`, `ctypes`, `json`, `asyncio` | Smallest stdlib-only image; imports compile from source |
| `runtime` | `micro` minus installer, keeps `site-packages` | `ssl`, `sqlite3`, `ctypes`, `json`, `asyncio` | Agent sandboxes with preinstalled packages |
| `runtime-nano` | `runtime` plus no `__pycache__` | `ssl`, `sqlite3`, `ctypes`, `json`, `asyncio` | Smallest agent sandbox with preinstalled packages |

`headless`, `headed`, and `test` keep `include/`, `config-*/Makefile`,
`ensurepip`, `venv`, and `site-packages`, so `pip install cffi` and `venv`
work. `micro`, `nano`, `runtime`, and `runtime-nano` are runtime-only: no pip,
no venv, no headers, no build scripts, no `pydoc_data`, and no test or
terminal-UI extension modules. `headless` and `headed` drop only the test-only
extensions (`_test*`, `_ctypes_test`, `xxlimited*`, `xxsubtype`, `_xxtestfuzz`)
and keep curses and readline. `runtime` keeps `site-packages`, so packages
installed at image-build time (numpy, pandas, and others) survive; only `pip`,
`pip-*.dist-info`, `ensurepip`, and `bin/pip*` are removed. `nano` and
`runtime-nano` also drop precompiled bytecode, so each process compiles modules
on first import; expect a small startup cost when the runtime filesystem is
read-only.

Three runtime Dockerfiles are provided:

- `docker/runtime.Dockerfile`: Debian slim, with a shell and apt.
- `docker/runtime-distroless.Dockerfile`: distroless `cc-debian12`, no shell.
- `docker/runtime-scratch.Dockerfile`: `scratch` root filesystem with only the
  required sonames, CA certificates, tzdata, NSS files, and runtime directories.

The scratch image with `runtime-nano` measured 33,500,721 bytes in CI, about
32 MiB. It keeps the standard library, HTTPS, SQLite, `ctypes`, compression
modules, time zones, and `site-packages`. Edit `configs/distributions.toml` to
change the variants; the default distribution is `headless`.

Variant names are appended to archive filenames, for example
`snugpy-0.1.0-cpython3.14.9-linux-x86_64-static-lean-runtime-nano.tar.xz`. The
package metadata keeps one entry per variant. The report matrix uses the default
distribution and lists every variant's installed and archive size separately.

## Commands

| Command | Action |
| --- | --- |
| `make conda` | Create or update the conda toolchain |
| `make lock` | Write `conda-linux-64.lock` from the current prefix |
| `make check` | Unit tests, `compileall`, ShellCheck, and `shfmt -d` |
| `make fetch` | Verify and extract pinned CPython and zerodep sources |
| `make build PROFILE=size` | Build one isolated profile |
| `make test PROFILE=size` | Run smoke and ABI gates |
| `make test-full PROFILE=size` | Run full CPython and zerodep gates |
| `make measure PROFILE=size RUNS=20` | Collect size, startup, RSS, and workload data |
| `make package PROFILE=size` | Create stripped archives for every distribution and smoke-test them |
| `make package PROFILE=size DISTRIBUTION=runtime-nano` | Create and test one distribution |
| `make report` | Write `results/summary.csv` and `results/report.md` |
| `make matrix` | Run all seven profiles without stopping on unrelated failures |
| `make images PROFILE=static-lean IMAGE_TAG=0.1.0` | Build the four runtime images locally |
| `make publish-images PROFILE=static-lean IMAGE_TAG=0.1.0` | Build, smoke-test, and push the images and `latest` |
| `make clean` | Remove `work/`, `out/`, and `dist/` |

The direct scripts accept `VERSION`, `TARGET`, and `PROFILE` as positional
arguments. Use `python -m snugpy_build.cli list` to see the configured values.

Native build cells use the same command shape:

| Target | Runner | Profile | Backend |
| --- | --- | --- | --- |
| `linux-x86_64` | `ubuntu-24.04` / Debian 12 container | `static-lean` | `configure` |
| `linux-arm64` | `ubuntu-24.04-arm` / Debian 12 container | `static-lean` | `configure` |
| `macos-arm64` | `macos-15` | `macos-static` | `configure` |
| `macos-x86_64` | `macos-15-intel` | `macos-static` | `configure` |
| `windows-x86_64` | `windows-2025` | `windows-release` | `pcbuild` |

```bash
./scripts/build.sh 3.14 static-lean linux-arm64 --jobs "$(nproc)"
./scripts/build.sh 3.14 macos-static macos-arm64 --jobs "$(sysctl -n hw.logicalcpu)"
python -m snugpy_build.cli build 3.14 windows-release windows-x86_64
```

Docker can produce Linux artifacts for both architectures. macOS needs Apple's
SDK and native code signing tools, and Windows uses MSVC `PCbuild`; neither is a
supported Docker build target for this project.

## Portability and limits

- CPython `3.14.9` is the only build target. It is pinned by tag, commit, and
  source SHA256.
- `linux-x86_64` is the only release-approved target. Native CI builds the
  other four targets but does not approve them for release.
- macOS archives currently link Homebrew libraries by absolute path. Treat them
  as runner-compatible CI artifacts until dependency bundling is added.
- Windows artifacts are `tar.xz` layouts built with MSVC, not `.exe` installers.
- `static-lean` is a non-PIE executable. Container or VM isolation must be the
  security boundary.
- Distribution archives do not bundle external C libraries. Provide the
  documented sonames at runtime, or use one of the images.
- Runtime variants have no pip, `ensurepip`, headers, or build tools.
- `runtime-nano` compiles standard-library modules on first import. Use
  `runtime` when startup latency matters more than image size.

The conda-forge `gdbm` package omits its ndbm compatibility library. The conda
setup step builds `libgdbm_compat` from pinned GDBM `1.18` source so both
`_dbm` and `_gdbm` are available. `tests/smoke.py` verifies an ndbm round trip.

Native extensions in the conda-linked profiles link conda-forge libraries such
as OpenSSL, SQLite, and `libffi`. `static-lean` extensions link the Debian
sonames instead. In both cases the archive does not bundle those libraries. Run
an extracted artifact with the matching library set available, or bundle the
required libraries before redistribution.

The actual symbol requirements of each artifact must be checked with
`scripts/check-abi.sh` or `objdump -T` before any portability or release claim.
These archives are not general-purpose Linux distributions.

## Version policy

The compatibility floor for the SnugPy tooling and for `zerodep` is Python 3.10.
That does **not** mean SnugPy must build or distribute CPython 3.10, 3.11, 3.12,
and 3.13. CPython has a different ABI in each minor release. The initial target
is one pinned CPython 3.14 maintenance release. A future version is added as its
own pinned source, build matrix, and release decision; compiled objects,
prefixes, and configuration are never shared between versions.

## Layout

```text
configs/        immutable versions, targets, profiles, release decisions
snugpy_build/     CLI, source verification, build, validation, metrics, packaging
scripts/        shell entry points and conda environment setup
tests/          unit tests, runtime smoke test, C ABI smoke module
benchmarks/     CPU and I/O workloads
patches/        exceptional common and version-specific patches
sources/        verified upstream source trees (ignored)
work/           per-cell generated build trees (ignored)
out/            per-cell install prefixes (ignored)
dist/           distribution archives (ignored)
results/        metadata per cell; summary.csv and report.md are tracked
install.sh      one-line installer for the PyPI CLI
uninstall.sh    uninstaller for the managed venv
```

## CI

`.github/workflows/ci.yml` runs the unit checks, then builds the six
conda-linked profiles as independent matrix jobs with `fail-fast: false`. Each
job creates its conda environment from `conda-linux-64.lock`, runs fetch, build,
smoke tests, packaging, and measurement, and uploads its JSON results and
archives. A separate `static-lean` job runs inside `debian:bookworm`, links
Debian system libraries, and runs the ABI gate. A dependent job measures the
Debian slim, distroless, scratch `runtime`, and scratch `runtime-nano` images.
An aggregate job downloads all profile results and regenerates the report.

`.github/workflows/native-builds.yml` adds native platform builds. It uses an
ARM64 Ubuntu runner with a Debian 12 container, Apple Silicon and Intel macOS
runners, and a Windows runner. The Windows job uses CPython's `PCbuild` and
`PC/layout` tools; it does not use MinGW or a Linux cross-compiler. Docker on
`ts-build02` is limited to Linux and is not part of this matrix.

`.github/workflows/benchmark.yml` is the manual full-regression and repeated
measurement path. It runs the full CPython suite and zerodep tests with network
access, then packages and measures one selected profile.

`.github/workflows/release.yml` is the release path. It verifies the source
version and the approved release profile, builds and fully tests `static-lean`,
publishes the Python package to PyPI, pushes the Docker Hub images, and creates
the GitHub Release with archives, checksums, and the report. Set
`DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, and `PYPI_API_TOKEN` as repository
secrets before running it.

## Documentation

- `README_en.md`: English README
- `README_zh.md`: Chinese README
- `CHANGELOG.md`: release history and known limitations
- `docs/version-matrix.md`: Python versions, profiles, distributions, and sizes
- `docs/runtime-libraries.md`: ABI gate, library inventory, and image sizes

## License

SnugPy is licensed under the MIT License. See `LICENSE`.

A distribution archive also contains CPython-derived files. CPython keeps its
own PSF License Agreement, which is included in every archive at
`licenses/CPython-PSF-LICENSE.txt`. Third-party components are listed in
`THIRD_PARTY_LICENSES.md`.
