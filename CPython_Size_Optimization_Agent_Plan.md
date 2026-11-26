# SnugPy — Codex Implementation Plan

**Status:** Implementation specification · **Updated:** 2026-11-25  
**Project:** SnugPy, a compact, full-compatibility CPython distribution  
**Primary target:** Linux x86-64, CPython 3.14  
**Next targets:** CPython 3.15 and Linux ARM64  
**Reference application:** `https://github.com/Oaklight/zerodep`

> Naming: **SnugPy** is the display name. `snugpy` is the PyPI package, CLI,
> GitHub organization, and repository name. The build system must not depend on
> the brand name.

## 0. Executive decisions — read first

1. **One SnugPy repository, one main branch, one shared build/optimization/test framework.** Do **not** maintain a separate SnugPy codebase or permanent CPython fork for every Python release.
2. **Each CPython version has its own pristine upstream source checkout.** Download/verify pinned 3.14.x and (when enabled) 3.15.x sources. Build each version repeatedly under different profiles. Never share compiled objects, install prefixes, or generated configuration between builds.
3. **Source patches are exceptional.** Common patches only when proven applicable; otherwise use `patches/3.14/` and `patches/3.15/`. Prefer upstream-compatible build flags and external tooling over interpreter modifications.
4. **Preserve the complete, unmodified upstream standard library** (pure-Python files, data, `ensurepip`, `venv`, `idlelib`, `tkinter`, `test`, and native extensions). Do not prune or compress the stdlib as a size optimization. A missing optional extension due to build dependencies is a failed build, not a success.
5. **Preserve CPython behavior, C extension ABI, and native extension loading.** No VM rewrite, feature removal, altered object layouts, or deliberate compatibility breaks.
6. **Measure both interpreter core and total distribution.** Core = stripped `python` ELF + `libpython` ELF when present, deduplicating symlinks/hardlinks; also report stdlib, extensions, required external libraries, and full installed bytes. A tiny shared-library launcher is not a tiny Python runtime.
7. **Separate exploration from release.** CI runs the matrix; release builds only manually approved, compatible configurations. Never automatically choose a winner based solely on size.
8. **Builds must work locally using the same scripts as CI.** GitHub Actions is orchestration, not the implementation of the build system.

## 1. Scope and version policy

- Initial proof of concept: **one pinned CPython 3.14 maintenance release**, Linux x86-64, five profiles. Resolve the exact release tag and immutable commit/checksum during implementation; do not use a floating branch or silently update it.
- Expand to a pinned CPython 3.15 release only after the 3.14 pipeline passes. Do not assume any version is available without checking the upstream release source.
- Python `Requires-Python >=3.10` for zerodep does **not** require distributing CPython 3.10. It means the package claims compatibility beginning at 3.10; test that the actual code runs on 3.14/3.15. Older runtime builds are optional, not a project goal.
- Each interpreter follows the semantics and ABI of its own CPython version; do not attempt to emulate Python 3.10 inside CPython 3.14.
- Initial platform: Ubuntu 24.04 GitHub-hosted x86-64 for experimental CI. Document glibc and external dependency constraints. These artifacts are **not** automatically portable Linux distributions.
- Future ARM64: use native ARM64 runners where available or an explicit documented cross-build strategy; do not label an x86-64 build as ARM64.

## 2. Repository layout

```text
snugpy/
├── .github/workflows/
│   ├── ci.yml                 # PR/push: fast smoke matrix
│   ├── benchmark.yml          # manual/scheduled: full matrix and measurements
│   ├── release.yml            # tagged/manual: approved builds only
│   └── upstream.yml           # scheduled update proposals, no auto-release
├── configs/
│   ├── versions.toml          # immutable CPython tags, URLs, SHA256/commits
│   ├── targets.toml           # platform and toolchain requirements
│   ├── profiles.toml          # shared build profile definitions
│   └── release-selection.toml # reviewed profile selection per version/arch
├── snugpy_build/                # optional Python CLI/library for orchestration
│   ├── source.py
│   ├── profiles.py
│   ├── build.py
│   ├── validate.py
│   ├── metrics.py
│   └── report.py
├── scripts/
│   ├── fetch.sh
│   ├── build.sh
│   ├── test.sh
│   ├── measure.sh
│   ├── package.sh
│   └── check-deps.sh
├── patches/
│   ├── common/                # only genuinely version-independent patches
│   ├── 3.14/
│   └── 3.15/
├── tests/
│   ├── test_build_system.py
│   ├── abi_smoke/
│   └── smoke.py
├── benchmarks/
│   └── workloads/
├── sources/                   # gitignored: immutable extracted source trees
├── work/                      # gitignored: per-build generated workdirs
├── out/                       # gitignored: separate install prefixes
├── dist/                      # gitignored: packaged artifacts
├── results/                   # machine-readable metrics; curated reports
├── Makefile
├── README.md
└── LICENSE
```

Do not commit vendored CPython source. Cache downloaded **verified** source archives; extraction must be immutable and not contaminated by generated files. If patches are needed, copy the source into a per-build working tree or apply patches to a separate worktree; never patch the pristine shared source in place.

## 3. Build matrix

### Initial five profiles

| Profile | Compiler / configuration | What it tests |
|---|---|---|
| `baseline` | GCC, upstream default optimization, `--enable-shared` | Reference build |
| `size` | GCC `-Os`, `--enable-shared` | Size-oriented code generation |
| `lto` | GCC `-Os`, `--with-lto`, `--enable-shared` | Size optimization plus link-time optimization |
| `static` | GCC `-Os`, `--disable-shared` | Static `libpython` linkage into executable; **not** a fully static system binary |
| `clang-oz` | Clang `-Oz`, `--enable-shared` | Aggressive size-oriented code generation |

All five must use the **same pinned source revision, stdlib inventory, toolchain environment (except compiler differences), dependencies, and validation** within a given Python version/architecture. Record the *effective* compiler/linker flags from build logs; CPython's Makefile can add or override flags. Use `OPT`/`CFLAGS_NODIST` or equivalent only after verifying behavior for that CPython release.

### Optional follow-up experiments

- `size-lto-static`: `-Os` + LTO + `--disable-shared`.
- `gc-sections`: `-ffunction-sections -fdata-sections` + linker `--gc-sections`, with extension/ABI regression checks.
- `clang-oz-lto`: Clang + LTO with an explicitly pinned compatible linker.
- PGO, allocator changes, alternative linkers: **separate exploratory profiles**, never assumed to save space.
- Keep **stripping as a measurement/package dimension**, not a hidden difference between profiles: collect pre-strip and post-strip bytes for every profile; strip copies of ELF objects, verify afterward, and preserve debug artifacts separately if needed.

### Matrix progression

1. `3.14 × 5 profiles × linux-x86_64` = **5 independent builds**.
2. `3.14,3.15 × 5 profiles × linux-x86_64` = **10 builds**.
3. `3.14,3.15 × 5 profiles × linux-x86_64,linux-aarch64` = **20 builds**.

Each job runs `fetch → prepare isolated source → configure → build → install → validate → measure → package`. A failure in one matrix cell should not cancel unrelated cells (`fail-fast: false`).

## 4. Local command-line contract

Implement these commands as shell wrappers first, or as a small Python CLI if it simplifies testing. They must be functional, not merely documented examples:

```bash
./scripts/fetch.sh 3.14
./scripts/build.sh 3.14 size linux-x86_64
./scripts/test.sh 3.14 size linux-x86_64
./scripts/measure.sh 3.14 size linux-x86_64
./scripts/package.sh 3.14 size linux-x86_64

# Optional ergonomic facade:
snugpy build --python 3.14 --profile size --target linux-x86_64
snugpy benchmark --python 3.14 --profile all --target linux-x86_64
```

Canonical layout:

```text
sources/cpython-<exact-tag>/                # pristine and immutable
work/<exact-tag>/<target>/<profile>/src/   # patched working source if needed
work/<exact-tag>/<target>/<profile>/build/ # out-of-tree build
out/<exact-tag>/<target>/<profile>/        # installed runtime
results/<exact-tag>/<target>/<profile>/    # metrics and logs
dist/snugpy-<release>-cpython<version>-<target>-<profile>.tar.xz
```

Use **absolute source paths** for configure, ensure `make` is run from the build directory, and ensure the installation prefix is unique. Run the newly built Python explicitly; never accidentally test `/usr/bin/python3`. Handle `LD_LIBRARY_PATH` or rpath correctly for `--enable-shared`, and verify execution after packaging/extraction in a clean location. Make scripts idempotent or fail with a clear error if a directory is dirty. Fail fast on missing tools and required native-extension dependencies.

## 5. Source acquisition, trust, and reproducibility

- Pin exact upstream CPython source tarball URL and SHA256 (or signed Git tag plus immutable commit); verify before extraction.
- Pin exact `oaklight/zerodep` commit, record its declared Python support and actual test command. Never edit zerodep source to force passing tests.
- Record compiler, linker, `make`, libc, kernel, CPU architecture, OpenSSL, SQLite, zlib, libffi, ncurses, Tcl/Tk, and relevant development-library versions.
- Provide a pinned container image or documented toolchain setup for repeatable Linux builds. GitHub-hosted runner labels alone are not sufficient for bit-for-bit reproducibility.
- Fix locale, timezone, `SOURCE_DATE_EPOCH` where appropriate, deterministic archive order/mtime, and path normalization. **Do not claim bit-for-bit reproducibility until independently verified.**
- Cache source archives and build dependencies, not mutable build outputs across incompatible profiles. Cache keys must include CPython tag, toolchain identity, target, profile, and patches.

## 6. Standard library completeness, distributions, and ABI contract

Every profile install prefix must retain all upstream stdlib Python files, data, tests, scripts, `ensurepip` wheels, and native extensions. Preserve `venv`, `idlelib`, `tkinter`, and platform-applicable optional extensions. Install all necessary build dependencies; compare the native-extension inventory to a baseline built in the same environment. Do not delete `__pycache__` or stdlib components to manufacture size improvements. This complete prefix is the compatibility baseline and the source of the `test` distribution.

Packaging derives deployment variants from the complete prefix. Variants are explicit output transformations. They must not change profile measurements or compatibility claims:

- `headless`: runtime for servers and containers. Excludes the CPython test suite, `idlelib`, `tkinter`, and development archives (`libpython*.a`, `python.o`). Keeps headers, `config-*/Makefile`, `ensurepip`, `venv`, native extensions, and `site-packages`.
- `headed`: adds Tk and IDLE for workstation use, but still excludes the test suite and development archives.
- `test`: no exclusions. Used for compatibility testing and redistribution analysis.

Declare variants in `configs/distributions.toml`. For every archive, record the exclude patterns, installed bytes, archive bytes, SHA256, and a smoke import result. Report variant sizes separately from the profile's installed size and interpreter core size. Do not present a pruned download as a smaller interpreter.

Implement validation of:

1. Stdlib **source/data inventory and hashes** compared with baseline (account for documented version-specific generated files and paths). Compare **within** a CPython version, not across versions.
2. Native-extension module inventory, loading, and required dynamic symbols; native extension bytes may differ between profiles.
3. `ctypes`, `ssl`, `sqlite3`, `bz2`, `lzma`, `readline`, `curses`, `_tkinter`, `multiprocessing`, `subprocess`, `asyncio`, `socket`, `venv`, `ensurepip`.
4. A compiled third-party-style C extension built against the produced headers and imported by the produced interpreter; `ctypes.CDLL` smoke test.
5. CPython regression tests; compare fail/skip outcomes with the same-version baseline, and investigate **every new failure**.
6. Zerodep's own tests and representative entry points. Separate tests needing internet, credentials, external services, or privileges; never silently skip them.
7. Import and execute from an **extracted release tarball** in a clean location, not only from the build tree.

A profile is release-eligible only if its compatibility and completeness gates pass. If baseline itself has environment-dependent failures, document them and compare deltas rather than declaring unconditional success.

## 7. Measurements and winner selection

For each build capture machine-readable JSON and summary CSV with:

- `cpython_version`, `cpython_tag`, `cpython_commit_or_sha256`, `snugpy_commit`, `zerodep_commit`, `target`, `profile`, `toolchain`, `configure_flags`, `cflags`, `ldflags`.
- `core_unstripped_bytes`, `core_stripped_bytes`: sum **regular unique ELF payloads** for executable and `libpython` (if present), excluding symlink duplicates.
- `stdlib_source_data_bytes`, `native_extensions_bytes`, `installed_total_bytes`, `external_shared_libs` (list and size), `archive_bytes`, `default_distribution`, and per-variant `installed_bytes`, `archive_bytes`, and `status`.
- Startup latency for `python -S -c pass`, normal `python -c pass`, and a representative stdlib import workload; use repeated runs with median/spread and identify cold vs warm cache semantics honestly.
- Peak RSS for startup/import and one CPU-bound and one I/O-bound representative workload; test hardware and environment.
- CPython and zerodep pass/fail/skip counts, extension inventory diff, ABI result, package smoke result, `eligible` boolean, and failure reasons.

Do not compare raw static executable bytes against only the shared build's launcher. Do not count symlinks twice. Distinguish the installed runtime from external system dependencies and from the compressed archive size. Do not use illustrative MB numbers as actual results.

Report the **Pareto frontier** for size vs startup/runtime/RSS, not only the smallest build. Define explicit acceptable performance regressions after baseline data is available; require human approval for release selection. A different profile may win on each Python version and architecture.

## 8. GitHub Actions workflows

### `.github/workflows/ci.yml` — fast PR/push gate

- Triggers: PR, push to `main`, manual dispatch.
- Begin with CPython 3.14 x86-64; matrix of five profiles, `fail-fast: false`, bounded job timeout.
- Install required build packages and toolchains; pin actions to reviewed commit SHAs for production (major tags acceptable only during bootstrap).
- Run source verification, build, stdlib/extension smoke tests, zerodep smoke tests, core size measurements, and package smoke test.
- Upload build logs, metrics JSON, test results, and archives with unambiguous names including version/target/profile.
- Publish a PR summary table. Keep PR jobs bounded; run the full CPython regression suite in the benchmark/nightly workflow if too costly for every PR.
- Mark missing artifacts, missing dependencies, patch failures, or unverified source as hard failures.

### `.github/workflows/benchmark.yml` — full experiments

- Triggers: `workflow_dispatch`, scheduled (e.g. weekly), optionally protected-branch pushes.
- Full matrix of enabled versions/targets/profiles; `fail-fast: false`.
- Run full CPython and zerodep tests, repeated startup/RSS benchmarks, ABI checks, complete inventory validation.
- Store raw results and machine-readable summaries as artifacts; aggregate after all jobs finish, including failed cells and explicit missing metrics.
- Avoid presenting cross-runner benchmark differences as compiler effects: use a controlled runner class, ideally dedicated benchmark runners for precise comparisons.
- Maintain historical summaries without blindly committing noisy generated outputs to `main`.

### `.github/workflows/release.yml` — controlled distribution

- Trigger: version tag or manual dispatch with approval/environment protection.
- Read `configs/release-selection.toml` to select the reviewed profile for each supported version/target.
- Rebuild from pinned inputs, rerun compatibility and package smoke gates, create deterministic tarball when possible, SHA256SUMS, build manifest, and GitHub artifact attestations where supported.
- Publish only **eligible** artifacts; never ship a profile merely because it is smallest.
- Test extracted artifacts on the claimed compatibility baseline. Document minimum glibc and linked-library requirements.

### `.github/workflows/upstream.yml` — update proposals

- Scheduled check for new CPython maintenance releases on supported lines.
- Propose changes to pinned version/checksum in a PR with release notes and CI results; do not auto-merge or auto-release.
- If patches fail, report the conflict and request manual adaptation.

### Example CI skeleton (Codex must implement scripts/configs)

```yaml
name: SnugPy CI
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-24.04
    timeout-minutes: 120
    strategy:
      fail-fast: false
      matrix:
        python: ['3.14']
        target: [linux-x86_64]
        profile: [baseline, size, lto, static, clang-oz]
    steps:
      - uses: actions/checkout@v4
      - name: Install dependencies
        run: ./scripts/check-deps.sh --install-ubuntu
      - name: Fetch and verify CPython
        run: ./scripts/fetch.sh '${{ matrix.python }}'
      - name: Build
        run: ./scripts/build.sh '${{ matrix.python }}' '${{ matrix.profile }}' '${{ matrix.target }}'
      - name: Validate
        run: ./scripts/test.sh '${{ matrix.python }}' '${{ matrix.profile }}' '${{ matrix.target }}' --smoke
      - name: Package and test extraction
        run: ./scripts/package.sh '${{ matrix.python }}' '${{ matrix.profile }}' '${{ matrix.target }}'
      - name: Measure
        run: ./scripts/measure.sh '${{ matrix.python }}' '${{ matrix.profile }}' '${{ matrix.target }}'
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: snugpy-${{ matrix.python }}-${{ matrix.target }}-${{ matrix.profile }}
          path: |
            results/${{ matrix.python }}/**
            dist/*.tar.xz
          if-no-files-found: warn
```

**Implementation note:** The skeleton uses `results/${{ matrix.python }}/**` for convenience; adjust it to the actual exact-tag output layout. The release workflow should use pinned action SHAs and stronger artifact handling. The example is not a substitute for working scripts or tests.

## 9. Implementation phases for Codex

### Phase A — Functional skeleton (first PR)

- Create repository layout, config parser/schema, version pinning, source checksum verification, dependency installer/checker, and README.
- Implement baseline and `size` local builds for pinned CPython 3.14, out-of-tree and isolated.
- Add unit tests for profile resolution, version/target validation, source integrity, path isolation, and duplicate-safe ELF accounting.
- **Acceptance:** clean Ubuntu machine can build both profiles using documented commands, and generated interpreters start successfully.

### Phase B — Five-profile matrix and GitHub CI

- Implement `lto`, `static`, `clang-oz`; explicitly handle compiler and linker availability.
- Add `.github/workflows/ci.yml`, package/install smoke, artifacts, metrics, PR summary.
- **Acceptance:** five independent jobs execute; failures are clearly attributable and do not cancel others; no shared build contamination.

### Phase C — Compatibility and measurements

- Complete stdlib inventory and extension checks; CPython regression suite; zerodep tests; ABI extension test.
- Add stable size, startup, RSS, and dependency measurements, machine-readable results, and comparison report.
- **Acceptance:** baseline-relative regressions and missing modules are detected and block eligibility.

### Phase D — Releases and update automation

- Implement reviewed selection config, release workflow, manifest, checksums, extracted-package validation, and provenance.
- Implement upstream update PR workflow with version pin updates and test gates.
- **Acceptance:** approved artifact can be rebuilt and traced to source, compiler, patches, and test results.

### Phase E — Expand supported versions and targets

- Add pinned CPython 3.15 to the **same** build system, not a new fork.
- Add native Linux ARM64 CI and architecture-specific measurements.
- **Acceptance:** matrix expands to 20 jobs without duplicating build logic; any exceptions are isolated in version/target adapters or patches.

### Phase F — Advanced optimizations only after evidence

- Use `size -A`, `readelf`, `nm --size-sort`, and linker maps to locate hotspots.
- Introduce carefully justified, measured CPython source patches only when compiler/linker approaches plateau. Require per-version patch applicability and full regression tests.
- Consider additional combined profiles and performance trade-offs, never stdlib removal.

## 10. Codex operating instructions

1. Implement working code, not just workflow YAML or placeholders. Prioritize an end-to-end 3.14 baseline before generalization.
2. Keep all Python-version logic data-driven and in one repository. Do not clone the SnugPy project into per-version branches/forks.
3. Do not invent source checksums, CPython release tags, benchmark results, passing tests, or GitHub workflow outcomes. If internet access is unavailable, make pins configurable and state which checks remain unverified.
4. Preserve the complete stdlib. Never silently disable modules or bypass tests to make a build pass.
5. Make CI and local builds invoke identical scripts. Document exact commands, prerequisites, and output paths.
6. Use small commits/PR-sized milestones with runnable tests. On failures, preserve logs and continue unrelated matrix jobs.
7. Favor boring, inspectable tooling over premature frameworks. A shell-first implementation with TOML config and a small Python report generator is acceptable.
8. Provide a final implementation report: files created, commands executed, real test results, real size numbers (if measured), unresolved blockers, and next actions.

## 11. Definition of done (initial milestone)

- [ ] One SnugPy codebase with version-agnostic build scripts and immutable CPython source pin.
- [ ] CPython 3.14 builds independently under `baseline`, `size`, `lto`, `static`, and `clang-oz` on Linux x86-64.
- [ ] Every build has a distinct build directory, install prefix, logs, metrics, and set of distribution archives.
- [ ] Complete stdlib is preserved in every build prefix and in the `test` distribution; `headless`/`headed` exclusions are explicit, smoke-tested, and measured separately.
- [ ] CPython smoke and zerodep tests execute with results recorded; ABI checks implemented.
- [ ] GitHub Actions CI matrix uploads artifacts and summary even if individual cells fail.
- [ ] Metrics distinguish interpreter core, full install, archive, and external dependencies.
- [ ] README documents reproducible local invocation and known limitations.
- [ ] No compatibility or performance claims without corresponding measurements.

**Next milestone:** full regression/benchmark workflows, approved releases, CPython 3.15, and ARM64.
