# Runtime external libraries

SnugPy distribution archives do not bundle external C libraries. The interpreter
core links only the C runtime, `libm`, and the dynamic loader. Optional native
extensions load their libraries by soname. The runtime image must provide those
sonames.

This page records the two link environments, the `static-lean` ABI gate, the
measured dependency inventory, and the three runtime image strategies.

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
| `libzstd.so.1` | 763,816 | `libzstd1` | `_zstd` |
| `libssl.so.3` | 688,160 | `libssl3` | `_ssl` |
| `liblzma.so.5` | 190,456 | `liblzma5` | `_lzma` |
| `libz.so.1` | 121,280 | `zlib1g` | `zlib`, `binascii` |
| `libbz2.so.1.0` | 74,688 | `libbz2-1.0` | `_bz2` |
| `libffi.so.8` | 43,480 | `libffi8` | `_ctypes` |
| `libuuid.so.1` | 34,872 | `libuuid1` | `_uuid` |

Optional libraries total 8,097,024 bytes. `libcrypto` is 59% of that total.
`libc.so.6`, `libm.so.6`, and `ld-linux-x86-64.so.2` come from `libc6` and are
always present in a glibc base image.

Debian 12 OpenSSL 3.0 does not depend on brotli. The conda-forge OpenSSL used
by the comparison profiles also pulled brotli, which added about 1 MiB. The
Debian-based deployment path avoids that dependency.

## Runtime image strategy

SnugPy has three runtime Dockerfiles. All use the `static-lean` profile and run
the same module and SQLite smoke test. The Debian slim and distroless images use
`runtime`. The scratch image can use either `runtime` or `runtime-nano`.

| Image | Distribution | Final bytes | MiB | Shell | Package manager |
| --- | --- | ---: | ---: | --- | --- |
| Debian slim | `runtime` | 131,471,769 | 125.38 | yes | apt |
| Distroless | `runtime` | 75,338,025 | 71.85 | no | no |
| Scratch | `runtime` | 65,259,602 | 62.24 | no | no |
| Scratch | `runtime-nano` | 33,500,721 | 31.95 | no | no |

### Docker Hub tags

The release workflow publishes the `static-lean` images for `linux/amd64`:

| Tag | Distribution | Dockerfile |
| --- | --- | --- |
| `oaklight/snugpy:0.1.0` | `runtime-nano` | `runtime-scratch.Dockerfile` |
| `oaklight/snugpy:latest` | `runtime-nano` | `runtime-scratch.Dockerfile` |
| `oaklight/snugpy:0.1.0-runtime` | `runtime` | `runtime-scratch.Dockerfile` |
| `oaklight/snugpy:0.1.0-distroless` | `runtime` | `runtime-distroless.Dockerfile` |
| `oaklight/snugpy:0.1.0-debian` | `runtime` | `runtime.Dockerfile` |

`scripts/publish-images.sh` builds every image, runs the module and SQLite
smoke test, and only pushes after the smoke test passes. Use `--push` to
publish and `--latest` to add the `latest` tag. The release workflow supplies
the Docker Hub credentials through repository secrets.

```bash
SNUGPY_RELEASE=0.1.0 ./scripts/publish-images.sh \
  3.14 static-lean linux-x86_64 \
  --namespace oaklight --tag 0.1.0 --push --latest
```

### Debian slim

`docker/runtime.Dockerfile` starts from `debian:bookworm-slim`, installs only
`libssl3`, `libsqlite3-0`, and `netbase`, copies the `runtime` distribution to
`/opt/snugpy`, and sets `PATH`. `netbase` provides `/etc/services` and
`/etc/protocols` for service-name resolution. `libbz2`, `libffi`, `liblzma`,
`libuuid`, `libzstd`, and `zlib1g` are already present in the slim base image.

The Dockerfile uses a multi-stage build:

```dockerfile
FROM ${BASE} AS unpack
ADD ${ARCHIVE} /opt/
RUN mv /opt/snugpy-* /opt/snugpy

FROM ${BASE}
RUN apt-get update && apt-get install -y --no-install-recommends ${PACKAGES} ...
COPY --from=unpack /opt/snugpy /opt/snugpy
```

The final image does not include the unpack stage. `ADD` followed by `RUN mv` in
one stage leaves two copies in the image. The old single-stage Dockerfile
measured 177,391,776 bytes. The current multi-stage image measures 131,471,769
bytes, a reduction of 45,920,007 bytes or 25.9%.

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
| SnugPy `runtime` installation | 49,003,968 |
| Copied libraries and layer overhead | 2,666,440 |
| Final distroless image | 75,338,025 |

The distroless image is 56,133,744 bytes smaller than the Debian slim image, a
42.7% reduction. It is 57.5% smaller than the original single-stage image.

CI runs the module and SQLite smoke test inside the image. A separate local
check also passed HTTPS, numpy 2.5.5, and pandas 3.1.1.

### Scratch

`docker/runtime-scratch.Dockerfile` assembles the final image `FROM scratch`.
A Debian builder stage copies only:

- the dynamic loader, `libc`, `libm`, `libmvec`, `libgcc_s`, and `libstdc++`
- OpenSSL, SQLite, zlib, zstd, bz2, lzma, libffi, and libuuid
- NSS resolver files and `/etc/nsswitch.conf`
- the CA certificate bundle and OpenSSL configuration
- full tzdata
- `/etc/passwd`, `/etc/group`, `/tmp`, and `/home/nonroot`

The final image has no shell, package manager, compiler, userland utilities, or
distribution metadata. It runs as UID 65532.

| Distribution | SnugPy installation | Root filesystem | Final image |
| --- | ---: | ---: | ---: |
| `runtime` | 49,003,968 | 16,255,634 | 65,259,602 |
| `runtime-nano` | 17,245,087 | 16,255,634 | 33,500,721 |

The scratch root filesystem costs 16,255,634 bytes. The installed Python tree
determines the remaining size, so `runtime-nano` is the minimum image for an
agent sandbox that needs preinstalled packages.

Scratch `runtime` is 10,078,423 bytes smaller than distroless `runtime`, a 13.4%
reduction. Scratch `runtime-nano` is 41,837,304 bytes smaller than distroless
`runtime`, a 55.5% reduction. It is 97,971,048 bytes smaller than the Debian
slim `runtime` image, a 74.5% reduction.

Local verification inside the scratch image passed:

```text
runtime-ok
OpenSSL 3.0.22
TLSv1.3
dns <resolved address>
tz America/New_York
uid 65532 nonroot
sqlite 1
numpy 2.5.5
pandas 3.1.1
{'a': 3}
```

The CI smoke test imports `ssl`, `sqlite3`, `ctypes`, `json`, `asyncio`, `bz2`,
`hashlib`, `lzma`, `socket`, `uuid`, `zlib`, and `zoneinfo`, checks
`socket.getservbyname("http", "tcp")`, then runs an SQLite query. DNS, HTTPS,
and numpy/pandas were separate local checks, not CI gates.

`scripts/image-size.sh` selects the Dockerfile with `IMAGE_DOCKERFILE`:

```bash
IMAGE_DOCKERFILE=docker/runtime-scratch.Dockerfile \
  ./scripts/image-size.sh 3.14 static-lean linux-x86_64 \
    debian:bookworm-slim runtime-nano
```

## Next options

- Offline variant: drop `_ssl` and `_hashlib` to remove `libssl` and
  `libcrypto`, saving 5.4 MiB. This breaks HTTPS, so it needs a separate
  distribution name.
- Minimal SQLite: compile a reduced amalgamation into `_sqlite3`. This removes
  the 1.4 MiB system dependency and may shrink the total, at the cost of a
  build-time SQLite pin.
- Minimal OpenSSL: build a pinned OpenSSL without legacy providers, engines,
  tests, docs, zstd, or brotli. The current Debian `libcrypto` is 4.7 MiB and
  dominates the external-library footprint.
- Reduced tzdata: keep only the zones required by the deployment. Full tzdata
  costs about 1.3 MiB.
- Pinned base images: record the Debian and distroless digests next to the
  archive hash so both images are reproducible.

Remeasure after every change:

```bash
./scripts/image-size.sh 3.14 static-lean linux-x86_64 \
  debian:bookworm-slim runtime
IMAGE_DOCKERFILE=docker/runtime-scratch.Dockerfile \
  ./scripts/image-size.sh 3.14 static-lean linux-x86_64 \
  debian:bookworm-slim runtime-nano
```
