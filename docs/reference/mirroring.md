# Baseline Mirroring And Local Divergence

This repository carries three documentation scopes:

- `docs/decision-records/org/` mirrors accepted organization ADRs from
  `nwarila-platform/.github`.
- `docs/decision-records/template/` mirrors accepted UBI 9 image-pattern ADRs
  that still apply to this repository.
- `docs/decision-records/repo/` records local decisions for
  `ubi9-aws-signing-helper`.

The local repository is not a scaffold. It may diverge from the inherited UBI 9
image pattern when the AWS helper requires a different implementation, but the
reason must be explicit in a repo-scoped ADR.

## Current Local Divergence

Repo ADR-0001 records the main divergence: `aws_signing_helper` is compiled from
upstream source inside `containers/Dockerfile` with the validated Go FIPS module.
That local decision changes the manifest shape, build-args generator output,
Dockerfile stages, CI build path, publish workflow evidence, and documentation
for this image.

## Files That Should Stay Locally Accurate

When inherited baseline text conflicts with this repository's source-build
model, update the local file instead of preserving inaccurate template prose.
The most important local files are:

- `README.md`
- `examples/image-manifest.json`
- `containers/Dockerfile`
- `tools/build_image.sh`
- `tools/check_image_manifest.py`
- `tools/generate_build_args.py`
- `tools/check_compliance_checklist.py`
- `tools/verify.py`
- `tests/runtime-hardening.sh`
- `.github/workflows/reusable-ubi-image-build.yaml`
- `.github/workflows/publish-image.yaml`
- `docs/explanation/*`
- `docs/how-to/*`
- `docs/reference/*`
- `docs/compliance/*`
- `docs/decision-records/repo/*`

## Review Rule

A local document should describe mechanisms that exist in this repository. If a
claim depends on future source-integrity work, release promotion policy, or
deployment configuration, document it as a gap or out-of-scope control rather
than as implemented evidence.
