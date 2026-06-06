#!/usr/bin/env python3
"""Generate docker buildx build flags from a reviewed image manifest.

The image manifest is the single human-reviewable source of truth for the pins
that produce this UBI 9 image. This image compiles aws_signing_helper FROM
SOURCE inside the Dockerfile with the validated FIPS 140-3 Go Cryptographic
Module, so the build args carry the UBI bases, the dnf package set, and the Go
toolchain + source pins from application.build -- NOT a prebuilt
APP_BINARY/APP_SHA256 pair (there is no committed dist/ binary to copy).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import check_image_manifest


class GenerateError(Exception):
    """Raised when the manifest cannot be turned into build args."""


def build_invocation(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a structured docker buildx invocation derived from the manifest.

    The shape is intentionally small: a list of platforms plus an ordered map
    of build args. Consumers can render it as `--build-arg` flags or use the
    JSON form directly (for example, in a GitHub Actions matrix).
    """

    image = manifest["image"]
    base = manifest["base"]
    dnf = manifest["dnf"]
    application = manifest["application"]
    build = application.get("build")
    if build is None:
        raise GenerateError(
            "application.build is required for the from-source build model "
            "(this image compiles aws_signing_helper inside the Dockerfile)"
        )

    build_args: dict[str, str] = {}
    build_args["UBI_MINIMAL_IMAGE"] = base["builder"]
    build_args["UBI_MICRO_IMAGE"] = base["runtime"]
    build_args["DNF_PACKAGES"] = " ".join(dnf["packages"])
    build_args["DNF_REPOS"] = " ".join(dnf.get("repos", []))

    # Go toolchain + source pins for the from-source FIPS compile stage.
    go_image = build.get("go_image")
    if not go_image:
        raise GenerateError("application.build.go_image must be set for the from-source build")
    build_args["GO_IMAGE"] = go_image
    build_args["SOURCE_REPO"] = build["source_repo"]
    build_args["SOURCE_REF"] = build["source_ref"]
    build_args["SOURCE_COMMIT"] = build["source_commit"]

    build_args["OCI_TITLE"] = image["name"]

    return {
        "platforms": list(image["platforms"]),
        "build_args": build_args,
    }


def render_docker_buildx(invocation: dict[str, Any]) -> str:
    """Render as one token per line for `mapfile -t` consumption.

    Each flag and its value occupy adjacent lines so that values containing
    spaces (notably DNF_PACKAGES) survive intact when read into a bash array.
    """

    lines: list[str] = []
    if invocation["platforms"]:
        lines.append("--platform")
        lines.append(",".join(invocation["platforms"]))
    for key, value in invocation["build_args"].items():
        lines.append("--build-arg")
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def render_json(invocation: dict[str, Any]) -> str:
    return json.dumps(invocation, indent=2, sort_keys=False) + "\n"


RENDERERS = {
    "docker-buildx": render_docker_buildx,
    "json": render_json,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--format",
        choices=sorted(RENDERERS),
        default="docker-buildx",
        help="output format (default: docker-buildx for mapfile consumption)",
    )
    parser.add_argument(
        "--template",
        action="store_true",
        help="allow REPLACE_WITH_* markers from the starter manifest",
    )
    args = parser.parse_args()

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        check_image_manifest.validate_manifest(manifest, template=args.template)
        invocation = build_invocation(manifest)
    except (OSError, json.JSONDecodeError, check_image_manifest.ManifestError, GenerateError) as exc:
        print(f"generate build args failed: {exc}", file=sys.stderr)
        return 1

    # Always emit LF endings: this output feeds bash `mapfile -t` and docker
    # buildx invocations that run inside Linux containers, where a stray CR
    # would corrupt argument parsing.
    sys.stdout.buffer.write(RENDERERS[args.format](invocation).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
