# Publish The Image

`.github/workflows/publish-image.yaml` is the release path for this repository.
It builds the multi-platform image from the reviewed manifest, pushes the image
to GHCR by digest, and verifies image-level evidence against that digest.

## When It Runs

The workflow runs on:

- Pushes to `main`.
- Tags matching `v*`.
- Manual `workflow_dispatch`.

The workflow filename is part of the keyless Cosign identity check, so do not
rename it without updating the verification policy and related ADRs.

## Release Flow

The publish job performs these steps:

1. Checks out the repository with a pinned `actions/checkout` commit.
2. Sets up Python, QEMU, Docker Buildx, and Cosign with pinned action SHAs.
3. Logs in to GHCR with the GitHub Actions token.
4. Runs `tools/generate_build_args.py examples/image-manifest.json` and writes
   the Buildx arguments to `dist/buildargs.txt`.
5. Runs `docker buildx build` for the manifest-selected platforms with
   `--provenance=mode=max`, `--sbom=true`, and `--push`.
6. Extracts the pushed digest from `dist/image-metadata.json`.
7. Generates a GitHub artifact attestation for the pushed image digest.
8. Signs the pushed digest recursively with keyless Cosign.
9. Verifies the GitHub artifact attestation.
10. Verifies the Cosign signature identity and OIDC issuer.
11. Builds the OpenSCAP RHEL 9 STIG datastream from a SHA512-pinned
    ComplianceAsCode release and uploads the advisory scorecard.
12. Runs Trivy and Grype vulnerability gates against the pushed digest.
13. Runs `tests/runtime-hardening.sh` against the pushed digest.
14. Runs `tools/verify_public_ghcr_pull.sh` to prove the image is anonymously
    pullable from GHCR.

The helper binary is compiled during the Dockerfile build for each target
platform. The release workflow does not build or verify a separate binary
artifact before Docker Buildx runs.

## Evidence To Review

For a completed release, review:

- The pushed image reference and digest emitted by the `Build and push image
  with BuildKit attestations` step.
- BuildKit SBOM and provenance attached to the pushed OCI image.
- The GitHub artifact attestation verification output.
- The Cosign verification output, including the expected workflow identity and
  `https://token.actions.githubusercontent.com` issuer.
- OpenSCAP ARF/HTML artifacts, with the caveat that the host STIG scorecard is
  advisory for a minimal container image.
- Trivy and Grype gate output.
- Runtime hardening output against the same digest.
- Anonymous GHCR pull output.

## Verify Evidence From A Clean Checkout

After a publish run, verify the attestation and signature against the digest:

```sh
gh attestation verify oci://ghcr.io/OWNER/ubi9-aws-signing-helper@sha256:DIGEST -R OWNER/ubi9-aws-signing-helper

cosign verify ghcr.io/OWNER/ubi9-aws-signing-helper@sha256:DIGEST \
  --certificate-identity-regexp 'https://github.com/OWNER/ubi9-aws-signing-helper/.github/workflows/publish-image.yaml@refs/(heads/main|tags/v.*)' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

Use the digest, not a mutable tag, when reviewing release evidence.

## Review Rules

- Keep every `uses:` action pinned to a reviewed commit SHA.
- Keep registry authentication in GitHub Actions permissions and token scope,
  not in the manifest or Docker build arguments.
- Attest, sign, scan, and harden the pushed digest.
- Treat the OpenSCAP STIG output as advisory unless a repo ADR changes the gate;
  Trivy and Grype are the hard vulnerability gates.
- Do not claim upstream source signature validation until the manifest and
  Dockerfile implement it.
