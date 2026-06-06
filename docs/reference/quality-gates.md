# Quality Gates

These checks are only merge-blocking when repository rulesets require their
reported status names. See [`governance.md`](governance.md) for the repository
settings that make the gates enforceable.

| Gate | Source | Role | Notes |
| --- | --- | --- | --- |
| Contract verify | `python tools/verify.py ci` | Blocking | Checks docs layout, manifest contract, Dockerfile markers, runtime script coverage, compliance checklists, Go builder image pinning, build-args generator parity, local build-helper boundaries, security caller workflows, the image-build reusable, publish workflow markers, stale placeholders, docs phantom-build references, Markdown links, and local workflow references. |
| actionlint | `.github/workflows/ci.yaml` | Blocking | Validates workflow syntax and common GitHub Actions mistakes. |
| markdownlint | `.github/workflows/ci.yaml` | Blocking | Keeps Markdown readable and consistent. |
| Image build + hardening | `.github/workflows/reusable-ubi-image-build.yaml` | Blocking | Builds the UBI 9 image from the manifest. The Dockerfile compiles `aws_signing_helper` from upstream source with the validated Go FIPS module, asserts the binary provenance and dynamic linkage, loads the local image, runs runtime hardening, and smoke-runs `--help`. |
| Runtime hardening | `tests/runtime-hardening.sh <image> <entrypoint>` | Blocking | Inspects the exported image rootfs for forbidden tools, preserved rpmdb, CA bundle, non-root user, read-only-rootfs compatibility, dropped-capability guidance, no-new-privileges guidance, setuid/setgid rejection, and expected entrypoint metadata. |
| CodeQL | `.github/workflows/codeql.yaml` | Blocking | Calls `nwarila-platform/.github/.github/workflows/reusable-codeql.yaml` and scans `actions` plus `python`. |
| Trivy + Gitleaks + zizmor | `.github/workflows/security.yaml` | Blocking | Calls `nwarila-platform/.github/.github/workflows/reusable-iac-security.yaml` for filesystem misconfig scanning, secret scanning, and GitHub Actions security analysis. |
| OpenSSF Scorecard | `.github/workflows/scorecard.yaml` | Blocking | Calls `nwarila-platform/.github/.github/workflows/reusable-scorecard.yaml` for repo-level supply-chain posture. |
| Repo hygiene | `.github/workflows/repo-hygiene.yaml` | Blocking | Calls `nwarila-platform/.github/.github/workflows/reusable-repo-hygiene.yaml` for org workflow hygiene, SHA pins, and `pull_request_target` safety. |
| Auto-merge for trusted bots | `.github/workflows/auto-merge.yaml` | Advisory | Calls `nwarila-platform/.github/.github/workflows/reusable-auto-merge.yaml`; trusted bot PRs can auto-merge only after required checks pass. |
| Publish signed image | `.github/workflows/publish-image.yaml` | Release | Builds and pushes the multi-platform image by digest with BuildKit SBOM/provenance, GitHub artifact attestation, recursive Cosign signing, OpenSCAP scorecard, Trivy, Grype, runtime hardening, and public GHCR pull verification. |

## Local CI Boundary

Pull-request CI uses Docker's local `--load` exporter so runtime hardening can
inspect the image. Registry-backed SBOM, provenance, attestation, signature, and
scan evidence is produced only by the publish workflow because those records are
bound to the pushed digest.
