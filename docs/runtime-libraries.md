# Runtime external libraries

SnugPy does not bundle external C libraries. The interpreter core links only the
C runtime, `libm`, and the dynamic loader. Optional native extensions load their
libraries by soname. The runtime image must provide those sonames.

This page records the two link environments, the `static-lean` ABI gate, the
measured dependency inventory, and the runtime image strategy.

## Two link environments

| Profiles | Link source | Portability |
| --- | --- | --- |
| `baseline`, `size`, `lto`, `static`, `clang-oz`, `lean` | conda-forge libraries in the toolchain prefix | Needs the matching conda libraries or a bundled copy |
| `static-lean` | Debian 12 system libraries | Needs Debian 12 library sonames and the ABI gate below |

The default profiles are comparison builds. Their extension modules link
conda-forge OpenSSL 3.4 and other conda libraries. The archive does not include
those libraries.

`static-lean` is the deployment profile. It sets `external_libs = "system"` in
`configs/profiles.toml`, builds inside `debian:bookworm`, and links the Debian
12 system libraries.

## Why the linker needs explicit flags

conda-forge Clang ships a default configuration file that injects:

- the conda sysroot
- conda include directories
- conda library directories
- conda rpath entries

Those defaults silently take precedence over Debian libraries. `static-lean`
therefore uses:

```text
--no-default-config --gcc-toolchain=/usr
```

`--no-default-config` disables the conda configuration file.
`--gcc-toolchain=/usr` makes Clang use the Debian GCC startup files and
libraries. The Debian container must install `gcc` and `libc6-dev`; without the
system CRT objects, the compiler cannot link a test program.

The profile also replaces `pkg-config` with `/usr/bin/pkg-config` and sets
`PKG_CONFIG_LIBDIR` to the Debian paths. The conda prefix is removed from
`LIBRARY_PATH` and `LD_LIBRARY_PATH` for this profile.

The flag spelling matters. Clang accepts `--no-default-config`. The single-dash
form `-no-default-config` fails with `unknown argument` and surfaces only as
`C compiler cannot create executables`.

## ABI gate

`scripts/check-abi.sh` inspects every ELF file in the install prefix with
`objdump -T`. The current gate allows:

| Family | Allowed |
| --- | --- |
| `GLIBC` | 2.36 |
| `OPENSSL` | 3.0.9 |
| `GLIBCXX` | 3.4.30 |
| `CXXABI` | 1.3.13 |

Measured result for the current `static-lean` archive:

```text
OK: OPENSSL max 3.0.0 (allowed 3.0.9)
OK: GLIBC max 2.35 (allowed 2.36)
OK: GLIBCXX not referenced
OK: CXXABI not referenced
```

The artifact needs glibc 2.35 even though Debian 12 provides 2.36. The gate
allows 2.36 because that is the build platform. A consumer must still provide
compatible OpenSSL 3.0 and SQLite sonames.

## Dependency inventory

The inventory below comes from the `static-lean` `runtime` archive executed
inside `debian:bookworm-slim`. Symlinks are resolved to their real files.

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

Optional libraries total 8,097,024 bytes. `libcrypto` is 59% of that total.
`libc.so.6`, `libm.so.6`, and `ld-linux-x86-64.so.2` come from `libc6` and are
always present in a glibc base image.

Debian's OpenSSL 3.0 links zstd but not brotli. The Ubuntu 24.04 conda OpenSSL
also pulled brotli, which added about 1 MiB. Debian 12 avoids that chain.

## Runtime image strategy

SnugPy has two runtime Dockerfiles. Both use `runtime`, keep `site-packages`,
and run the same `ssl`, `sqlite3`, `ctypes`, `json`, and `asyncio` smoke test.

### Debian slim

`docker/runtime.Dockerfile` starts from `debian:bookworm-slim`, installs only
`libssl3` and `libsqlite3-0`, copies the `runtime` distribution to `/opt/snugpy`,
and sets `PATH`. `libbz2`, `libffi`, `liblzma`, `libuuid`, `libzstd`, and
`zlib1g` are already present in the slim base image.

The Dockerfile uses a multi-stage build:

```dockerfile
FROM ${BASE} AS unpack
ADD ${ARCHIVE} /opt/
RUN mv /opt/snugpy-* /opt/snugpy

FROM ${BASE}
RUN apt-get update && apt-get install -y --no-install-recommends ${PACKAGES} ...
COPY --from=unpack /opt/snugpy /opt/snugpy
```

The final image does not include the unpack stage. This matters: `ADD` followed
by `RUN mv` in one stage leaves two copies in the image. The old single-stage
Dockerfile measured 177,391,776 bytes. The multi-stage Dockerfile measures
130,681,569 bytes, a reduction of 46,710,207 bytes or 26.3%.

### Distroless

`docker/runtime-distroless.Dockerfile` uses
`gcr.io/distroless/cc-debian12:nonroot` as the final stage. Distroless removes
the shell, package manager, and most of the Debian userland. It still provides
glibc, `libgcc`, OpenSSL 3, and the CA certificate bundle.

A Debian builder stage installs and copies only the libraries that distroless
lacks:

- `libsqlite3.so.0`
- `libffi.so.8`
- `libbz2.so.1.0`
- `liblzma.so.5`
- `libuuid.so.1`
- `libz.so.1`
- `libzstd.so.1`

The image runs as the distroless `nonroot` user, UID 65532.

| Component | Bytes |
| --- | ---: |
| `gcr.io/distroless/cc-debian12:nonroot` base | 23,667,617 |
| SnugPy `runtime` installation | 47,583,622 |
| Copied libraries and layer overhead | 2,557,131 |
| Final distroless image | 73,808,370 |

The distroless image is 56,873,199 bytes smaller than the Debian slim image, a
43.5% reduction. It is 58.4% smaller than the original single-stage image.

Verified inside the image:

```text
runtime-ok
ssl OpenSSL 3.0.20
sqlite 1
https 200
```

The smoke test covers `ssl`, `sqlite3` writes, `ctypes`, `json`, `asyncio`,
`bz2`, `lzma`, `zlib`, `uuid`, and `hashlib`, plus an HTTPS request.

### Comparison

| Image | Base bytes | Final bytes | Shell | Package manager |
| --- | ---: | ---: | --- | --- |
| Debian slim | 74,867,382 | 130,681,569 | yes | apt |
| Distroless | 23,667,617 | 73,808,370 | no | no |

`scripts/image-size.sh` selects the Dockerfile with `IMAGE_DOCKERFILE`:

```bash
IMAGE_DOCKERFILE=docker/runtime-distroless.Dockerfile \
  ./scripts/image-size.sh 3.14 static-lean linux-x86_64 \
    gcr.io/distroless/cc-debian12:nonroot runtime
```

## Next options

- Offline variant: drop `_ssl` and `_hashlib` to remove `libssl` and
  `libcrypto`, saving 5.4 MiB. This breaks HTTPS, so it needs a separate
  distribution name.
- Minimal SQLite: compile a reduced amalgamation into `_sqlite3`. This removes
  the 1.4 MiB system dependency and may shrink the total, at the cost of a
  build-time SQLite pin.
- Minimal OpenSSL: build a pinned OpenSSL without legacy providers, engines,
  tests, docs, zstd, or brotli. Bundle it only if a target base image cannot
  provide a compatible OpenSSL.
- Pinned base images: record the Debian and distroless digests next to the
  archive hash so both images are reproducible.

Remeasure after every change:

```bash
./scripts/image-size.sh 3.14 static-lean linux-x86_64 \
  debian:bookworm-slim runtime
```
