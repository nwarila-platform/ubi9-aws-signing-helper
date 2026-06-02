# ubi9-aws-signing-helper

Red Hat UBI 9 (`ubi-micro`) OCI image of the **AWS IAM Roles Anywhere signing
helper** (`aws_signing_helper`) — the serve-mode sidecar that vends short-lived
STS credentials for HashiCorp Vault `awskms` auto-unseal on self-hosted
(non-EKS) clusters where there is no IRSA / instance profile / IMDS to source
AWS credentials from.

The helper is built **FROM SOURCE** with the FIPS 140-3 **Go Cryptographic
Module v1.0.0** (CMVP #5247): `GOFIPS140=v1.0.0`, `CGO_ENABLED=1`,
`GODEBUG=fips140=on`. This diverges from the template's copy-verified-prebuilt
model because `aws_signing_helper` is glibc-DYNAMIC (PKCS#11/TPM cgo support is
compiled unconditionally, so a `CGO_ENABLED=0` static build is not possible and
a prebuilt vendor binary cannot carry `GOFIPS140` provenance). See
[ADR-0001](docs/decision-records/repo/0001-helper-go-native-fips.md).

```sh
aws_signing_helper serve --port 9911 --hop-limit 1 \
  --certificate /aws/certs/tls.crt --private-key /aws/certs/tls.key \
  --trust-anchor-arn <ta> --profile-arn <profile> --role-arn <role>
# consumer: AWS_EC2_METADATA_SERVICE_ENDPOINT=http://127.0.0.1:9911
```

`serve` and its flags are supplied as pod args; the image entrypoint is just the
helper binary.

## Prerequisites

The contract checks need only Python; the image lifecycle needs Docker:

- Python 3.12+
- Bash, for the build and runtime hardening scripts
- Docker Buildx (with QEMU for multi-arch), to compile + build the image

## Quickstart

Run the contract checks (no Docker required):

```sh
python tools/verify.py ci
```

Build the image end-to-end (Docker required):

```sh
make image
```

`make image` renders the docker buildx flags from the manifest, builds the UBI 9
image for `linux/amd64` (the `gobuild` stage clones and compiles
`aws_signing_helper` with the validated FIPS module and asserts the FIPS build
properties via `go version -m` before the binary reaches the runtime stage), and
runs the runtime hardening assertions against it.

## Supply chain

- Two-stage UBI 9 build: an `ubi-minimal` `microdnf --installroot` stage
  assembles the runtime rootfs (the rpm database at `/var/lib/rpm` is preserved
  so scanners enumerate packages), and the final `ubi-micro` runtime carries no
  shell, no package manager, no `curl`/`wget`.
- The helper is compiled from the pinned upstream source
  (`github.com/aws/rolesanywhere-credential-helper` at a release tag) inside the
  Dockerfile with the pinned, digest-addressed `golang` builder image. The Go
  builder is Renovate-capped below 1.26 so the validated FIPS module stays valid.
- Multi-arch (`linux/amd64`, `linux/arm64`), digest-addressable, published to
  GHCR with BuildKit **SBOM + provenance**, a **GitHub artifact attestation**,
  and a keyless **Cosign signature** (recursive). See
  [`.github/workflows/publish-image.yaml`](.github/workflows/publish-image.yaml).
- The release gate additionally runs the **OpenSCAP DISA RHEL 9 STIG** profile,
  **Trivy**, and **Grype** against the pushed digest, plus the runtime hardening
  contract and an anonymous public GHCR pull check.

## Runtime hardening contract

Non-root UID/GID **65532** (named `nonroot` account synthesized into the
rootfs); read-only root filesystem compatible; drop all capabilities;
`seccompProfile: RuntimeDefault`. The image contains no shell and none of the
forbidden tools enumerated in the manifest; it ships a populated CA bundle at
`/etc/pki/tls/certs/ca-bundle.crt` for TLS to AWS endpoints.
[`tests/runtime-hardening.sh`](tests/runtime-hardening.sh) asserts these against
the built/published image.

## Repository Layout

| Path | Role |
| --- | --- |
| [`contracts/image-manifest.schema.json`](contracts/image-manifest.schema.json) | Human-reviewable image manifest schema (supports the from-source `application.build` model). |
| [`examples/image-manifest.json`](examples/image-manifest.json) | Manifest with real pinned UBI bases, Go builder, and upstream source ref. |
| [`containers/Dockerfile`](containers/Dockerfile) | Three-stage build: `rpm-rootfs` (ubi-minimal), `gobuild` (golang FIPS compile), `runtime` (ubi-micro). |
| [`tests/runtime-hardening.sh`](tests/runtime-hardening.sh) | Runtime assertion script (no shell/package manager/curl/wget; rpmdb present; CA bundle populated). |
| [`tools/verify.py`](tools/verify.py) | Local and CI contract checks. |
| [`tools/check_image_manifest.py`](tools/check_image_manifest.py) | Validate the image manifest contract. |
| [`tools/generate_build_args.py`](tools/generate_build_args.py) | Render docker buildx flags (UBI bases + Go toolchain/source pins) from the manifest. |
| [`tools/build_image.sh`](tools/build_image.sh) | Build the image locally from the manifest plus the rendered build args. |
| [`tools/check_compliance_checklist.py`](tools/check_compliance_checklist.py) | Validate the RHEL 9 STIG + CIS applicability checklists. |
| [`tools/verify_public_ghcr_pull.sh`](tools/verify_public_ghcr_pull.sh) | Assert the published digest is anonymously pullable from GHCR. |
| [`docs/`](docs/) | Diataxis documentation plus org/template/repo ADR scopes. |
| [`.github/workflows/`](.github/workflows/) | `ci.yaml` runs the contract checks and the image-build reusable; `codeql.yaml`, `scorecard.yaml`, `security.yaml`, `auto-merge.yaml`, and `repo-hygiene.yaml` call the canonical reusable workflows in `nwarila-platform/.github`. |
| [`.github/workflows/reusable-ubi-image-build.yaml`](.github/workflows/reusable-ubi-image-build.yaml) | Repository-specific reusable: build (compile-in-Dockerfile) -> runtime hardening -> `--help` smoke. |
| [`.github/workflows/publish-image.yaml`](.github/workflows/publish-image.yaml) | Main/tag/manual publish: multi-arch build+push with SBOM/provenance -> attestation -> recursive Cosign -> OpenSCAP STIG + Trivy + Grype -> runtime hardening -> anonymous GHCR pull. |

## Normalized Repo Interface

| Command | Purpose |
| --- | --- |
| `make verify` | Run the local CI-equivalent contract checks. |
| `make build-args` | Render docker buildx flags from the manifest. |
| `make image-build` | Build the OCI image for `linux/amd64`. |
| `make image-test` | Run runtime hardening assertions against the built image. |
| `make image` | Run the full build -> hardening pipeline. |

## License

MIT - see [LICENSE](LICENSE).
