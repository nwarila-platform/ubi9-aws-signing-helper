# Build The Image

This repository builds `aws_signing_helper` from upstream source inside
`containers/Dockerfile` with the validated FIPS 140-3 Go Cryptographic Module.
The local build path compiles the helper during `docker buildx build`; there is
no separate application-binary staging step.

## End-To-End

```sh
make image
```

This runs:

1. `tools/build_image.sh`, which calls `tools/generate_build_args.py` to render
   Docker Buildx flags from `examples/image-manifest.json`, then builds the UBI
   9 image for `linux/amd64` and loads it into the local Docker daemon.
2. `tests/runtime-hardening.sh`, which exports the built image rootfs and checks
   for the runtime hardening contract.

Inside the Dockerfile, the `gobuild` stage checks out the manifest-pinned
`SOURCE_COMMIT` (resolved from release tag `SOURCE_REF`) and fails closed unless
the checkout `HEAD` equals that commit, reconciles the upstream `go.mod`
directive to the validated toolchain's language level, and compiles with:

```sh
GOFIPS140=v1.0.0 CGO_ENABLED=1 GOTOOLCHAIN=local
```

The build fails before runtime assembly unless `go version -m` records
`GOFIPS140=v1.0.0`, `CGO_ENABLED=1`, and the upstream module path, and unless
`readelf` finds a dynamic ELF interpreter.

## Inputs

The reviewed manifest is the single source of truth for build inputs:

1. `base.builder` pins the `ubi-minimal` builder image by digest.
2. `base.runtime` pins the `ubi-micro` runtime image by digest.
3. `dnf.packages` lists the minimum RPM package set for the runtime rootfs.
4. `application.build.go_image` pins the Go builder image by tag and digest.
5. `application.build.source_repo`, `application.build.source_ref`, and
   `application.build.source_commit` select and pin the upstream helper source;
   the Dockerfile checks out `source_commit` and fails closed on mismatch.
6. `runtime.user`, `runtime.entrypoint`, and `runtime.forbidden_executables`
   define the runtime hardening contract.

`application.verification.type` is currently `none`. That is intentional and
honest: the upstream source IS pinned to an immutable commit SHA
(`source_commit`, enforced fail-closed), and this build asserts FIPS/cgo/module
provenance on the compiled binary, but it does not verify a signed upstream
source checksum or a publisher tag signature (upstream `v1.8.2` is a lightweight
tag with no signed tag object).

Do not pass secrets through Docker build args. BuildKit max provenance can
expose build argument values. If a future build needs private fetch credentials,
use BuildKit secrets and keep them out of the final image and provenance-visible
arguments.

## Build From A Manifest

Use the helper for local runtime testing:

```sh
bash tools/build_image.sh examples/image-manifest.json ubi9-aws-signing-helper:dev linux/amd64
```

To call Docker Buildx directly in a release workflow that needs registry push,
multi-platform output, and BuildKit attestations:

```sh
mapfile -t buildargs < <(python tools/generate_build_args.py examples/image-manifest.json)

docker buildx build \
  --file containers/Dockerfile \
  --tag ghcr.io/OWNER/ubi9-aws-signing-helper:VERSION \
  "${buildargs[@]}" \
  --provenance=mode=max \
  --sbom=true \
  --push \
  .
```

`tools/generate_build_args.py` emits one token per line so `mapfile -t`
produces an array suitable for `"${buildargs[@]}"` expansion. Use
`--format=json` when a workflow needs structured values.

## Verify Runtime Hardening

```sh
tests/runtime-hardening.sh <image-ref> /usr/local/bin/aws_signing_helper
```

The script inspects the exported image filesystem for forbidden tools, rpmdb and
CA bundle presence, non-root execution, dropped capabilities guidance,
read-only-rootfs compatibility, setuid/setgid files, and expected entrypoint
metadata.
