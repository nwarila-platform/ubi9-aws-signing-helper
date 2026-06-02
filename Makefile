.PHONY: help verify ci manifest docs dockerfile build-args image-build image-test image clean

# Path to the reviewed image manifest. Override to point at a different manifest.
MANIFEST     ?= examples/image-manifest.json
IMAGE_TAG    ?= ubi9-aws-signing-helper:local
APP_PLATFORM ?= linux/amd64

help:
	@printf '%s\n' \
		'Contract checks (no Docker required):' \
		'  verify     Run the full local verification surface' \
		'  ci         Alias for verify' \
		'  manifest   Validate the image manifest contract' \
		'  docs       Validate documentation layout' \
		'  dockerfile Validate Dockerfile contract markers' \
		'  build-args Render docker buildx flags from the manifest' \
		'' \
		'End-to-end image lifecycle (Docker required):' \
		'  image-build Build the OCI image for $$APP_PLATFORM (compiles the helper' \
		'              from source with the FIPS Go module inside the Dockerfile)' \
		'  image-test  Run runtime-hardening assertions against the built image' \
		'  image       image-build + image-test' \
		'  clean       Remove dist/ build outputs'

verify:
	python tools/verify.py verify

ci:
	python tools/verify.py ci

manifest:
	python tools/check_image_manifest.py $(MANIFEST)

docs:
	python tools/verify.py docs-layout

dockerfile:
	python tools/verify.py dockerfile-contract

build-args:
	python tools/generate_build_args.py $(MANIFEST)

image-build:
	bash tools/build_image.sh '$(MANIFEST)' '$(IMAGE_TAG)' '$(APP_PLATFORM)'

image-test:
	bash tests/runtime-hardening.sh '$(IMAGE_TAG)' /usr/local/bin/aws_signing_helper

image: image-build image-test

clean:
	rm -rf dist
