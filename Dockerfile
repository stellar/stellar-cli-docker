# syntax=docker/dockerfile:1.10

# Trusted, reproducible stellar-cli image. See SEP-58 for the full contract:
# https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0058.md
#
# Every input is pinned. The Debian base via the official Rust image's
# multi-arch index digest, the Rust toolchain by version, and stellar-cli to
# a specific upstream commit SHA. Build args are not optional; the build
# scripts and CI workflows always supply them.

ARG RUST_VERSION
ARG RUST_IMAGE_DIGEST
ARG STELLAR_CLI_REF
ARG STELLAR_CLI_VERSION
ARG VARIANT=standard
ARG BUILD_DATE
ARG BUILDS_JSON_SHA

FROM rust:${RUST_VERSION}-slim-bookworm@${RUST_IMAGE_DIGEST} AS builder
ARG STELLAR_CLI_REF
ARG STELLAR_CLI_VERSION
ENV CARGO_HOME=/usr/local/cargo \
    DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        libdbus-1-dev \
        libssl-dev \
        libudev-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*
RUN cargo install --locked --root /out \
        --git https://github.com/stellar/stellar-cli.git \
        --rev "${STELLAR_CLI_REF}" \
        stellar-cli

# Fail the build loudly if the binary's reported version disagrees with the
# version the caller declared. Catches accidental ref/version drift in
# builds.json at build time, not later when an image is already published.
RUN installed="$(/out/bin/stellar version --only-version)" \
    && test "$installed" = "${STELLAR_CLI_VERSION}" \
    || { echo "stellar-cli version mismatch: binary reports '$installed', expected '${STELLAR_CLI_VERSION}'" >&2; exit 1; }

FROM rust:${RUST_VERSION}-slim-bookworm@${RUST_IMAGE_DIGEST}
ARG RUST_VERSION
ARG RUST_IMAGE_DIGEST
ARG STELLAR_CLI_REF
ARG STELLAR_CLI_VERSION
ARG VARIANT
ARG BUILD_DATE
ARG BUILDS_JSON_SHA
ARG TARGETARCH

# RUSTUP_TOOLCHAIN is baked in so an in-source `rust-toolchain.toml` in a
# consumer's contract can't silently swap our pinned toolchain at build
# time. Required by SEP-58 "self-contained build environment". Consumers can
# still override with `-e RUSTUP_TOOLCHAIN=...` if they know what they're
# doing.
ENV DEBIAN_FRONTEND=noninteractive \
    RUSTUP_TOOLCHAIN=${RUST_VERSION}

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libdbus-1-3 \
        libssl3 \
        libudev1 \
    && rm -rf /var/lib/apt/lists/*
RUN rustup target add wasm32v1-none
COPY --from=builder /out/bin/stellar /usr/local/bin/stellar
RUN chmod +x /usr/local/bin/stellar

ENV STELLAR_CONFIG_HOME=/config \
    STELLAR_DATA_HOME=/data
WORKDIR /source

ENTRYPOINT ["stellar"]
CMD []

LABEL org.opencontainers.image.title="stellar-cli" \
      org.opencontainers.image.description="Trusted, SEP-58-compatible build image for Stellar smart contracts." \
      org.opencontainers.image.source="https://github.com/stellar/stellar-cli-docker" \
      org.opencontainers.image.url="https://github.com/stellar/stellar-cli-docker" \
      org.opencontainers.image.documentation="https://github.com/stellar/stellar-cli-docker" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.vendor="Stellar Development Foundation" \
      org.opencontainers.image.version="${STELLAR_CLI_VERSION}" \
      org.opencontainers.image.revision="${STELLAR_CLI_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.base.name="docker.io/library/rust:${RUST_VERSION}-slim-bookworm" \
      org.opencontainers.image.base.digest="${RUST_IMAGE_DIGEST}" \
      org.stellar.rust-version="${RUST_VERSION}" \
      org.stellar.rust-image-digest="${RUST_IMAGE_DIGEST}" \
      org.stellar.stellar-cli-ref="${STELLAR_CLI_REF}" \
      org.stellar.stellar-cli-version="${STELLAR_CLI_VERSION}" \
      org.stellar.wasm-target="wasm32v1-none" \
      org.stellar.variant="${VARIANT}" \
      org.stellar.build-arch="${TARGETARCH}" \
      org.stellar.builds-json-sha="${BUILDS_JSON_SHA}"
