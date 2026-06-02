# syntax=docker/dockerfile:1.7

# BuildKit SBOMs should include the build context as well as the builder stages
# that assemble the runtime rootfs and compile the application, not only the
# final image. BUILDKIT_SBOM_SCAN_CONTEXT is a global ARG;
# BUILDKIT_SBOM_SCAN_STAGE must be set as a per-stage ARG inside each stage that
# should be scanned (see
# https://docs.docker.com/build/metadata/attestations/sbom/#configure-sbom-scanners).
ARG BUILDKIT_SBOM_SCAN_CONTEXT=true

# Both UBI bases are digest-pinned (see the image manifest) and Renovate-managed
# with redhat versioning. ubi-minimal carries microdnf for the rootfs builder;
# ubi-micro is the minimal runtime. The Go builder image is pinned by tag@sha256
# and Renovate-capped below 1.26 so the GOFIPS140 module stays validated.
ARG UBI_MINIMAL_IMAGE
ARG UBI_MICRO_IMAGE
ARG GO_IMAGE

# -----------------------------------------------------------------------------
# Stage 1: assemble the runtime rootfs with the rpm database preserved.
# -----------------------------------------------------------------------------
FROM ${UBI_MINIMAL_IMAGE} AS rpm-rootfs
ARG BUILDKIT_SBOM_SCAN_STAGE=true
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG TARGETARCH
# Space-separated microdnf package install specs (names), e.g. "ca-certificates".
ARG DNF_PACKAGES
# Optional space-separated repo IDs to enable exclusively. Empty = use the base
# image's default repositories.
ARG DNF_REPOS=""

# ubi-minimal ships microdnf (not dnf); --installroot requires it to be told
# where the host's repo/vars/config live (it cannot infer them from the empty
# installroot). PRESERVING the rpmdb is mandatory: it is how Trivy/Grype/OpenSCAP
# enumerate the installed packages. Deleting it would make scanners report zero
# packages (a false "0 CVE" result), so this stage NEVER removes
# /rootfs/var/lib/rpm or /rootfs/var/lib/dnf. Only regenerable cache/logs are
# pruned. The runtime binary is glibc-dynamic and runs as a named non-root
# account, so synthesize the passwd/group entries for UID/GID 65532 here.
RUN set -eux; \
    test -n "${DNF_PACKAGES}" || { echo "DNF_PACKAGES must be set" >&2; exit 1; }; \
    mkdir -p /rootfs; \
    microdnf install -y --installroot=/rootfs --releasever=9 \
      --config=/etc/dnf/dnf.conf --noplugins \
      --setopt=reposdir=/etc/yum.repos.d \
      --setopt=varsdir=/etc/dnf/vars \
      --setopt=cachedir=/var/cache/microdnf-installroot \
      --nodocs --setopt=install_weak_deps=0 \
      ${DNF_REPOS:+--disablerepo=* --enablerepo=${DNF_REPOS}} \
      ${DNF_PACKAGES}; \
    microdnf clean all; \
    rm -rf /rootfs/var/cache/* /var/cache/microdnf-installroot \
      /rootfs/var/log/dnf.log /rootfs/var/log/dnf.librepo.log /rootfs/var/log/hawkey.log; \
    if rpm --root=/rootfs -q bash >/dev/null 2>&1; then \
      rpm --root=/rootfs -e --nodeps --noscripts bash; \
    fi; \
    for shell in sh bash dash ash busybox ksh zsh tcsh csh; do \
      rm -f "/rootfs/usr/bin/${shell}" "/rootfs/usr/sbin/${shell}"; \
      if [ -e "/rootfs/usr/bin/${shell}" ] || [ -e "/rootfs/usr/sbin/${shell}" ]; then \
        echo "shell '${shell}' survived in the runtime rootfs" >&2; exit 1; \
      fi; \
    done; \
    test -s /rootfs/var/lib/rpm/rpmdb.sqlite || test -s /rootfs/var/lib/rpm/Packages || \
      { echo "rpm database missing from rootfs; scanners would see zero packages" >&2; exit 1; }; \
    printf 'nonroot:x:65532:65532:AWS signing helper runtime user:/nonexistent:/usr/sbin/nologin\n' > /rootfs/etc/passwd; \
    printf 'nonroot:x:65532:\n' > /rootfs/etc/group; \
    chown 0:0 /rootfs/etc/passwd /rootfs/etc/group; \
    chmod 0644 /rootfs/etc/passwd /rootfs/etc/group

# -----------------------------------------------------------------------------
# Stage 2: compile aws_signing_helper from source with the validated FIPS 140-3
# Go Cryptographic Module. The helper is glibc-DYNAMIC: PKCS#11/TPM support is
# compiled with cgo unconditionally, so CGO_ENABLED=0 cannot produce a working
# static binary. Building inside the Dockerfile lets buildx compile each arch
# natively under QEMU and avoids cgo cross-compilation entirely.
# -----------------------------------------------------------------------------
FROM ${GO_IMAGE} AS gobuild
ARG BUILDKIT_SBOM_SCAN_STAGE=true
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# GOFIPS140=v1.0.0 selects the validated Go Cryptographic Module v1.0.0
# (CMVP #5247, FIPS 140-3 Active). NEVER use "certified"/"inprocess": only the
# literal version maps to the certificate. GOTOOLCHAIN=local pins the toolchain
# to the pinned builder image so no unvalidated toolchain is ever downloaded.
ENV GOFIPS140=v1.0.0 \
    CGO_ENABLED=1 \
    GOTOOLCHAIN=local \
    GOFLAGS=-buildvcs=false

# Source pins (manifest-driven). SOURCE_REF is the upstream release tag;
# GO_MOD_GO_DIRECTIVE reconciles the upstream go.mod's go/toolchain directive
# down to the validated FIPS toolchain's language version (see
# docs/decision-records/repo/0001-helper-go-native-fips.md).
ARG SOURCE_REPO="github.com/aws/rolesanywhere-credential-helper"
ARG SOURCE_REF="v1.8.2"
ARG GO_MOD_GO_DIRECTIVE="1.24.0"

# The cgo C toolchain (gcc) and git are required to clone + build with cgo.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates gcc git; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    test -n "${SOURCE_REF}"; \
    git clone --depth 1 --branch "${SOURCE_REF}" "https://${SOURCE_REPO}.git" /src; \
    cd /src; \
    # Reconcile the upstream go.mod directive to the validated FIPS toolchain's
    # language level. The upstream v1.8.2 go.mod requires go >= 1.26.0, but the
    # GOFIPS140=v1.0.0 validated module (CMVP #5247) exists only in Go 1.24/1.25.
    # Lower the directive and drop the toolchain pin so GOTOOLCHAIN=local builds
    # with the validated 1.24 toolchain. This is a build-time reconciliation of
    # the language floor only; no source is patched.
    sed -i -E "s/^go [0-9]+\.[0-9]+(\.[0-9]+)?/go ${GO_MOD_GO_DIRECTIVE}/" go.mod; \
    sed -i -E "/^toolchain /d" go.mod; \
    head -4 go.mod

RUN set -eux; \
    cd /src; \
    mkdir -p /out; \
    # find the main package: aws_signing_helper's entrypoint is the repo root
    # (main.go -> cmd.Execute()). Build it explicitly.
    test -f main.go || { echo "expected repo-root main package not found" >&2; exit 1; }; \
    go build -trimpath -o /out/aws_signing_helper .; \
    chmod 0555 /out/aws_signing_helper

# Assert the FIPS build properties before the binary can reach the runtime
# stage. Any drift (CGO disabled, wrong GOFIPS140, static link, missing module
# path) fails the build here rather than shipping a non-FIPS binary.
RUN set -eux; \
    info="$(go version -m /out/aws_signing_helper)"; \
    printf '%s\n' "${info}"; \
    printf '%s\n' "${info}" | grep -Eq 'build[[:space:]]+GOFIPS140=v1\.0\.0' \
      || { echo "FIPS assertion failed: GOFIPS140=v1.0.0 not recorded in the binary" >&2; exit 1; }; \
    printf '%s\n' "${info}" | grep -Eq 'build[[:space:]]+CGO_ENABLED=1' \
      || { echo "FIPS assertion failed: CGO_ENABLED=1 not recorded in the binary" >&2; exit 1; }; \
    printf '%s\n' "${info}" | grep -Fq "${SOURCE_REPO}" \
      || { echo "provenance assertion failed: source module path not recorded" >&2; exit 1; }; \
    # Confirm the binary is a glibc-DYNAMIC ELF (interpreter present): the cgo
    # build cannot be static, and the runtime ubi-micro provides glibc.
    interp="$(LC_ALL=C readelf -l /out/aws_signing_helper | grep -Eo '/lib(64)?/ld-[^]]+' | head -1 || true)"; \
    test -n "${interp}" || { echo "expected a dynamic ELF interpreter; got static binary" >&2; exit 1; }; \
    echo "FIPS build verified: GOFIPS140=v1.0.0 CGO_ENABLED=1 dynamic-interp=${interp}"

# -----------------------------------------------------------------------------
# Stage 3: minimal ubi-micro runtime. No shell, no package manager, no
# curl/wget. glibc + the RHEL CA bundle at /etc/pki/tls/certs/ca-bundle.crt come
# from the assembled rootfs.
# -----------------------------------------------------------------------------
FROM ${UBI_MICRO_IMAGE} AS runtime

ARG OCI_CREATED
ARG OCI_DESCRIPTION="Red Hat UBI 9 AWS IAM Roles Anywhere signing helper (FIPS 140-3 Go Cryptographic Module)"
ARG OCI_REVISION
ARG OCI_SOURCE
ARG OCI_TITLE="ubi9-aws-signing-helper"
ARG OCI_VERSION

LABEL org.opencontainers.image.created="${OCI_CREATED}" \
      org.opencontainers.image.description="${OCI_DESCRIPTION}" \
      org.opencontainers.image.revision="${OCI_REVISION}" \
      org.opencontainers.image.source="${OCI_SOURCE}" \
      org.opencontainers.image.title="${OCI_TITLE}" \
      org.opencontainers.image.version="${OCI_VERSION}"

# The assembled rootfs (including /var/lib/rpm for scanners and the synthesized
# nonroot account) and the from-source FIPS binary.
COPY --from=rpm-rootfs /rootfs/ /
COPY --from=gobuild /out/aws_signing_helper /usr/local/bin/aws_signing_helper

# GODEBUG=fips140=on activates the FIPS 140-3 mode of the Go Cryptographic
# Module at runtime; combined with the GOFIPS140=v1.0.0 build it runs the
# validated module in approved mode.
ENV GODEBUG=fips140=on

# ubi-micro itself ships /usr/bin/bash (+ /usr/bin/sh); the COPY --from=rpm-rootfs
# above overlays the assembled rootfs onto the base WITHOUT deleting files the
# base already provides, so a shell removed in the builder rootfs can still be
# present here via the base layer. Remove the shell again in the final image and
# fail the build if any survives.
RUN ["/bin/sh", "-c", "for s in sh bash dash ash busybox ksh zsh tcsh csh; do rm -f \"/usr/bin/$s\" \"/usr/sbin/$s\" \"/bin/$s\" \"/sbin/$s\"; done; for s in sh bash dash ash busybox; do if [ -e \"/usr/bin/$s\" ] || [ -e \"/usr/sbin/$s\" ]; then echo \"shell $s survived in runtime image\" >&2; exit 1; fi; done"]

USER 65532:65532
# `serve` and its flags are supplied as pod args, not baked into the image.
ENTRYPOINT ["/usr/local/bin/aws_signing_helper"]
