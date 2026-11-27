# Version and distribution matrix

This page is the consolidated inventory of everything SnugPy currently builds.
It covers one pinned CPython version and one target. A new CPython minor
version is a separate build matrix, not a configuration switch.

Snapshot source:

- CI run `45936972209` on `main`, commit `483087e`
- CPython `3.14.9`
- Target `linux-x86_64`
- Profiles: seven
- Distributions: six per profile

## Supported Python versions

| Python | Role | Status |
| --- | --- | --- |
| 3.10 | Minimum for the SnugPy tooling and pinned `zerodep` | Not built |
| 3.11 | No pin | Not built |
| 3.12 | Toolchain interpreter only | Not built |
| 3.13 | No pin | Not built |
| 3.14.9 | Pinned build target | Built, smoke-tested, not release-eligible |

The 3.10 floor is a tooling requirement. It does not imply a 3.10
distribution. Each built CPython minor version gets its own pinned source
archive, build prefix, extension ABI, and release decision.

## Platforms

| Platform | Status |
| --- | --- |
| `linux-x86_64` | Built |
| `linux-aarch64` | Not started |
| macOS | Not started |
| Windows | Not started |

`static-lean` is built inside `debian:bookworm`. The other profiles build on
the Ubuntu 24.04 runner against conda-forge libraries.

## Build profiles

Core bytes cover the executable and `libpython` when present. Installed and
archive bytes use the default `headless` distribution. Startup is the median
warm-cache `python -c pass` time. RSS is the peak for the same command.

| Profile | Core stripped | Core vs baseline | Headless installed | Headless archive | Startup | RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 6,384,032 | +0.00% | 71,937,788 | 12,359,488 | 9.245 ms | 10,336 KiB |
| `size` | 5,090,400 | -20.26% | 69,928,547 | 11,750,620 | 10.670 ms | 9,104 KiB |
| `lto` | 4,968,224 | -22.18% | 69,716,235 | 11,721,472 | 16.420 ms | 8,844 KiB |
| `static` | 5,009,472 | -21.53% | 69,850,098 | 11,743,492 | 14.429 ms | 8,896 KiB |
| `clang-oz` | 5,025,184 | -21.29% | 69,795,920 | 11,761,900 | 10.305 ms | 8,724 KiB |
| `lean` | 4,223,984 | -33.84% | 68,407,469 | 11,451,976 | 10.398 ms | 8,332 KiB |
| `static-lean` | 3,673,432 | -42.46% | 67,456,470 | 11,387,468 | 14.443 ms | 7,584 KiB |

`static-lean` is the smallest profile. It is also the only profile linked
against Debian 12 system libraries instead of the conda-forge toolchain
libraries. It is a non-PIE executable, so container or VM isolation must be the
security boundary.

No profile is release-eligible yet. CI runs smoke tests and the ABI gate, but
the full CPython regression suite and `zerodep` tests are skipped. `eligible` is
`false` for every row in the report until those gates run.

Startup medians vary by several milliseconds between CI runs. Treat them as
order-of-magnitude indicators, not a stable ranking. Core, installed, and
archive sizes are stable across runs.

## Distribution variants

Cells show installed size / archive size in MiB. Every profile produces all six
variants from the same stripped installation tree.

| Profile | `headed` | `headless` | `micro` | `nano` | `runtime` | `test` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 77.2 / 12.8 | 68.6 / 11.8 | 49.5 / 7.2 | 20.6 / 4.5 | 49.5 / 7.2 | 237.3 / 27.0 |
| `size` | 75.3 / 12.2 | 66.7 / 11.2 | 47.6 / 6.6 | 18.7 / 3.9 | 47.6 / 6.6 | 233.3 / 26.2 |
| `lto` | 75.1 / 12.2 | 66.5 / 11.2 | 47.4 / 6.6 | 18.5 / 3.9 | 47.4 / 6.6 | 286.3 / 64.2 |
| `static` | 75.2 / 12.2 | 66.6 / 11.2 | 47.5 / 6.6 | 18.6 / 3.9 | 47.5 / 6.6 | 241.0 / 26.2 |
| `clang-oz` | 75.1 / 12.2 | 66.6 / 11.2 | 47.4 / 6.6 | 18.6 / 3.9 | 47.4 / 6.6 | 233.1 / 26.3 |
| `lean` | 73.8 / 11.9 | 65.2 / 10.9 | 46.2 / 6.3 | 17.3 / 3.6 | 46.2 / 6.3 | 232.8 / 26.1 |
| `static-lean` | 72.9 / 11.9 | 64.3 / 10.9 | 45.3 / 6.3 | 16.4 / 3.5 | 45.3 / 6.3 | 240.6 / 26.0 |

The `lto` `test` archive at 64.2 MiB is an outlier. Every other `test` archive
is close to 26 MiB. Investigate before using that cell as a baseline.

## `static-lean` distribution detail

| Distribution | Installed bytes | Archive bytes | Smoke imports |
| --- | ---: | ---: | --- |
| `headed` | 76,423,212 | 12,442,140 | `ssl`, `sqlite3`, `ctypes`, `tkinter` |
| `headless` | 67,456,470 | 11,387,468 | `ssl`, `sqlite3`, `ctypes` |
| `micro` | 47,474,194 | 6,558,320 | `ssl`, `sqlite3`, `ctypes`, `json`, `asyncio` |
| `nano` | 17,228,342 | 3,721,540 | `ssl`, `sqlite3`, `ctypes`, `json`, `asyncio` |
| `runtime` | 47,474,313 | 6,561,324 | `ssl`, `sqlite3`, `ctypes`, `json`, `asyncio` |
| `test` | 252,291,530 | 27,280,416 | `ssl`, `sqlite3`, `ctypes`, `test` |

`runtime` is the agent-sandbox target. It keeps `site-packages` so
`numpy`/`pandas` installed at image-build time survive, and removes `pip`,
`ensurepip`, headers, and build files.

`nano` is the smallest archive. It removes `__pycache__`, so imports compile on
first use. Use it only when the runtime filesystem can absorb that cost or is
read-only with a warm build step.

## Runtime image footprint

Measured with `debian:bookworm-slim` as the base and `runtime` as the
distribution.

| Component | Bytes | MiB |
| --- | ---: | ---: |
| Base image | 74,867,382 | 71.40 |
| SnugPy installation | 47,583,622 | 45.38 |
| Optional system libraries | 8,097,024 | 7.72 |
| Image, old single-stage build | 177,391,776 | 169.17 |
| Image, multi-stage build | 130,681,569 | 124.63 |

The multi-stage build saves 46,710,207 bytes, or 26.3% of the old image. The
single-stage Dockerfile created two 47.5 MiB layers: one for `ADD` and one
for the following `RUN mv`. The multi-stage build removes the duplicate. The
image contains no compiler, no package manager, and no build headers.

## External libraries used by `static-lean`

The interpreter core needs only `libc`, `libm`, and the dynamic loader. Optional
extensions load these libraries by soname at runtime:

| SONAME | Bytes | Debian package | Loaded by |
| --- | ---: | --- | --- |
| `libcrypto.so.3` | 4,742,424 | `libssl3` | `_ssl`, `_hashlib` |
| `libsqlite3.so.0` | 1,437,848 | `libsqlite3-0` | `_sqlite3` |
| `libzstd.so.1` | 763,816 | `libzstd1` | `_zstd`, OpenSSL |
| `libssl.so.3` | 688,160 | `libssl3` | `_ssl` |
| `liblzma.so.5` | 190,456 | `liblzma5` | `_lzma` |
| `libz.so.1` | 121,280 | `zlib1g` | `zlib`, `binascii`, OpenSSL |
| `libbz2.so.1.0` | 74,688 | `libbz2-1.0` | `_bz2` |
| `libffi.so.8` | 43,480 | `libffi8` | `_ctypes` |
| `libuuid.so.1` | 34,872 | `libuuid1` | `_uuid` |

The optional libraries total 8,097,024 bytes. `libcrypto` is 59% of that total.
See `docs/runtime-libraries.md` for the ABI gate and the image strategy.

## Reproduce

```bash
./scripts/fetch.sh 3.14 --zerodep
./scripts/build.sh 3.14 static-lean linux-x86_64 --jobs "$(nproc)"
./scripts/test.sh 3.14 static-lean linux-x86_64 --smoke
./scripts/package.sh 3.14 static-lean linux-x86_64
./scripts/measure.sh 3.14 static-lean linux-x86_64 --runs 5
./scripts/check-abi.sh out/v3.14.9/linux-x86_64/static-lean
./scripts/image-size.sh 3.14 static-lean linux-x86_64 \
  debian:bookworm-slim runtime
```
