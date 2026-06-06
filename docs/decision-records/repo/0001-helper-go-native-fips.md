# ADR-0001: Compile the helper from source with the FIPS 140-3 Go Cryptographic Module

| Field          | Value                                    |
| -------------- | ---------------------------------------- |
| Status         | Accepted                                 |
| Date           | 2026-06-02                               |
| Authors        | Nick Warila (@NWarila)                   |
| Decision-maker | Nick Warila (sole portfolio maintainer)  |
| Consulted      | None.                                    |
| Informed       | None.                                    |
| Reversibility  | Medium                                   |
| Review-by      | N/A (Accepted)                           |

## TL;DR

This image compiles `aws_signing_helper` (the AWS IAM Roles Anywhere credential
helper) **from source** inside the Dockerfile's `gobuild` stage with the
validated FIPS 140-3 **Go Cryptographic Module v1.0.0** (CMVP #5247): builder
`golang:1.25.10` pinned by `@sha256:`, `GOFIPS140=v1.0.0`, `CGO_ENABLED=1`,
`GOTOOLCHAIN=local`, and runtime `GODEBUG=fips140=on`. It does **not** copy a
prebuilt vendor binary the way the rest of the portfolio does, because the helper
is glibc-DYNAMIC by necessity and a prebuilt binary cannot carry `GOFIPS140`
provenance. The validated module exists only in Go 1.24/1.25, so Renovate caps
the `golang` builder below `1.26.0`. The upstream `v1.8.2` `go.mod` declares
`go 1.26.0`; the build reconciles that language-floor directive down to the
validated 1.24 toolchain (it does not patch source). The from-source binary
intentionally differs byte-for-byte from AWS's published reference binaries,
whose SHA256s are recorded in the manifest as a version reference only, not a
byte-match gate.

## Context and Problem Statement

The portfolio's UBI 9 application template ships a copy-verified-prebuilt model:
download a vendor release binary, verify its committed SHA256 (and signature
where available), and `COPY` it into the runtime. That model assumes (a) a
prebuilt binary exists for each target platform and (b) the binary's trust anchor
is its published checksum.

Neither assumption holds for a FIPS posture on `aws_signing_helper`:

1. **The helper is glibc-DYNAMIC, not static.** Its PKCS#11 and TPM code paths
   are compiled with cgo unconditionally. A `CGO_ENABLED=0` static build does not
   produce a working binary. Empirically, the produced ELF is dynamically linked
   against `libc.so.6` with interpreter `/lib64/ld-linux-x86-64.so.2`; the
   runtime `ubi-micro` supplies glibc.
2. **A prebuilt binary cannot carry `GOFIPS140` provenance we control.** AWS
   publishes a raw per-platform binary built on Amazon Linux 2023 with its own
   toolchain. We cannot assert from the outside that it was built with
   `GOFIPS140=v1.0.0` against the validated module; `go version -m` on the
   published artifact does not record our required FIPS build settings.
3. **The host-OpenSSL FIPS story is void on the target platform.** The Vault
   auto-unseal use case runs on Talos, not RHEL. RHEL's OpenSSL FIPS certificate
   (CMVP #4746) is bound to the RHEL operational environment and does not carry
   over to a Talos host. The portable FIPS story for a Go program is the Go
   Cryptographic Module (CMVP #5247), which is an OE-portable *runtime* module
   selected at build time with `GOFIPS140` — not a property of the base image.

So the helper needs a different build model than the template provides: compile
from source with the validated Go FIPS module, and prove the FIPS build
properties in the build itself.

## Decision Drivers

- FIPS 140-3 cryptography that is valid on the actual deployment OE (Talos), not
  only on RHEL.
- Provenance we can assert and gate on (`go version -m` showing
  `GOFIPS140=v1.0.0`, `CGO_ENABLED=1`, the upstream module path), rather than
  trusting an opaque vendor binary.
- Reuse of the portfolio's UBI 9 hardening, manifest, and supply-chain machinery
  wherever it still applies (rootfs assembly, rpmdb preservation, runtime
  hardening, SBOM/provenance/attestation/Cosign, OpenSCAP/Trivy/Grype gates).
- A fail-closed guard against silently building with an unvalidated crypto
  module if the Go builder is bumped.

## Considered Options

1. **Copy AWS's prebuilt `aws_signing_helper` binary** (the template default,
   as the chiseled predecessor did) and pin its SHA256.
2. **Compile from source with a non-FIPS Go toolchain** (`CGO_ENABLED=1`, no
   `GOFIPS140`).
3. **Compile from source with the validated FIPS 140-3 Go Cryptographic Module**
   (`GOFIPS140=v1.0.0`, `CGO_ENABLED=1`, `GODEBUG=fips140=on`) inside the
   Dockerfile, building each arch natively under buildx/QEMU. *(chosen)*

## Decision Outcome

Chosen option: **3 — compile from source with the validated FIPS module**.

The Dockerfile's `gobuild` stage (`FROM golang:1.25.10@sha256:...`) installs the
cgo C toolchain (`gcc`) plus `git`, clones the pinned upstream tag, builds with
`GOFIPS140=v1.0.0 CGO_ENABLED=1 GOTOOLCHAIN=local`, and then asserts the FIPS
build properties before the binary may reach the runtime stage:

- `go version -m` must record `GOFIPS140=v1.0.0` and `CGO_ENABLED=1`;
- the upstream module path must be present;
- the ELF must be dynamically linked (an interpreter must exist).

The runtime stage (`FROM ubi-micro AS runtime`) copies the assembled rootfs and
the binary, sets `ENV GODEBUG=fips140=on`, runs as `USER 65532:65532`, and uses
`ENTRYPOINT ["/usr/local/bin/aws_signing_helper"]` (the `serve` subcommand and
its flags are supplied as pod args, not baked in).

Building inside the Dockerfile lets buildx compile each arch natively under QEMU,
which avoids cgo cross-compilation entirely.

### go.mod directive reconciliation

Upstream `v1.8.2`'s `go.mod` declares `go 1.26.0` with `toolchain go1.26.2`. The
validated Go Cryptographic Module v1.0.0 (CMVP #5247) is selectable only in Go
1.24/1.25, and `GOTOOLCHAIN=local` (mandated so no unvalidated toolchain is ever
downloaded) means a `golang:1.25.10` builder refuses to build a module whose
language floor is `1.26.0`. The build therefore lowers the `go` directive to the
validated toolchain's language version and drops the `toolchain` pin
(`GO_MOD_GO_DIRECTIVE`, default `1.24.0`). This is a build-time reconciliation of
the **language floor** only; no source is patched. The build was validated
empirically: with the directive lowered, `golang:1.25.10` compiles the binary
and `go version -m` records `GOFIPS140=v1.0.0-c2097c7c` (the `-c2097c7c` snapshot
suffix is Go's identifier for the validated v1.0.0 module) and `CGO_ENABLED=1`.

### Go toolchain bump 1.24.13 -> 1.25.10 (stdlib security fixes)

The Go builder was bumped from `golang:1.24.13` to `golang:1.25.10` to pick up Go
1.25.10's standard-library security fixes. The 1.24.13 stdlib carried 12 fixable
HIGH-severity CVEs across `net/url`, `crypto/x509`, `crypto/tls`, `net`,
`golang.org/x/net/http2`, `net/mail`, and `net/http/httputil` (ReverseProxy DoS) —
CVE-2026-25679, -32280, -32281, -32283, -33811, -33814, -39820, -39823, -39825,
-39826, -39836, and -42499 — all of which compile into the from-source binary's
linked stdlib and are resolved by Go 1.25.10. The bump is **FIPS-preserving**: Go
1.25 still ships the validated Go Cryptographic Module v1.0.0 (CMVP #5247),
selected via `GOFIPS140=v1.0.0`, and 1.25.10 stays under the Renovate `<1.26.0`
cap that guards against an unvalidated Go 1.26 module being substituted. The
go.mod language-floor reconciliation above is unchanged: a 1.25.10 toolchain
builds the directive-lowered module exactly as the 1.24.13 toolchain did.

## Pros and Cons of the Options

### Option 1 — copy AWS prebuilt binary

- Good: simplest; matches the rest of the portfolio; byte-pinnable.
- Good: no Go toolchain in the build.
- Bad: cannot assert `GOFIPS140` provenance — the binary's crypto build settings
  are AWS's, not ours, and `go version -m` does not show our required FIPS flags.
- Bad: no FIPS 140-3 posture we can stand behind for the Talos OE.

### Option 2 — from source, non-FIPS toolchain

- Good: we control the build and its provenance.
- Good: avoids the go.mod directive reconciliation if a recent Go is used.
- Bad: no FIPS module — defeats the entire reason this image exists.

### Option 3 — from source, validated FIPS module (chosen)

- Good: OE-portable FIPS 140-3 cryptography valid on Talos (CMVP #5247),
  asserted in-build via `go version -m`.
- Good: reuses the portfolio's UBI hardening + supply-chain machinery.
- Good: native per-arch compile under buildx/QEMU avoids cgo cross-compilation.
- Bad: diverges from the template's prebuilt model (new `gobuild` stage, adapted
  manifest/generator/verify contracts).
- Bad: pinned below Go 1.26 until a newer validated module ships; requires the
  go.mod directive reconciliation for tags whose floor exceeds the toolchain.
- Bad: the from-source binary is not byte-identical to AWS's reference binary, so
  a byte-match gate is impossible.

## Confirmation

- `python tools/verify.py ci` gates the Dockerfile contract markers
  (`FROM ${GO_IMAGE} AS gobuild`, `GOFIPS140=v1.0.0`, `CGO_ENABLED=1`,
  `GOTOOLCHAIN=local`, `GODEBUG=fips140=on`, the `go version -m` assertion, the
  `ubi-micro` runtime, `USER 65532`, and the `aws_signing_helper` entrypoint),
  the manifest's `application.build` FIPS provenance, and the Renovate `<1.26.0`
  golang cap.
- The Dockerfile asserts `GOFIPS140=v1.0.0` + `CGO_ENABLED=1` + the module path +
  a dynamic ELF interpreter before the binary reaches the runtime stage; any
  drift fails the build.
- `bash tests/runtime-hardening.sh` confirms no shell / package manager /
  curl / wget, the rpmdb present, the CA bundle populated, non-root, and the
  expected entrypoint.
- `docker run --rm --network none <image> --help` exits cleanly, proving the
  glibc-DYNAMIC binary loads on `ubi-micro` with no network.

## Consequences

- A Go toolchain and cgo C toolchain are present in the (discarded) builder
  stage; the runtime carries only the compiled binary.
- The image manifest gains an `application.build` block and drops the prebuilt
  `application.artifacts`; the schema and `check_image_manifest.py` make
  `artifacts` optional for a from-source `go-binary` and require `build` instead.
- `generate_build_args.py` emits `GO_IMAGE`, `SOURCE_REPO`, and `SOURCE_REF`
  instead of prebuilt-binary checksum arguments; `ci.yaml`, the reusable, and
  `publish-image.yaml` compile the helper during the Dockerfile build.
- Bumping the upstream source ref may require revisiting the
  `GO_MOD_GO_DIRECTIVE` reconciliation if the new tag's language floor changes.

## Assumptions

- The Go Cryptographic Module v1.0.0 (CMVP #5247) remains Active and selectable
  via `GOFIPS140=v1.0.0` in Go 1.24/1.25.
- The upstream `aws_signing_helper` continues to build under the validated
  toolchain once its `go.mod` language floor is reconciled (validated for
  `v1.8.2`).
- The deployment runtime can set `seccompProfile: RuntimeDefault`, drop
  capabilities, and mount a read-only root filesystem.

## Supersedes

None.

## Superseded by

None.

## Implementing PRs

- This repository's initial content PR (`feat/ubi9-helper-content`).

## Related ADRs

- Template [ADR-0001](../template/0001-replace-chisel-with-ubi9.md) — UBI 9 base
  selection and the rootfs/rpmdb/CA-bundle invariants this image reuses.
- Template [ADR-0002](../template/0002-compliance-gate-openscap-rhel9-stig.md) —
  the OpenSCAP DISA RHEL 9 STIG release gate this image inherits.
- Template [ADR-0003](../template/0003-publish-image-per-image-frozen-cosign-identity.md)
  — the frozen `publish-image.yaml` Cosign identity this image preserves.

## Compliance Notes

- FIPS 140-3: the cryptography is provided by the validated Go Cryptographic
  Module v1.0.0 (CMVP certificate #5247, Active), selected at build with
  `GOFIPS140=v1.0.0` and run in approved mode with `GODEBUG=fips140=on`. This is
  an OE-portable runtime module: it remains valid on the Talos deployment OE,
  unlike RHEL's OpenSSL FIPS certificate (#4746), which is bound to the RHEL OE.
- The Renovate `<1.26.0` cap on the `golang` builder is the fail-closed guard
  that prevents an unvalidated Go 1.26 module from being substituted silently.
- DISA RHEL 9 STIG and CIS Docker image applicability are tracked in
  `docs/compliance/` and gated by the OpenSCAP profile in `publish-image.yaml`.
