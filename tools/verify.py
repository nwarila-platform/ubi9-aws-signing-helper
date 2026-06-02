#!/usr/bin/env python3
"""Local verification entrypoint for ubi9-aws-signing-helper.

This image diverges from the template's copy-verified-prebuilt model: the
aws_signing_helper binary is compiled FROM SOURCE inside the Dockerfile with the
validated FIPS 140-3 Go Cryptographic Module (GOFIPS140=v1.0.0, CMVP #5247,
CGO_ENABLED=1, GODEBUG=fips140=on). The contract checks below are adapted to
that compile-in-Dockerfile model: there is no build_app.sh prebuilt step and no
APP_BINARY/APP_SHA256 build args.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"

DOC_DIRS = [
    "docs/compliance",
    "docs/decision-records/org",
    "docs/decision-records/template",
    "docs/decision-records/repo",
    "docs/explanation",
    "docs/how-to",
    "docs/reference",
    "docs/tutorials",
]

ADR_HEADINGS = [
    "## TL;DR",
    "## Context and Problem Statement",
    "## Decision Drivers",
    "## Considered Options",
    "## Decision Outcome",
    "## Pros and Cons of the Options",
    "## Confirmation",
    "## Consequences",
    "## Assumptions",
    "## Supersedes",
    "## Superseded by",
    "## Implementing PRs",
    "## Related ADRs",
    "## Compliance Notes",
]

# Org ADRs every nwarila-platform consumer must mirror from
# nwarila-platform/.github. This local verifier checks presence, not byte
# identity against the org source.
EXPECTED_ORG_ADRS = {"0001", "0002", "0003", "0004", "0005"}


class VerifyError(Exception):
    """Raised when a verification target fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def _load_tool(module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, TOOLS_DIR / f"{module_name}.py")
    if spec is None or spec.loader is None:
        raise VerifyError(f"unable to load tools/{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def check_docs_layout() -> None:
    for directory in DOC_DIRS:
        require((ROOT / directory).is_dir(), f"missing docs directory: {directory}")

    require((ROOT / "docs/README.md").is_file(), "missing docs/README.md")
    require((ROOT / "docs/decision-records/README.md").is_file(), "missing ADR index")
    for document in (
        "docs/how-to/derive-image-repo.md",
        "docs/how-to/build-image.md",
        "docs/how-to/publish-image.md",
        "docs/reference/governance.md",
        "docs/reference/quality-gates.md",
        "docs/reference/supply-chain-evidence.md",
        "docs/compliance/README.md",
        "docs/compliance/cis-docker-image-applicability.md",
        "docs/compliance/rhel-9-stig-v2r8-applicability.md",
    ):
        require((ROOT / document).is_file(), f"missing required documentation: {document}")

    org_adrs = sorted((ROOT / "docs/decision-records/org").glob("[0-9][0-9][0-9][0-9]-*.md"))
    present_org_adrs = {adr.name[:4] for adr in org_adrs}
    missing_org_adrs = sorted(EXPECTED_ORG_ADRS - present_org_adrs)
    require(
        not missing_org_adrs,
        "missing mirrored org ADRs under docs/decision-records/org: "
        + ", ".join(missing_org_adrs),
    )

    # The from-source FIPS decision is repo-specific; require at least one
    # repo-scoped ADR and the full MADR heading set on every template- and
    # repo-scoped ADR.
    repo_adrs = sorted((ROOT / "docs/decision-records/repo").glob("[0-9][0-9][0-9][0-9]-*.md"))
    require(repo_adrs, "missing repo-scoped ADR under docs/decision-records/repo")

    for scope in ("template", "repo"):
        for adr in (ROOT / "docs/decision-records" / scope).glob("[0-9][0-9][0-9][0-9]-*.md"):
            text = adr.read_text(encoding="utf-8")
            missing = [heading for heading in ADR_HEADINGS if heading not in text]
            require(not missing, f"{adr.relative_to(ROOT)} missing ADR headings: {', '.join(missing)}")


def check_manifest() -> None:
    # The committed example manifest carries real, working pins so this image
    # builds end-to-end; validate it in strict mode so any future regression
    # that reintroduces REPLACE_WITH_* markers is caught here.
    run([sys.executable, "tools/check_image_manifest.py", "examples/image-manifest.json"])

    # The shared validator still supports template mode (a derived repo fills in
    # its own pins). Exercise it in-process against a synthetic manifest so the
    # permissive path is regression-tested without committing a second fixture.
    validator = _load_tool("check_image_manifest")
    manifest = json.loads((ROOT / "examples/image-manifest.json").read_text(encoding="utf-8"))
    manifest["base"]["builder"] = "registry.access.redhat.com/ubi9/ubi-minimal@sha256:REPLACE_WITH_DIGEST"
    validator.validate_manifest(manifest, template=True)


def check_dockerfile_contract() -> None:
    dockerfile = ROOT / "containers/Dockerfile"
    require(dockerfile.is_file(), "missing containers/Dockerfile")
    text = dockerfile.read_text(encoding="utf-8")

    # UBI 9 runtime + from-source FIPS gobuild contract markers.
    required_markers = [
        "FROM ${UBI_MINIMAL_IMAGE} AS rpm-rootfs",
        "FROM ${GO_IMAGE} AS gobuild",
        "FROM ${UBI_MICRO_IMAGE} AS runtime",
        "microdnf install -y --installroot=/rootfs",
        "DNF_PACKAGES",
        "GOFIPS140=v1.0.0",
        "CGO_ENABLED=1",
        "GOTOOLCHAIN=local",
        "GODEBUG=fips140=on",
        "git clone --depth 1 --branch",
        "go build -trimpath -o /out/aws_signing_helper",
        "go version -m /out/aws_signing_helper",
        "COPY --from=rpm-rootfs /rootfs/ /",
        "COPY --from=gobuild /out/aws_signing_helper /usr/local/bin/aws_signing_helper",
        "USER 65532:65532",
        "ENTRYPOINT [\"/usr/local/bin/aws_signing_helper\"]",
        "BUILDKIT_SBOM_SCAN_CONTEXT=true",
    ]
    missing = [marker for marker in required_markers if marker not in text]
    require(not missing, f"Dockerfile missing contract markers: {', '.join(missing)}")

    # The Go builder image must be pinned tag@sha256 in the manifest-fed ARG.
    require(
        re.search(r"golang:[A-Za-z0-9._-]+@sha256:[a-f0-9]{64}", text) is not None
        or "ARG GO_IMAGE" in text,
        "Dockerfile must consume a pinned GO_IMAGE build arg",
    )

    require("SECRET" not in text.upper(), "Dockerfile must not define secret build args")
    require("PASSWORD" not in text.upper(), "Dockerfile must not contain password markers")
    require("TOKEN" not in text.upper(), "Dockerfile must not contain token markers")
    # Prebuilt-binary markers must NOT appear: this image compiles from source.
    require("APP_BINARY" not in text, "Dockerfile must not COPY a prebuilt APP_BINARY; compile from source")
    require("APP_SHA256" not in text, "Dockerfile must not define APP_SHA256; the binary is compiled from source")
    # The rpm database (/var/lib/rpm) and dnf history (/var/lib/dnf) MUST survive
    # into the runtime so Trivy/Grype/OpenSCAP enumerate the installed packages.
    require(
        "rm -rf /rootfs/var/lib/rpm" not in text,
        "Dockerfile must not delete /rootfs/var/lib/rpm (scanners would see zero packages)",
    )
    require(
        "rm -rf /rootfs/var/lib/dnf" not in text,
        "Dockerfile must not delete /rootfs/var/lib/dnf (scanners would see zero packages)",
    )
    require("apt-get update; \\\n    apt-get install" in text, "apt-get update must be paired with apt-get install")

    dockerignore = ROOT / ".dockerignore"
    require(dockerignore.is_file(), "missing .dockerignore")

    # BUILDKIT_SBOM_SCAN_STAGE is a per-stage ARG. It must appear inside the
    # rpm-rootfs and gobuild builder stages with value true.
    builder_stages = (
        ("rpm-rootfs", "FROM ${UBI_MINIMAL_IMAGE} AS rpm-rootfs"),
        ("gobuild", "FROM ${GO_IMAGE} AS gobuild"),
    )
    for stage, marker in builder_stages:
        require(marker in text, f"Dockerfile missing builder stage '{stage}'")
        stage_body = text.split(marker, 1)[1].split("\nFROM ", 1)[0]
        require(
            "ARG BUILDKIT_SBOM_SCAN_STAGE=true" in stage_body,
            f"stage '{stage}' must declare ARG BUILDKIT_SBOM_SCAN_STAGE=true so BuildKit scans it",
        )


def check_runtime_script() -> None:
    script = ROOT / "tests/runtime-hardening.sh"
    require(script.is_file(), "missing tests/runtime-hardening.sh")
    text = script.read_text(encoding="utf-8")
    for path in [
        "/bin/sh",
        "/bin/bash",
        "/usr/bin/sh",
        "/usr/bin/bash",
        "/usr/bin/dnf",
        "/usr/bin/microdnf",
        "/usr/bin/rpm",
        "/usr/bin/yum",
        "/usr/bin/curl",
        "/usr/bin/wget",
    ]:
        require(path in text, f"runtime hardening script does not assert absence of {path}")
    # The /bin -> /usr/bin symlink means a shell at /usr/bin/bash also answers
    # /bin/bash; require the generic shell-anywhere scan so the real path is caught.
    require(
        "s?bin/(sh|bash|dash" in text,
        "runtime hardening must scan for a shell binary at any bin/sbin path",
    )
    # The rpm database must be asserted PRESENT (preserved for scanners), and the
    # RHEL CA bundle must be asserted populated (the helper's TLS to AWS endpoints
    # depends on it; the Debian /etc/ssl/certs path does not exist on UBI).
    require("/var/lib/rpm" in text, "runtime hardening must assert the rpm database is present")
    require(
        "/etc/pki/tls/certs/ca-bundle.crt" in text,
        "runtime hardening must assert the UBI CA bundle at /etc/pki/tls/certs/ca-bundle.crt",
    )


def check_compliance_checklist() -> None:
    # The RHEL 9 STIG + CIS applicability checklists are gated by their own tool,
    # which cross-checks the committed docs against the pinned DISA source hash,
    # rule count, STIG-ID format, and decision-coverage rules.
    run([sys.executable, "tools/check_compliance_checklist.py"])


# Build args that the Dockerfile reads from the build runtime (date, git, CI
# context) rather than from the reviewed manifest. The generator is not
# expected to emit these; they are populated by the publish-image.yaml release
# workflow. GO_MOD_GO_DIRECTIVE has a Dockerfile default and is a build-time
# reconciliation knob, not a manifest field.
RUNTIME_ONLY_ARGS = {
    "BUILDKIT_SBOM_SCAN_CONTEXT",
    "BUILDKIT_SBOM_SCAN_STAGE",
    "TARGETARCH",
    "DNF_REPOS",
    "GO_MOD_GO_DIRECTIVE",
    "OCI_CREATED",
    "OCI_DESCRIPTION",
    "OCI_REVISION",
    "OCI_SOURCE",
    "OCI_VERSION",
}


def check_build_tool_pins() -> None:
    manifest = json.loads((ROOT / "examples/image-manifest.json").read_text(encoding="utf-8"))
    application = manifest["application"]
    require(application["source"] == "go-binary", "helper image must be a from-source go-binary")
    require(application["name"] == "aws_signing_helper", "application.name must be aws_signing_helper")
    require(application["version"], "application.version must be set")

    build = application.get("build")
    require(build is not None, "from-source helper must carry application.build provenance")
    require(build["gofips140"] == "v1.0.0", "application.build.gofips140 must be v1.0.0 (validated CMVP #5247 module)")
    require(build["cgo_enabled"] == "1", "application.build.cgo_enabled must be '1' (aws_signing_helper is cgo-dynamic)")
    require(build.get("godebug") == "fips140=on", "application.build.godebug must be fips140=on")
    require(
        build["source_repo"] == "github.com/aws/rolesanywhere-credential-helper",
        "application.build.source_repo must be the upstream rolesanywhere-credential-helper",
    )
    require(
        re.fullmatch(r"v\d+\.\d+\.\d+", build["source_ref"]) is not None,
        f"application.build.source_ref must be a release tag (vX.Y.Z): {build['source_ref']}",
    )
    require(
        re.fullmatch(r"golang:[A-Za-z0-9._-]+@sha256:[a-f0-9]{64}", build["go_image"]) is not None,
        "application.build.go_image must be a pinned golang tag@sha256",
    )
    # The validated Go Cryptographic Module v1.0.0 (CMVP #5247) exists only in
    # Go 1.24/1.25; Go 1.26 introduces an unvalidated module. Guard the pin.
    go_tag = build["go_image"].split("@", 1)[0].split(":", 1)[1]
    require(
        not go_tag.startswith("1.26") and not go_tag.startswith("1.27"),
        f"go_image must stay below Go 1.26 for the validated GOFIPS140 module; got {go_tag}",
    )

    verification = application["verification"]
    require(verification["type"] == "none", "from-source helper verification.type must be 'none'")
    require(
        "note" in verification and "GOFIPS140=v1.0.0" in verification["note"],
        "verification.note must explain the from-source FIPS build",
    )

    # Renovate must cap the golang datasource below 1.26 so the validated module
    # is never bumped out from under the build.
    renovate = (ROOT / ".github/renovate.json5").read_text(encoding="utf-8")
    require('"matchDatasources": ["docker"]' in renovate, "Renovate must track the docker datasource")
    require('"matchDepNames": ["golang"]' in renovate, "Renovate must match the golang dep")
    require('"allowedVersions": "<1.26.0"' in renovate, "Renovate must cap golang below 1.26.0 (GOFIPS140 guard)")
    require("currentDigest" in renovate, "Renovate must track the golang image digest")


def check_build_args_generator() -> None:
    generator = _load_tool("generate_build_args")
    manifest_path = ROOT / "examples/image-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    invocation = generator.build_invocation(manifest)
    build_args = invocation["build_args"]
    platforms = invocation["platforms"]

    require(platforms == manifest["image"]["platforms"], "generator must echo image.platforms verbatim")

    # From-source build args: UBI bases + dnf set + Go toolchain/source pins.
    expected_keys = {
        "UBI_MINIMAL_IMAGE",
        "UBI_MICRO_IMAGE",
        "DNF_PACKAGES",
        "DNF_REPOS",
        "GO_IMAGE",
        "SOURCE_REPO",
        "SOURCE_REF",
        "OCI_TITLE",
    }
    missing = sorted(expected_keys - set(build_args))
    require(not missing, f"generator missing build args: {', '.join(missing)}")

    # No prebuilt-binary args in the from-source model.
    leaked = sorted(k for k in build_args if k.startswith("APP_BINARY") or k.startswith("APP_SHA256"))
    require(not leaked, f"from-source generator must not emit prebuilt args: {', '.join(leaked)}")

    # Every Dockerfile ARG that is not runtime-only must have a manifest-derived
    # value, and vice versa.
    dockerfile_args = set(re.findall(r"^\s*ARG\s+([A-Z][A-Z0-9_]*)", (ROOT / "containers/Dockerfile").read_text(encoding="utf-8"), re.MULTILINE))
    expected_from_dockerfile = dockerfile_args - RUNTIME_ONLY_ARGS
    missing_from_generator = sorted(expected_from_dockerfile - set(build_args))
    require(
        not missing_from_generator,
        f"Dockerfile defines ARGs the generator does not emit: {', '.join(missing_from_generator)} (add to manifest or RUNTIME_ONLY_ARGS)",
    )
    unknown_from_generator = sorted(set(build_args) - dockerfile_args)
    require(
        not unknown_from_generator,
        f"generator emits build args the Dockerfile does not declare: {', '.join(unknown_from_generator)}",
    )

    # JSON form must round-trip the same structure.
    rendered_json = generator.render_json(invocation)
    decoded = json.loads(rendered_json)
    require(decoded == invocation, "json renderer must round-trip the invocation structure")

    # docker-buildx form pairs each flag with its value on adjacent lines.
    rendered = generator.render_docker_buildx(invocation).splitlines()
    require(rendered[0] == "--platform", "docker-buildx output must lead with --platform")
    require(rendered[1] == ",".join(platforms), "docker-buildx --platform value must follow on the next line")
    flag_value_pairs = rendered[2:]
    require(len(flag_value_pairs) % 2 == 0, "docker-buildx --build-arg flags and values must be paired")
    for index in range(0, len(flag_value_pairs), 2):
        require(flag_value_pairs[index] == "--build-arg", f"expected --build-arg at line {index + 3}")
        pair = flag_value_pairs[index + 1]
        require("=" in pair, f"build arg pair at line {index + 4} must be KEY=VALUE")


def check_local_build_helper() -> None:
    helper = ROOT / "tools/build_image.sh"
    require(helper.is_file(), "missing tools/build_image.sh")
    text = helper.read_text(encoding="utf-8")
    require("--load" in text, "local image helper must load the image for runtime tests")
    require("--provenance=false" in text, "local image helper must disable BuildKit provenance")
    forbidden_markers = ["--provenance=mode=max", "--sbom=true", "--attest"]
    present = [marker for marker in forbidden_markers if marker in text]
    require(
        not present,
        "local image helper must not pretend to emit release attestations: " + ", ".join(present),
    )


def check_stale_placeholders() -> None:
    tokens = ["TO" + "DO", "FIX" + "ME", "CHANGE" + "ME", r"YOUR_[A-Z0-9_]+"]
    pattern = re.compile(r"\b(" + "|".join(tokens) + r")\b")
    ignored_parts = {".git"}
    checked_suffixes = {".md", ".py", ".sh", ".json", ".json5", ".yaml", ".yml"}
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if any(part in ignored_parts for part in path.parts):
            continue
        if not path.is_file() or (path.suffix.lower() not in checked_suffixes and path.name != "Dockerfile"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                findings.append(f"{path.relative_to(ROOT)}:{line_no}: {line.strip()}")
    require(not findings, "stale placeholders found:\n" + "\n".join(findings))


# Universal quality-gate caller workflows. nwarila-platform repos use reusable
# workflows hosted in nwarila-platform/.github and pinned by 40-char SHA.
ORG_REUSABLE_CALLER_WORKFLOWS = {
    "codeql.yaml": "reusable-codeql.yaml",
    "scorecard.yaml": "reusable-scorecard.yaml",
    "security.yaml": "reusable-iac-security.yaml",
    "auto-merge.yaml": "reusable-auto-merge.yaml",
    "repo-hygiene.yaml": "reusable-repo-hygiene.yaml",
}

REUSABLE_USES_PATTERN = re.compile(
    r"uses:\s+nwarila-platform/\.github/\.github/workflows/(?P<reusable>reusable-[a-z0-9-]+\.yaml)@(?P<sha>[0-9a-f]{40})\b"
)
EXTERNAL_USES_PATTERN = re.compile(r"uses:\s+(?P<target>(?!\./)[^@\s]+)@(?P<ref>[^\s#]+)")


def check_security_workflows() -> None:
    workflows_dir = ROOT / ".github/workflows"
    require(workflows_dir.is_dir(), "missing .github/workflows directory")

    unpinned_uses: list[str] = []
    workflows = sorted({*workflows_dir.glob("*.yaml"), *workflows_dir.glob("*.yml")})
    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            match = EXTERNAL_USES_PATTERN.search(line)
            if match is None:
                continue
            if re.fullmatch(r"[0-9a-f]{40}", match.group("ref")) is None:
                unpinned_uses.append(f"{workflow.relative_to(ROOT)}:{line_no}: {line.strip()}")
    require(not unpinned_uses, "external workflow actions must be pinned by 40-char SHA:\n" + "\n".join(unpinned_uses))

    renovate = ROOT / ".github/renovate.json5"
    require(renovate.is_file(), "missing Renovate dependency update configuration")
    renovate_text = renovate.read_text(encoding="utf-8")
    for marker in ("github-actions", "custom.regex", "pinDigests", "minimumReleaseAge"):
        require(marker in renovate_text, f"Renovate configuration missing patch/rebuild marker: {marker}")

    for filename, reusable in ORG_REUSABLE_CALLER_WORKFLOWS.items():
        path = workflows_dir / filename
        require(path.is_file(), f"missing universal quality-gate caller: .github/workflows/{filename}")
        text = path.read_text(encoding="utf-8")
        if filename == "security.yaml":
            require("schedule:" in text and "workflow_dispatch:" in text, "security.yaml must run on schedule and manually")
        match = REUSABLE_USES_PATTERN.search(text)
        require(
            match is not None,
            f".github/workflows/{filename} must call nwarila-platform/.github/.github/workflows/<reusable>@<40-char-sha>",
        )
        assert match is not None  # for type-checkers
        require(
            match.group("reusable") == reusable,
            f".github/workflows/{filename} must call {reusable} (found {match.group('reusable')})",
        )
        if filename == "repo-hygiene.yaml":
            source_ref = re.search(r"^\s+source_ref:\s*([0-9a-f]{40})\s*$", text, flags=re.MULTILINE)
            require(
                source_ref is not None,
                ".github/workflows/repo-hygiene.yaml must set source_ref to a 40-char SHA",
            )
            assert source_ref is not None
            require(
                source_ref.group(1) == match.group("sha"),
                ".github/workflows/repo-hygiene.yaml source_ref must match the reusable uses SHA",
            )

    codeql_text = (workflows_dir / "codeql.yaml").read_text(encoding="utf-8")
    require(
        "languages:" in codeql_text,
        ".github/workflows/codeql.yaml must override the default languages input",
    )
    for language in ("actions", "python"):
        require(
            f'"{language}"' in codeql_text,
            f".github/workflows/codeql.yaml must include {language!r} in the languages list",
        )


# Image-specific reusable workflow. The build + runtime-hardening pipeline is
# exposed as a reusable workflow so the same contract can be called instead of
# copy-pasting the steps; ci.yaml exercises it as this repository's own
# self-test. Because the binary is compiled inside the Dockerfile, there is NO
# build_app.sh / verify_app_shas prebuilt step.
PUBLISH_WORKFLOW_MARKERS = [
    "branches: [main]",
    "tags:\n      - \"v*\"",
    "workflow_dispatch:",
    "cancel-in-progress: ${{ github.ref == 'refs/heads/main' }}",
    "id-token: write",
    "packages: write",
    "attestations: write",
    "docker/setup-qemu-action@",
    "platforms: amd64,arm64",
    "docker/setup-buildx-action@",
    "sigstore/cosign-installer@",
    "--provenance=mode=max",
    "--sbom=true",
    "--metadata-file dist/image-metadata.json",
    "--push",
    "actions/attest-build-provenance@",
    "push-to-registry: true",
    "cosign sign --recursive",
    "gh attestation verify \"oci://${IMAGE_REF}\" --repo \"${GITHUB_REPOSITORY}\"",
    "cosign verify --recursive",
    "--certificate-identity-regexp",
    "https://token.actions.githubusercontent.com",
    "/.github/workflows/publish-image.yaml@refs/(heads/main|tags/v.*)",
    "oscap-podman",
    "xccdf_org.ssgproject.content_profile_stig",
    "ssg-rhel9-ds.xml",
    "trivy",
    "--ignore-unfixed",
    "--severity HIGH,CRITICAL",
    "grype",
    "tests/runtime-hardening.sh",
    "tools/verify_public_ghcr_pull.sh",
]


def check_template_reusables() -> None:
    workflows_dir = ROOT / ".github/workflows"
    reusable = workflows_dir / "reusable-ubi-image-build.yaml"
    require(
        reusable.is_file(),
        "missing image-build reusable: .github/workflows/reusable-ubi-image-build.yaml",
    )
    text = reusable.read_text(encoding="utf-8")

    require(
        "workflow_call:" in text,
        "reusable-ubi-image-build.yaml must be a workflow_call reusable",
    )
    for inp in ("manifest_path:", "image_tag:", "platform:"):
        require(inp in text, f"reusable-ubi-image-build.yaml must declare input {inp!r}")
    for step in (
        "tools/build_image.sh",
        "tests/runtime-hardening.sh",
    ):
        require(step in text, f"reusable-ubi-image-build.yaml must run {step}")
    # The from-source model has no prebuilt app step.
    require(
        "tools/build_app.sh" not in text,
        "reusable-ubi-image-build.yaml must NOT run a prebuilt build_app.sh (binary is compiled in-Dockerfile)",
    )

    ci_text = (workflows_dir / "ci.yaml").read_text(encoding="utf-8")
    require(
        "uses: ./.github/workflows/reusable-ubi-image-build.yaml" in ci_text,
        "ci.yaml must exercise the image-build reusable via "
        "uses: ./.github/workflows/reusable-ubi-image-build.yaml",
    )


def check_publish_workflow() -> None:
    workflow = ROOT / ".github/workflows/publish-image.yaml"
    require(workflow.is_file(), "missing .github/workflows/publish-image.yaml")
    text = workflow.read_text(encoding="utf-8")
    missing = [marker for marker in PUBLISH_WORKFLOW_MARKERS if marker not in text]
    require(
        not missing,
        "publish-image.yaml missing required release-gate markers: " + ", ".join(missing),
    )
    require("tools/build_app.sh" not in text, "publish-image.yaml must NOT run prebuilt build_app.sh")


MARKDOWN_LINK = re.compile(r"!?\[[^\]]+\]\(([^)]+)\)")


def check_markdown_links() -> None:
    findings: list[str] = []
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in MARKDOWN_LINK.finditer(line):
                target = match.group(1).strip()
                if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                    continue
                target = target.split("#", 1)[0].strip().strip("<>")
                if not target:
                    continue
                candidate = (path.parent / unquote(target)).resolve()
                try:
                    candidate.relative_to(ROOT)
                except ValueError:
                    findings.append(f"{path.relative_to(ROOT)}:{line_no}: link escapes repo: {target}")
                    continue
                if not candidate.exists():
                    findings.append(f"{path.relative_to(ROOT)}:{line_no}: missing link target: {target}")
    require(not findings, "broken local markdown links found:\n" + "\n".join(findings))


WORKFLOW_REF = re.compile(r"(?<![\w/.-])\.github/workflows/([A-Za-z0-9._-]+\.ya?ml)")


def check_doc_workflow_refs() -> None:
    """Every local .github/workflows/*.yaml path cited in a reference doc must
    resolve to a tracked workflow file, so a documented gate cannot become a
    phantom when a workflow is renamed or removed. Cross-repo
    nwarila-platform/.github reusable references are intentionally excluded (the
    lookbehind rejects a preceding path segment)."""
    workflows_dir = ROOT / ".github/workflows"
    findings: list[str] = []
    for path in sorted((ROOT / "docs/reference").rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in WORKFLOW_REF.finditer(line):
                name = match.group(1)
                if not (workflows_dir / name).is_file():
                    findings.append(
                        f"{path.relative_to(ROOT)}:{line_no}: references missing "
                        f"workflow .github/workflows/{name}"
                    )
    require(
        not findings,
        "reference docs cite workflows that do not exist:\n" + "\n".join(findings),
    )


TARGETS = {
    "docs-layout": check_docs_layout,
    "manifest": check_manifest,
    "dockerfile-contract": check_dockerfile_contract,
    "runtime-script": check_runtime_script,
    "compliance-checklist": check_compliance_checklist,
    "build-tool-pins": check_build_tool_pins,
    "build-args": check_build_args_generator,
    "local-build-helper": check_local_build_helper,
    "security-workflows": check_security_workflows,
    "template-reusables": check_template_reusables,
    "publish-workflow": check_publish_workflow,
    "stale-placeholders": check_stale_placeholders,
    "markdown-links": check_markdown_links,
    "doc-workflow-refs": check_doc_workflow_refs,
}

_ORDER = [
    "docs-layout",
    "manifest",
    "dockerfile-contract",
    "runtime-script",
    "compliance-checklist",
    "build-tool-pins",
    "build-args",
    "local-build-helper",
    "security-workflows",
    "template-reusables",
    "publish-workflow",
    "stale-placeholders",
    "markdown-links",
    "doc-workflow-refs",
]

GROUPS = {
    "ci": list(_ORDER),
    "verify": list(_ORDER),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(set(TARGETS) | set(GROUPS)))
    args = parser.parse_args()

    selected = GROUPS.get(args.target, [args.target])
    try:
        for target in selected:
            TARGETS[target]()
            print(f"{target}: ok")
    except (VerifyError, subprocess.CalledProcessError) as exc:
        print(f"verify failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
