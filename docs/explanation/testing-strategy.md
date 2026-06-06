# Testing Strategy

The repository tests the image contract at three levels: fast Python checks,
Docker build/runtime checks, and publish-time evidence checks against the
pushed digest. The goal is to prove the build this repository actually performs:
compile `aws_signing_helper` from upstream source inside the Dockerfile with the
validated Go FIPS module, then ship it in a minimal UBI 9 runtime image.

## Contract Checks (`python tools/verify.py ci`)

Run on every push and pull request; no Docker is required. The CI target
validates:

- Diataxis documentation layout and required ADR mirrors.
- The committed image manifest in strict mode.
- Dockerfile contract markers for UBI 9 rootfs construction, preserved rpmdb,
  from-source Go/FIPS build settings, and forbidden prebuilt-binary inputs.
- Runtime hardening script coverage for forbidden tools, rpmdb presence, CA
  bundle presence, non-root execution, read-only-rootfs compatibility, dropped
  capabilities, and setuid/setgid rejection.
- RHEL 9 STIG and CIS Docker applicability checklists.
- The build-args generator, including parity between manifest-derived build
  args and Dockerfile `ARG` declarations.
- The local image build helper's `--load` behavior for runtime testing.
- Security workflow pinning and repository-specific reusable workflow shape.
- Publish workflow markers for BuildKit SBOM/provenance, GitHub artifact
  attestation, recursive keyless Cosign signing, OpenSCAP, Trivy, Grype,
  runtime hardening, and public GHCR pull verification.
- Stale placeholders, local Markdown links, local workflow references in docs,
  and docs references to phantom build paths.

## Image Build And Runtime Checks

The reusable image-build workflow runs a single-platform Docker Buildx build and
loads the result into the local Docker daemon for inspection. During the
Dockerfile build:

1. The `rpm-rootfs` stage installs only the manifest-selected RPM package set
   into `/rootfs`, removes regenerable cache/logs, and fails if the rpm database
   is absent.
2. The `gobuild` stage clones the upstream AWS helper tag, compiles with
   `GOFIPS140=v1.0.0`, `CGO_ENABLED=1`, and `GOTOOLCHAIN=local`, then requires
   `go version -m` to record the FIPS/cgo/module provenance.
3. The same stage uses `readelf` to prove the helper is a dynamic ELF before it
   can be copied into the final runtime image.
4. The `runtime` stage removes shell binaries, sets the non-root user, and
   exposes only the helper entrypoint.

After the build, `tests/runtime-hardening.sh` exports the image filesystem and
checks the runtime contract. CI also runs the image with `--help` under
`--network none`; that proves the dynamic helper binary can start without
turning a local build into release evidence.

## Publish Evidence

Release evidence is generated only in `.github/workflows/publish-image.yaml`,
where the image is pushed to GHCR by digest. That workflow:

- Builds the multi-platform image from the same manifest-derived build args with
  BuildKit SBOM and provenance enabled.
- Generates and verifies a GitHub artifact attestation for the pushed digest.
- Signs the pushed digest recursively with keyless Cosign and verifies the
  expected GitHub Actions OIDC identity.
- Runs OpenSCAP, Trivy, Grype, runtime hardening, and anonymous public pull
  checks against the pushed digest.

Docker's local `--load` exporter is intentionally limited to runtime tests. It
does not preserve registry-backed attestation evidence, so release conclusions
must be tied to the pushed digest.

## Known Gap

The Dockerfile fetches upstream source by release tag and the manifest records
`application.verification.type` as `none`. The current tests prove the FIPS build
properties and image-level release evidence, but they do not prove a signed
upstream source checksum or a commit-SHA pin.
