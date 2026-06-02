# Security Policy

## Reporting a vulnerability

**Do not file public issues for security vulnerabilities.**

### Preferred: GitHub private vulnerability reporting

Use [GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository's **Security** tab to report a vulnerability directly to the
maintainers.

### Fallback contact

If private vulnerability reporting is unavailable, contact the maintainer through
their [GitHub profile](https://github.com/NWarila).

## What to include

- Description of the vulnerability
- Steps to reproduce or a proof of concept
- The affected component (image build, manifest, workflow, or runtime contract)
  and the image tag/digest if known
- Potential impact

## Response timeline

| Stage | Target |
|-------|--------|
| Initial acknowledgement | 7 business days |
| Validation | 14 days |
| Remediation or mitigation | 90 days when reasonable |

These are targets, not guarantees. Complex issues may take longer; you will be
kept informed of progress.

## Scope

This repository builds a minimal Red Hat UBI 9 (`ubi-micro`) image of the **AWS
IAM Roles Anywhere signing helper** (`aws_signing_helper`). The helper is
compiled **FROM SOURCE** from the pinned upstream release tag with the validated
FIPS 140-3 Go Cryptographic Module v1.0.0 (CMVP #5247): `GOFIPS140=v1.0.0`,
`CGO_ENABLED=1`, `GODEBUG=fips140=on`. The Dockerfile asserts those FIPS build
properties via `go version -m` before the binary reaches the runtime stage. The
binary is glibc-DYNAMIC by necessity (PKCS#11/TPM cgo support is compiled
unconditionally); the runtime `ubi-micro` provides glibc and the CA trust store.

### In scope

- The image build and packaging maintained here: `containers/Dockerfile`, the
  UBI base / dnf package / Go builder / upstream source selection in
  `examples/image-manifest.json`, the build-args and verification logic in
  `tools/`, the runtime-hardening contract in `tests/runtime-hardening.sh`, and
  the supply-chain evidence (SBOM, provenance, attestation, Cosign signature)
  emitted by `.github/workflows/publish-image.yaml`.
- Misconfigurations in this repository's GitHub Actions workflows that could lead
  to secret exposure or privilege escalation.

### Out of scope

- Vulnerabilities in the upstream **AWS IAM Roles Anywhere credential helper**
  itself — report those upstream to
  [AWS](https://github.com/aws/rolesanywhere-credential-helper/security/policy).
  This image compiles the unmodified upstream source.
- Vulnerabilities in the Go toolchain, the FIPS module, or other third-party
  dependencies that should be reported upstream.
- Denial-of-service and social-engineering reports.

## Supported versions

Unless documented otherwise, only the most recent image published from the
default branch (and the latest `v*` release tag) is supported.

## Coordinated disclosure

We follow coordinated disclosure. Please give us reasonable time to investigate
and remediate before public disclosure, act in good faith, and do not access or
modify data that is not yours. We will credit reporters of valid vulnerabilities
unless they prefer to remain anonymous.
