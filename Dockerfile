# syntax=docker/dockerfile:1

ARG UBUNTU_VERSION=22.04

FROM ubuntu:${UBUNTU_VERSION} AS builder

ARG SIMPLESCALAR_REF=f770dfcee6687b66735c8be0ee4459458d1d1642
ARG SIMPLESCALAR_ARCHIVE=https://github.com/khaledhassan/simplescalar-docker/archive/${SIMPLESCALAR_REF}.tar.gz

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        gzip \
        make \
        tar \
    && rm -rf /var/lib/apt/lists/*

ADD ${SIMPLESCALAR_ARCHIVE} /tmp/simplescalar.tar.gz

RUN mkdir -p /opt/simplescalar-src \
    && tar -xzf /tmp/simplescalar.tar.gz --strip-components=1 -C /opt/simplescalar-src \
    && cd /opt/simplescalar-src/simplesim-3.0 \
    && make config-pisa \
    && make sim-outorder sim-cache sim-safe

FROM ubuntu:${UBUNTU_VERSION} AS runtime

LABEL org.opencontainers.image.title="sim-outorder experiments"
LABEL org.opencontainers.image.description="SimpleScalar sim-outorder runtime for UFPel processor architecture experiments"
LABEL org.opencontainers.image.source="https://github.com/khaledhassan/simplescalar-docker"

ENV DEBIAN_FRONTEND=noninteractive
ENV SIM_OUTORDER_BIN=/usr/local/bin/sim-outorder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        make \
        python3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/simplescalar-src/simplesim-3.0/sim-outorder /usr/local/bin/sim-outorder
COPY --from=builder /opt/simplescalar-src/simplesim-3.0/sim-cache /usr/local/bin/sim-cache
COPY --from=builder /opt/simplescalar-src/simplesim-3.0/sim-safe /usr/local/bin/sim-safe

WORKDIR /workspace

CMD ["bash"]
