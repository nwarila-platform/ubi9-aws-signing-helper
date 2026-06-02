# Build The Image

This repository builds `aws_signing_helper` **FROM SOURCE** with the validated
FIPS 140-3 Go Cryptographic Module inside the Dockerfile (see
[repo ADR-0001](../decision-records/repo/0001-helper-go-native-fips.md)). Unlike
the copy-verified-prebuilt template, there is no `dist/` binary and no
`build_app.sh` / `verify_app_shas.py` step: `docker buildx` clones and compiles
the helper natively per architecture (under QEMU for cross-arch).

## End-To-End

```sh
make image
```

This runs:

1. `tools/build_image.sh` - renders the docker buildx flags from the manifest
   via `tools/generate_build_args.py` (UBI bases, dnf package set, and the
   `GO_IMAGE` / `SOURCE_REPO` / `SOURCE_REF` from `application.build`), then runs
   `docker buildx build` for `linux/amd64` and loads the result into the local
   Docker daemon for testing. Inside the build, the `gobuild` stage clones the
   pinned upstream tag, compiles with `GOFIPS140=v1.0.0 CGO_ENABLED=1
   GOTOOLCHAIN=local`, and asserts the FIPS build properties (`go version -m`
   showing `GOFIPS140=v1.0.0` + `CGO_ENABLED=1`, the source module path, and a
   dynamic ELF interpreter) before the binary reaches the runtime stage.
2. `tests/runtime-hardening.sh` - exports the rootfs of the built image and
   asserts no shell, no dnf/microdnf/rpm/yum, no curl or wget, the rpmdb present,
   the CA bundle populated, a non-root runtime user, and the expected entrypoint.

The local `--load` path is not an evidence path. Docker does not preserve
BuildKit SBOM attestations in the local image store, and the helper disables
BuildKit provenance explicitly. Use
[`publish-image.md`](publish-image.md) when wiring a downstream release job.

## Inputs (Manifest Pins)

The reviewed `examples/image-manifest.json` is the single source of truth:

1. Pin the `ubi-minimal` builder image by digest in `base.builder`.
2. Pin the `ubi-micro` runtime image by digest in `base.runtime`.
3. Choose the minimum `dnf.packages` the runtime rootfs needs (here just
   `ca-certificates`). Add `dnf.repos` only if the build must enable specific
   repository IDs exclusively instead of the base image's defaults.
4. Record the from-source build provenance under `application.build`: the
   `go_image` (pinned `golang` tag@sha256, capped below Go 1.26 by Renovate so
   the validated `GOFIPS140` module stays valid), `gofips140`, `cgo_enabled`,
   `godebug`, `source_repo`, and `source_ref`. There is no prebuilt
   `application.artifacts`; `verification.type` is `none` with a note explaining
   the from-source FIPS build.

Do not pass secrets through Docker build args. If a future build needs private
fetch credentials, use BuildKit secrets and keep them out of the final image and
provenance-visible build arguments.

### Build From The Manifest

The recommended pattern reads the build args from the manifest rather than
duplicating them:

```sh
# Single-platform build that loads the image into the local Docker daemon.
bash tools/build_image.sh path/to/image-manifest.json my-image:dev linux/amd64
```

To bypass the helper and call docker buildx directly in a release workflow that
needs `--push`, multi-platform output, and BuildKit attestations:

```sh
mapfile -t buildargs < <(python tools/generate_build_args.py path/to/image-manifest.json)

docker buildx build \
  --file containers/Dockerfile \
  --tag ghcr.io/<owner>/<image>:<version> \
  "${buildargs[@]}" \
  --provenance=mode=max \
  --sbom=true \
  --push \
  .
```

`tools/generate_build_args.py` emits one token per line (alternating
`--build-arg` and `KEY=VALUE`) so that `mapfile -t` produces an array suitable
for `"${buildargs[@]}"` expansion without shell-quoting concerns. Use
`--format=json` instead when feeding values into a GitHub Actions matrix.

The Dockerfile's `gobuild` stage compiles the helper for the active `TARGETARCH`
natively (buildx runs it under QEMU for cross-arch), and fails the build if the
`go version -m` FIPS assertions do not hold.

## Verify Runtime Hardening

```sh
tests/runtime-hardening.sh <image-ref>
```

The script exports the image filesystem and checks for forbidden runtime tools
without needing the application to start successfully.
