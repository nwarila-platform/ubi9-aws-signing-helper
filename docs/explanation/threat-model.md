# Threat Model

This repository focuses on supply-chain and runtime-surface risks for the
`ubi9-aws-signing-helper` image.

## Primary Risks

| Risk | Repository Response |
| --- | --- |
| Mutable base image drift | Pin both the `ubi-minimal` builder and `ubi-micro` runtime images by digest in the manifest. |
| Unreviewed runtime contents | Keep `dnf.packages` explicit and assemble the runtime rootfs in a builder stage with weak dependencies disabled. |
| Scanners blind to image contents | Preserve `/var/lib/rpm` so Trivy, Grype, and OpenSCAP enumerate installed packages instead of reporting an empty image. |
| FIPS build provenance drift | Compile with `GOFIPS140=v1.0.0`, `CGO_ENABLED=1`, and `GOTOOLCHAIN=local`; fail the Dockerfile build unless `go version -m` and `readelf` prove the expected binary properties. |
| Upstream source integrity gap | Record `application.verification.type: none` and document that `SOURCE_REF` is a git tag without signed source checksum or commit-SHA verification. |
| Excess runtime tooling | Assert no shell, no package manager, and no curl/wget in the final image. |
| Root runtime | Require UID/GID `65532:65532`. |
| Missing release evidence | Publish by digest with BuildKit SBOM/provenance, GitHub artifact attestation, recursive keyless Cosign signing, OpenSCAP, Trivy, Grype, runtime hardening, and public GHCR pull checks. |

## Out Of Scope

- Registry compromise response.
- Admission-controller policy.
- AWS IAM Roles Anywhere profile, trust-anchor, certificate, and private-key
  lifecycle.
- Kubernetes runtime sandbox configuration.
- Secrets handling in consuming workloads.

Those belong to the deployment platform and operational runbooks, not static OCI
image contents.
