ARG BASE=debian:bookworm-slim

FROM ${BASE} AS unpack

ARG ARCHIVE=runtime.tar.xz
ADD ${ARCHIVE} /opt/
RUN mv /opt/snugpy-* /opt/snugpy

FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive
ARG PACKAGES="libssl3 libsqlite3-0"
RUN apt-get update \
 && apt-get install -y --no-install-recommends ${PACKAGES} \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

COPY --from=unpack /opt/snugpy /opt/snugpy

ENV PATH=/opt/snugpy/bin:$PATH
CMD ["python3.14"]
