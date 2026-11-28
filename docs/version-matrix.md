# Version and distribution matrix

This page is the consolidated inventory of everything SnugPy currently builds.
It covers one pinned CPython version and five native target definitions; only
`linux-x86_64` is release-approved. A new CPython minor version is a separate
build matrix, not a configuration switch.

Snapshot source:

- Other profile metrics: CI run `45948508874` on `main`, commit `39329e3`
- `static-lean` metrics, image sizes, and release gate: benchmark run
  `46067091932`, commit `9e6fc6b`
- CPython `3.14.9`
- Release target `linux-x86_64`
- Native build targets: `linux-arm64`, `macos-arm64`, `macos-x86_64`,
  `windows-x86_64`
- Profiles: nine
- Distributions: seven per profile

## Supported Python versions

| Python | Role | Status |
| --- | --- | --- |
| 3.10 | Minimum for the SnugPy tooling and pinned `zerodep` | Not built |
| 3.11 | No pin | Not built |
| 3.12 | Toolchain interpreter only | Not built |
| 3.13 | No pin | Not built |
| 3.14.9 | Pinned build target | Built, fully tested, release-eligible with `static-lean` |

The 3.10 floor is a tooling requirement. It does not imply a 3.10
distribution. Each built CPython minor version gets its own pinned source
archive, build prefix, extension ABI, and release decision.

## Platforms

| Platform | Runner | Status |
| --- | --- | --- |
| `linux-x86_64` | `ubuntu-24.04` | Built, fully tested, release-approved |
| `linux-arm64` | `ubuntu-24.04-arm` | Native CI build configured; release approval pending |
| `macos-arm64` | `macos-15` | Native CI build configured; release approval pending |
| `macos-x86_64` | `macos-15-intel` | Native CI build configured; release approval pending |
| `windows-x86_64` | `windows-2025` | Native CI build configured; release approval pending |

Linux `static-lean` is built inside `debian:bookworm`; Linux ARM64 uses the same
container on an ARM64 runner. macOS uses native Clang and Homebrew dependencies.
Windows uses CPython `PCbuild` and `PC/layout` with MSVC. Docker is used only
for Linux.

## Build profiles

Core bytes cover the executable and `libpython` when present. Installed and
archive bytes use the default `headless` distribution. Startup is the median
warm-cache `python -c pass` time. RSS is the peak for the same command.

| Profile | Core stripped | Core vs baseline | Headless installed | Headless archive | Startup | RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 6,384,032 | +0.00% | 71,938,414 | 12,364,144 | 9.273 ms | 10,280 KiB |
| `size` | 5,090,400 | -20.26% | 69,929,173 | 11,752,804 | 9.609 ms | 9,060 KiB |
| `lto` | 4,968,224 | -22.18% | 69,716,861 | 11,721,212 | 10.716 ms | 8,872 KiB |
| `static` | 5,009,472 | -21.53% | 69,850,724 | 11,743,108 | 9.944 ms | 8,860 KiB |
| `clang-oz` | 5,025,184 | -21.29% | 69,796,546 | 11,757,624 | 10.398 ms | 8,736 KiB |
| `lean` | 4,223,984 | -33.84% | 68,408,095 | 11,453,428 | 10.325 ms | 8,344 KiB |
| `static-lean` | 3,686,520 | -42.25% | 69,146,001 | 11,396,640 | 13.873 ms | 7,516 KiB |

`static-lean` is the smallest profile. It is also the only profile linked
against Debian 12 system libraries instead of the conda-forge toolchain
libraries. It is a non-PIE executable, so container or VM isolation must be the
security boundary.

`static-lean` is release-eligible for 0.1.0. Benchmark run `46067091932` passed
the full CPython regression suite and the `zerodep` tests with network access
(`eligible: true`, no failures or skips). The other six profiles still run
smoke tests only and remain experimental.

Startup medians vary by several milliseconds between CI runs. Treat them as
order-of-magnitude indicators, not a stable ranking. Core, installed, and
archive sizes are stable across runs.

## Distribution variants

Cells show installed size / archive size in MiB. Every profile produces all
seven variants from the same stripped installation tree.

| Profile | `headed` | `headless` | `micro` | `nano` | `runtime` | `runtime-nano` | `test` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 77.2 / 12.8 | 68.6 / 11.8 | 49.5 / 7.2 | 20.6 / 4.5 | 49.5 / 7.2 | 20.6 / 4.5 | 237.3 / 27.0 |
| `size` | 75.3 / 12.2 | 66.7 / 11.2 | 47.6 / 6.6 | 18.7 / 3.9 | 47.6 / 6.6 | 18.7 / 3.9 | 233.3 / 26.2 |
| `lto` | 75.1 / 12.2 | 66.5 / 11.2 | 47.4 / 6.6 | 18.5 / 3.9 | 47.4 / 6.6 | 18.5 / 3.9 | 286.3 / 64.2 |
| `static` | 75.2 / 12.2 | 66.6 / 11.2 | 47.5 / 6.6 | 18.6 / 3.9 | 47.5 / 6.6 | 18.6 / 3.9 | 241.0 / 26.2 |
| `clang-oz` | 75.1 / 12.2 | 66.6 / 11.2 | 47.4 / 6.6 | 18.6 / 3.9 | 47.4 / 6.6 | 18.6 / 3.9 | 233.1 / 26.3 |
| `lean` | 73.8 / 11.9 | 65.2 / 10.9 | 46.2 / 6.3 | 17.3 / 3.6 | 46.2 / 6.3 | 17.3 / 3.6 | 232.8 / 26.0 |
| `static-lean` | 74.5 / 11.9 | 65.9 / 10.9 | 46.7 / 6.3 | 16.4 / 3.5 | 46.7 / 6.3 | 16.4 / 3.6 | 242.3 / 26.0 |

The `lto` `test` archive at 64.2 MiB is an outlier. Every other `test` archive
is close to 26 MiB. Investigate before using that cell as a baseline.

## `static-lean` distribution detail

| Distribution | Installed bytes | Archive bytes | Smoke imports |
| --- | ---: | ---: | --- |
| `headed` | 78,112,743 | 12,450,960 | `ssl`, `sqlite3`, `ctypes`, `tkinter` |
| `headless` | 69,146,001 | 11,396,640 | `ssl`, `sqlite3`, `ctypes` |
| `micro` | 49,003,849 | 6,568,892 | `ssl`, `sqlite3`, `ctypes`, `json`, `asyncio` |
| `nano` | 17,244,968 | 3,722,400 | `ssl`, `sqlite3`, `ctypes`, `json`, `asyncio` |
| `runtime` | 49,003,968 | 6,563,328 | `ssl`, `sqlite3`, `ctypes`, `json`, `asyncio` |
| `runtime-nano` | 17,245,087 | 3,724,212 | `ssl`, `sqlite3`, `ctypes`, `json`, `asyncio` |
| `test` | 254,108,716 | 27,283,788 | `ssl`, `sqlite3`, `ctypes`, `test` |

`runtime` is the agent-sandbox target. It keeps `site-packages` so
`numpy`/`pandas` installed at image-build time survive, and removes `pip`,
`ensurepip`, headers, and build files.

`runtime-nano` is the compact agent-sandbox target. It keeps `site-packages`,
but removes `__pycache__` from both the standard library and installed packages.
Imports compile on first use. Its installed tree is 31,758,881 bytes smaller
than `runtime`. `nano` remains the smallest stdlib-only variant; its installed
tree is 119 bytes smaller than `runtime-nano`.

## Runtime image footprint

Measurements use `static-lean` on `linux-x86_64`. The three `runtime` images
contain 49,003,968 installed bytes. The scratch `runtime-nano` image contains
17,245,087 installed bytes.

| Image | Distribution | Final bytes | MiB | Shell | Package manager |
| --- | --- | ---: | ---: | --- | --- |
| Debian slim | `runtime` | 131,471,769 | 125.38 | yes | apt |
| Distroless | `runtime` | 75,338,025 | 71.85 | no | no |
| Scratch | `runtime` | 65,259,602 | 62.24 | no | no |
| Scratch | `runtime-nano` | 33,500,721 | 31.95 | no | no |

Scratch `runtime` is 10,078,423 bytes smaller than distroless `runtime`, a
13.4% reduction. Scratch `runtime-nano` is 41,837,304 bytes smaller than
distroless `runtime`, a 55.5% reduction. It is 97,971,048 bytes smaller than
the Debian slim `runtime` image, a 74.5% reduction.

### Scratch root filesystem

| Component | Bytes | MiB |
| --- | ---: | ---: |
| SnugPy `runtime` or `runtime-nano` installation | varies | varies |
| Shared libraries, loader, CA certificates, tzdata, NSS, runtime files | 16,255,634 | 15.50 |
| Final scratch image | installation + 16,255,634 | |

The scratch root filesystem contains only:

- `libc`, `libm`, `libmvec`, `libgcc_s`, and `libstdc++`
- OpenSSL, SQLite, zlib, zstd, bz2, lzma, libffi, and libuuid
- NSS resolver files and `/etc/nsswitch.conf`
- the CA certificate bundle and OpenSSL configuration
- full tzdata
- `/etc/passwd`, `/etc/group`, `/tmp`, and `/home/nonroot`

It has no shell, package manager, compiler, userland utilities, or distro
metadata. It runs as UID 65532. HTTPS, DNS, SQLite writes, `ctypes`, the
compression modules, time zones, numpy 2.5.5, and pandas 3.1.1 passed local
verification.

## External libraries used by `static-lean`

The interpreter core needs only `libc`, `libm`, and the dynamic loader. Optional
extensions load these libraries by soname at runtime:

| SONAME | Bytes | Debian package | Loaded by |
| --- | ---: | --- | --- |
| `libcrypto.so.3` | 4,742,424 | `libssl3` | `_ssl`, `_hashlib` |
| `libsqlite3.so.0` | 1,437,848 | `libsqlite3-0` | `_sqlite3` |
| `libzstd.so.1` | 763,816 | `libzstd1` | `_zstd` |
| `libssl.so.3` | 688,160 | `libssl3` | `_ssl` |
| `liblzma.so.5` | 190,456 | `liblzma5` | `_lzma` |
| `libz.so.1` | 121,280 | `zlib1g` | `zlib`, `binascii` |
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
IMAGE_DOCKERFILE=docker/runtime-distroless.Dockerfile \
  ./scripts/image-size.sh 3.14 static-lean linux-x86_64 \
  gcr.io/distroless/cc-debian12:nonroot runtime
IMAGE_DOCKERFILE=docker/runtime-scratch.Dockerfile \
  ./scripts/image-size.sh 3.14 static-lean linux-x86_64 \
  debian:bookworm-slim runtime-nano
```
