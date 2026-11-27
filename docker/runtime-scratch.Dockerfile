ARG BASE=debian:bookworm-slim

FROM ${BASE} AS unpack

ARG ARCHIVE=runtime.tar.xz
ADD ${ARCHIVE} /opt/
RUN mv /opt/snugpy-* /opt/snugpy

FROM ${BASE} AS rootfs

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    ca-certificates libbz2-1.0 libffi8 libgcc-s1 liblzma5 libssl3 \
    libsqlite3-0 libstdc++6 libuuid1 media-types netbase tzdata zlib1g libzstd1 \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

RUN set -eux; \
    install -d -m 0755 /rootfs/lib/x86_64-linux-gnu; \
    install -d -m 0755 /rootfs/lib64; \
    install -d -m 0755 /rootfs/usr/lib; \
    install -d -m 0755 /rootfs/usr/share; \
    install -d -m 0755 /rootfs/etc/ssl/certs; \
    install -d -m 0755 /rootfs/usr/lib/ssl; \
    install -d -m 1777 /rootfs/tmp; \
    install -d -m 0755 /rootfs/home/nonroot; \
    chown 65532:65532 /rootfs/home/nonroot; \
    ln -s ../../lib/x86_64-linux-gnu /rootfs/usr/lib/x86_64-linux-gnu; \
    ln -s /lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 /rootfs/lib64/ld-linux-x86-64.so.2; \
    cp -a /lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /lib/x86_64-linux-gnu/libc.so.6 /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /lib/x86_64-linux-gnu/libm.so.6 /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /lib/x86_64-linux-gnu/libmvec.so.1 /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /lib/x86_64-linux-gnu/libgcc_s.so.1 /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /lib/x86_64-linux-gnu/libpthread.so.0 /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /lib/x86_64-linux-gnu/libdl.so.2 /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /lib/x86_64-linux-gnu/librt.so.1 /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /lib/x86_64-linux-gnu/libnss_dns.so.2 /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /lib/x86_64-linux-gnu/libnss_files.so.2 /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /lib/x86_64-linux-gnu/libresolv.so.2 /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /usr/lib/x86_64-linux-gnu/libcrypto.so.3* /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /usr/lib/x86_64-linux-gnu/libssl.so.3* /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /usr/lib/x86_64-linux-gnu/libsqlite3.so.0* /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /usr/lib/x86_64-linux-gnu/libffi.so.8* /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /usr/lib/x86_64-linux-gnu/libbz2.so.1.0* /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /usr/lib/x86_64-linux-gnu/liblzma.so.5* /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /usr/lib/x86_64-linux-gnu/libuuid.so.1* /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /usr/lib/x86_64-linux-gnu/libz.so.1* /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /usr/lib/x86_64-linux-gnu/libzstd.so.1* /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /usr/lib/x86_64-linux-gnu/libstdc++.so.6* /rootfs/lib/x86_64-linux-gnu/; \
    cp -a /usr/share/zoneinfo /rootfs/usr/share/; \
    cp -a /etc/ssl/certs/ca-certificates.crt /rootfs/etc/ssl/certs/; \
    cp -a /etc/ssl/openssl.cnf /rootfs/etc/ssl/; \
    cp -a /etc/services /etc/protocols /etc/rpc /etc/ethertypes /etc/mime.types /rootfs/etc/; \
    ln -s /etc/ssl/certs/ca-certificates.crt /rootfs/usr/lib/ssl/cert.pem; \
    ln -s /etc/ssl/certs /rootfs/usr/lib/ssl/certs; \
    ln -s /etc/ssl/openssl.cnf /rootfs/usr/lib/ssl/openssl.cnf; \
    ln -s /usr/share/zoneinfo/Etc/UTC /rootfs/etc/localtime; \
    printf '%s\n' \
      'root:x:0:0:root:/root:/sbin/nologin' \
      'nonroot:x:65532:65532:nonroot:/home/nonroot:/sbin/nologin' \
      > /rootfs/etc/passwd; \
    printf '%s\n' \
      'root:x:0:' \
      'nonroot:x:65532:' \
      > /rootfs/etc/group; \
    printf '%s\n' \
      'passwd: files' \
      'group: files' \
      'hosts: files dns' \
      > /rootfs/etc/nsswitch.conf; \
    printf '%s\n' \
      'multi on' \
      > /rootfs/etc/host.conf

FROM scratch

COPY --from=rootfs /rootfs/ /
COPY --from=unpack /opt/snugpy /opt/snugpy

ENV HOME=/home/nonroot \
    PATH=/opt/snugpy/bin \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

USER 65532:65532
WORKDIR /home/nonroot
ENTRYPOINT ["/opt/snugpy/bin/python3.14"]
