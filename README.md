# SnugPy

**Whole Python. Small footprint.**

SnugPy builds compact, deployable Python runtimes and measures each candidate
against a full CPython baseline. It starts from pinned upstream CPython rather
than reimplementing the language, so compatibility comes first. Every profile
build preserves the standard library, `ensurepip`, `venv`, `idlelib`, `tkinter`,
`test`, and optional native extensions. Packaging then derives seven deployable
variants from the same stripped tree: `headless`, `headed`, `test`, `micro`,
`nano`, `runtime`, and `runtime-nano`. The `micro`, `nano`, `runtime`, and
`runtime-nano` variants drop the installer, headers, docs, and development files
for runtime-only sandboxes.

**Status:** experimental. The build and measurement framework is implemented,
but no release profile has been approved. GitHub Actions is the build and
verification path.

## Origin

SnugPy started from the same observation as MicroPython and PocketPy: most
deployments do not need the full CPython source tree or every development
artifact. Unlike those projects, SnugPy starts from CPython to keep full
compatibility, then removes deployment-irrelevant parts. Future work may modify
the interpreter more aggressively; the name does not promise an unmodified
CPython.

## Version policy

The compatibility floor for the SnugPy tooling and for `zerodep` is Python 3.10.
That does **not** mean SnugPy must build or distribute CPython 3.10, 3.11, 3.12,
and 3.13. CPython has a different ABI in each minor release. The initial target
is one pinned CPython 3.14 maintenance release. A future version is added as its
own pinned source, build matrix, and release decision; compiled objects,
prefixes, and configuration are never shared between versions.

## Install

The `snugpy` package on PyPI is the build and measurement tool, not the
interpreter runtime. Use a distribution archive or a Docker image for the
runtime.

```bash
python -m pip install snugpy
snugpy list
```

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

## Quick start

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
Use `--distribution headless` to build one variant while iterating; repeated
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
| `test` | nothing | `ssl`, `sqlite3`, `ctypes`, `test` | Compatibility testing and redistribution analysis |
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

The scratch image with `runtime-nano` measured 33,484,721 bytes in CI, about
32 MiB. It keeps the standard library, HTTPS, SQLite, `ctypes`, compression
modules, time zones, and `site-packages`. Edit `configs/distributions.toml` to
change the variants; the default distribution is `headless`.

Variant names are appended to archive filenames, for example
`snugpy-0.1.0-cpython3.14.9-linux-x86_64-baseline-headless.tar.xz`. The package
metadata keeps one entry per variant. The report matrix uses the default
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
| `make package PROFILE=size DISTRIBUTION=headless` | Create and test one distribution |
| `make report` | Write `results/summary.csv` and `results/report.md` |
| `make matrix` | Run all seven profiles without stopping on unrelated failures |
| `make clean` | Remove `work/`, `out/`, and `dist/` |

The direct scripts accept `VERSION`, `TARGET`, and `PROFILE` as positional
arguments. Use `python -m snugpy_build.cli list` to see the configured values.

## Pins

- CPython `3.14.9`, tag `v3.14.9`, commit
  `ead82c07db1f111d613926ed1b6667411d768125`, SHA256
  `e02d9ac21cebda6e46435369744a92c65cc7cd8669697694122cf97ffacd1e53`
- zerodep `v2026.11.20`, commit
  `9f872e8d652272c34600b9fda6448fe4fd4436c3`
- Target `linux-x86_64`
- conda-forge sysroot glibc `2.34` for the conda-linked profiles
- Debian 12 system libraries for `static-lean`; measured `GLIBC_2.35`,
  allowed `GLIBC_2.36`, OpenSSL `3.0`
- Toolchain: Python `3.12`, GCC `16`, Clang `23`, `lld`, GNU binutils

The conda sysroot is 2.34 even though the CI runner is Ubuntu 24.04.
`static-lean` does not use that sysroot; it builds in `debian:bookworm` and
links Debian system libraries. The actual symbol requirements of each artifact
must be checked with `scripts/check-abi.sh` or `objdump -T` before any
portability or release claim. These archives are not general-purpose Linux
distributions.

Native extensions in the conda-linked profiles link conda-forge libraries such
as OpenSSL, SQLite, and `libffi`. `static-lean` extensions link the Debian
sonames instead. In both cases the archive does not bundle those libraries. Run
an extracted artifact with the matching library set available, or bundle the
required libraries before redistribution.

The conda-forge `gdbm` package omits its ndbm compatibility library. The conda
setup step builds `libgdbm_compat` from pinned GDBM `1.18` source so both
`_dbm` and `_gdbm` are available. `tests/smoke.py` verifies an ndbm round trip.

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

- `CHANGELOG.md`: release history and known limitations
- `docs/version-matrix.md`: Python versions, profiles, distributions, and sizes
- `docs/runtime-libraries.md`: ABI gate, library inventory, and image sizes

## License

SnugPy is licensed under the MIT License. See `LICENSE`.

A distribution archive also contains CPython-derived files. CPython keeps its
own PSF License Agreement, which is included in every archive at
`licenses/CPython-PSF-LICENSE.txt`. Third-party components are listed in
`THIRD_PARTY_LICENSES.md`.
