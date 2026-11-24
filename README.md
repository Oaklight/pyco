# Pyco

Pyco builds compact, full-compatibility CPython distributions and measures each
candidate against a baseline. It is build orchestration around pinned upstream
CPython, not a CPython fork. The standard library, `ensurepip`, `venv`,
`idlelib`, `tkinter`, `test`, and optional native extensions are preserved.
Nothing is pruned to manufacture a smaller number.

**Status:** experimental. The build and measurement framework is implemented,
but no release profile has been approved. No CPython build has been verified in
the development checkout yet; GitHub Actions is the build and verification path.

## Version policy

The compatibility floor for the Pyco tooling and for `zerodep` is Python 3.10.
That does **not** mean Pyco must build or distribute CPython 3.10, 3.11, 3.12,
and 3.13. CPython has a different ABI in each minor release. The initial target
is one pinned CPython 3.14 maintenance release. A future version is added as its
own pinned source, build matrix, and release decision; compiled objects,
prefixes, and configuration are never shared between versions.

## Quick start

The toolchain is a conda-forge environment. It contains Python 3.12, GCC 16,
Clang 23, `lld`, binutils, `patchelf`, `hyperfine`, GNU `time`, ShellCheck,
`go-shfmt`, and the libraries needed by CPython's optional extensions.

```bash
git clone git@github.com:Oaklight/pyco.git
cd pyco

# New prefixes are created from the exact lock file when it exists.
./scripts/setup-conda.sh "$HOME/ml_lab/envs/pyco"

source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$HOME/ml_lab/envs/pyco"

./scripts/check-deps.sh
./scripts/fetch.sh 3.14 --zerodep
./scripts/build.sh 3.14 baseline linux-x86_64
./scripts/test.sh 3.14 baseline linux-x86_64 --smoke
./scripts/measure.sh 3.14 baseline linux-x86_64 --runs 10
./scripts/package.sh 3.14 baseline linux-x86_64
./scripts/report.sh
```

`scripts/setup-conda.sh` prefers `conda-linux-64.lock` for a new prefix. It
falls back to `environment.yml`, and it updates an existing prefix from
`environment.yml`. Set `PYCO_CONDA_USE_LOCK=0` to force the YAML path.

To use the environment without activating it, which is how CI runs builds:

```bash
export PYCO_CONDA_PREFIX="$HOME/ml_lab/envs/pyco"
export PATH="$PYCO_CONDA_PREFIX/bin:$PATH"
```

`PYCO_CONDA_PREFIX` takes precedence over `CONDA_PREFIX`. Conda activation
exports optimized and hardened `CFLAGS`, `CPPFLAGS`, and `LDFLAGS`; Pyco
discards those values and supplies only the selected profile flags plus the
conda include and library paths. This keeps `baseline` and the size profiles
comparable.

Regenerate the lock after an intentional environment change:

```bash
./scripts/lock-conda.sh "$HOME/ml_lab/envs/pyco"
```

## Profiles

| Profile | Compiler | Configuration | Purpose |
| --- | --- | --- | --- |
| `baseline` | GCC | upstream default optimization, shared libpython | Reference build |
| `size` | GCC `-Os` | shared libpython | Size-oriented code generation |
| `lto` | GCC `-Os` | `--with-lto`, shared libpython | Size plus link-time optimization |
| `static` | GCC `-Os` | `--disable-shared` | Static libpython linkage; not a fully static system binary |
| `clang-oz` | Clang `-Oz` | shared libpython | Aggressive size experiment |

Each profile has a separate work tree, install prefix, logs, and result
directory. A profile is release-eligible only after full CPython regression
tests, zerodep tests, ABI checks, stdlib inventory checks, and measurements
pass. Measurement reports a Pareto frontier; the smallest build is not selected
automatically.

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
| `make package PROFILE=size` | Create and smoke-test a deterministic archive |
| `make report` | Write `results/summary.csv` and `results/report.md` |
| `make matrix` | Run all five profiles without stopping on unrelated failures |
| `make clean` | Remove `work/`, `out/`, and `dist/` |

The direct scripts accept `VERSION`, `TARGET`, and `PROFILE` as positional
arguments. Use `python -m pyco_build.cli list` to see the configured values.

## Pins

- CPython `3.14.9`, tag `v3.14.9`, commit
  `ead82c07db1f111d613926ed1b6667411d768125`, SHA256
  `e02d9ac21cebda6e46435369744a92c65cc7cd8669697694122cf97ffacd1e53`
- zerodep `v2026.11.20`, commit
  `9f872e8d652272c34600b9fda6448fe4fd4436c3`
- Target `linux-x86_64`, nominal conda-forge sysroot glibc `2.34`
- Toolchain: Python `3.12`, GCC `16`, Clang `23`, `lld`, GNU binutils

The conda sysroot is 2.34 even though the CI runner is Ubuntu 24.04. The actual
symbol requirements of each artifact must be checked with `objdump -T` before
any portability or release claim. These archives are not general-purpose Linux
distributions.

## Layout

```text
configs/        immutable versions, targets, profiles, release decisions
pyco_build/     CLI, source verification, build, validation, metrics, packaging
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

`.github/workflows/ci.yml` runs the unit checks, then builds the five profiles
as independent matrix jobs with `fail-fast: false`. Each job creates its conda
environment from `conda-linux-64.lock`, runs fetch, build, smoke tests,
measurement, and packaging, and uploads its JSON results and archive. An
aggregate job downloads all profile results and regenerates the report.

`.github/workflows/benchmark.yml` is the manual full-regression and repeated
measurement path. It runs the full CPython suite and zerodep tests with network
access, then measures and packages one selected profile.

No release workflow is enabled yet. Release selection requires human approval in
`configs/release-selection.toml` after the compatibility and performance gates
pass.

## License

No license has been selected. Add a license before distributing or accepting
external contributions.
