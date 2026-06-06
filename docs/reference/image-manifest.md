# Image Manifest Contract

The image manifest is the review surface for this repository's Docker build
inputs. The committed manifest is
[`examples/image-manifest.json`](../../examples/image-manifest.json), and the
schema is
[`contracts/image-manifest.schema.json`](../../contracts/image-manifest.schema.json).

## Required Sections

The manifest is schema v2 (`schema_version` is `"2.0"`).

| Section | Purpose |
| --- | --- |
| `image` | Image name, RHEL version (`9`), and supported platforms. |
| `base.builder` | Digest-pinned `ubi-minimal` image used to assemble the runtime rootfs. |
| `base.runtime` | Digest-pinned `ubi-micro` final runtime image. |
| `dnf.packages` | Exact package list installed into the runtime rootfs with `microdnf --installroot`. |
| `dnf.repos` | Optional repository IDs to enable exclusively. |
| `application` | Helper name/version, final binary path, from-source Go build pins, and verification status. |
| `runtime` | Non-root user, entrypoint, and forbidden executable baseline. |
| `evidence` | Required release evidence types. |

`base.builder` and `base.runtime` must both be `@sha256`-pinned references. The
builder is `ubi-minimal` because it carries `microdnf`; the runtime is
`ubi-micro` because it keeps the final image small and package-manager-free.

## Application Build Block

This repository uses `application.source: "go-binary"` with
`application.build`:

| Field | Purpose |
| --- | --- |
| `go_version` | Reviewed Go toolchain version. |
| `go_image` | Digest-pinned Go builder image consumed by the Dockerfile. |
| `gofips140` | Expected Go FIPS module selector (`v1.0.0`). |
| `cgo_enabled` | Expected cgo setting (`1`) because the helper is glibc-dynamic. |
| `godebug` | Runtime FIPS activation value (`fips140=on`). |
| `source_repo` | Upstream AWS helper repository cloned by the Dockerfile. |
| `source_ref` | Upstream release tag cloned by the Dockerfile. |

`tools/generate_build_args.py` converts these fields into Docker Buildx
arguments. `containers/Dockerfile` then compiles the helper and asserts
`GOFIPS140`, `CGO_ENABLED`, the upstream module path, and dynamic ELF linkage
before copying the binary into the runtime stage.

## Verification Field

The committed manifest uses:

```json
"verification": {
  "type": "none",
  "note": "Built FROM SOURCE inside containers/Dockerfile ..."
}
```

That value is intentionally literal. The build proves local FIPS/cgo/module
provenance for the compiled binary, but it does not verify a signed upstream
source checksum or pin `SOURCE_REF` to a commit SHA.

The schema still recognizes stronger verification modes for repositories that
implement them:

| Mode | Use When |
| --- | --- |
| `checksum` | The upstream artifact has a trusted checksum source. |
| `checksum-signature` | The upstream publishes signed checksums and the build verifies them. |
| `pgp-signature` | The upstream publishes detached PGP signatures and the build verifies them. |
| `sigstore-bundle` | The upstream publishes Sigstore bundle evidence and the build verifies it. |
| `none` | No upstream artifact signature/checksum verification is implemented. |

## From Manifest To Docker Buildx

```sh
python tools/generate_build_args.py examples/image-manifest.json
```

The default output emits one token per line for shell array consumption. The
alternate `--format=json` mode produces a structured object for workflow logic.
See [`build-image.md`](../how-to/build-image.md) for concrete local and release
invocations.
