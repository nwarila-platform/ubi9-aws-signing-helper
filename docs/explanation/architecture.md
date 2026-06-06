# Architecture

`ubi9-aws-signing-helper` is a concrete UBI 9 container image for the AWS IAM
Roles Anywhere Credential Helper. It builds `aws_signing_helper` from upstream
source inside `containers/Dockerfile` so the resulting binary can record the
validated Go FIPS module provenance this repository requires.

## Repository Boundary

This repository owns:

- A manifest shape that records the reviewed UBI base image digests, the minimum
  RPM package set, the Go builder image, the upstream helper repository and
  `SOURCE_REF`, runtime policy, and required release evidence.
- A manifest-to-build-args generator so `examples/image-manifest.json` stays the
  single review surface for Docker build inputs.
- A three-stage Dockerfile:
  - `rpm-rootfs` assembles a minimal UBI 9 runtime rootfs with GPG-checked
    `microdnf` and preserves `/var/lib/rpm` for scanners.
  - `gobuild` clones the upstream helper tag, compiles with
    `GOFIPS140=v1.0.0`, `CGO_ENABLED=1`, and `GOTOOLCHAIN=local`, and asserts
    FIPS/cgo/module provenance with `go version -m` plus dynamic ELF linkage
    with `readelf`.
  - `runtime` starts from `ubi-micro`, copies only the rootfs and helper binary,
    removes shell entry points, sets `GODEBUG=fips140=on`, and runs as
    `65532:65532`.
- Runtime hardening assertions in `tests/runtime-hardening.sh`.
- Local and CI contract checks in `tools/verify.py`.
- A release workflow that builds and pushes by digest with BuildKit SBOM and
  provenance, GitHub artifact attestations, recursive keyless Cosign signing,
  OpenSCAP, Trivy, Grype, runtime hardening, and anonymous GHCR pull checks.

This repository does not claim upstream source signature verification. The
manifest records `application.verification.type` as `none`; the Dockerfile
fetches `SOURCE_REF` as an upstream git tag and does not verify a signed source
checksum or a pinned commit SHA.

## Build Flow

The build has five reviewable steps:

1. **Input review.** `examples/image-manifest.json` records the UBI base image
   digests, `dnf.packages`, `application.build.go_image`,
   `application.build.source_repo`, `application.build.source_ref`, runtime
   policy, and required evidence.
2. **Root filesystem construction.** The `ubi-minimal` stage installs the
   manifest-selected RPM packages into `/rootfs`, removes regenerable cache and
   logs, synthesizes the non-root account, and fails if the rpm database is not
   preserved for scanners.
3. **Helper compile.** The Go builder stage installs only the cgo build tools it
   needs, clones the upstream helper tag, reconciles the upstream `go.mod`
   directive to the validated FIPS toolchain's language level, and compiles the
   helper for the active Buildx `TARGETARCH`.
4. **Build assertions.** Before the binary can enter the runtime stage, the
   Dockerfile requires `go version -m` to show `GOFIPS140=v1.0.0`,
   `CGO_ENABLED=1`, and the AWS upstream module path. It also requires `readelf`
   to find a dynamic ELF interpreter because the helper's PKCS#11/TPM support
   uses cgo.
5. **Runtime assembly.** The final image copies the assembled rootfs and helper
   binary into `ubi-micro`, removes shell binaries that can arrive from the base
   layer, sets FIPS mode activation with `GODEBUG=fips140=on`, and exposes only
   `/usr/local/bin/aws_signing_helper`.

Local builds use Docker's `--load` exporter so the hardening script can inspect
the image. Release builds use registry push by digest because SBOM, provenance,
attestation, signature, and scan evidence belongs to the pushed image digest.

## External Dependencies

- Red Hat UBI 9 base images and the Red Hat repositories used by `microdnf`.
- The pinned digest-addressed Go builder image recorded in the manifest.
- `github.com/aws/rolesanywhere-credential-helper` at the manifest-selected
  upstream release tag.
- Docker Buildx and QEMU for multi-platform builds.
- GitHub Actions, GitHub artifact attestations, Sigstore Cosign, OpenSCAP,
  Trivy, and Grype for release evidence.
