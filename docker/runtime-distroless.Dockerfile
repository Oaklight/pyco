ARG BASE=gcr.io/distroless/cc-debian12:nonroot

FROM debian:bookworm-slim AS libs
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    libsqlite3-0 libffi8 libbz2-1.0 liblzma5 libuuid1 zlib1g libzstd1 \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* \
 && mkdir -p /out \
 && cp -a \
      /usr/lib/x86_64-linux-gnu/libsqlite3.so.0* \
      /usr/lib/x86_64-linux-gnu/libffi.so.8* \
      /usr/lib/x86_64-linux-gnu/libbz2.so.1.0* \
      /usr/lib/x86_64-linux-gnu/liblzma.so.5* \
      /usr/lib/x86_64-linux-gnu/libuuid.so.1* \
      /usr/lib/x86_64-linux-gnu/libz.so.1* \
      /usr/lib/x86_64-linux-gnu/libzstd.so.1* \
      /out/

FROM debian:bookworm-slim AS unpack

ARG ARCHIVE=runtime.tar.xz
ADD ${ARCHIVE} /opt/
RUN mv /opt/snugpy-* /opt/snugpy

FROM ${BASE}

COPY --from=libs /out/ /usr/lib/x86_64-linux-gnu/
COPY --from=unpack /opt/snugpy /opt/snugpy

ENV PATH=/opt/snugpy/bin:$PATH
ENTRYPOINT ["/opt/snugpy/bin/python3.14"]
