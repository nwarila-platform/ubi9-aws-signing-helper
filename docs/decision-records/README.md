# Architecture Decision Records

This directory holds the Architecture Decision Records (ADRs) governing this
repository. Per [org ADR-0001](org/0001-use-architecture-decision-records.md),
ADRs are organized into three scopes:

- `org/` - mirrored org-baseline ADRs from `nwarila-platform/.github`.
- `template/` - mirrored type-template ADRs from the UBI 9 application template
  that apply to every UBI 9 image repository.
- `repo/` - decisions made by this repository only.

`python tools/verify.py ci` checks that the expected org ADR filenames are
present and that every template- and repo-scoped ADR carries the full MADR
heading set. It does not compare the mirrored files byte-for-byte against
`nwarila-platform/.github`; mirror refreshes remain an explicit review task
unless a separate drift gate is added.

## Org ADRs

The `org/` scope is mirrored from `nwarila-platform/.github`.

| ADR | Status | Decision |
| --- | --- | --- |
| [ADR-0001](org/0001-use-architecture-decision-records.md) | Accepted | Use ADRs to document design rationale. |
| [ADR-0002](org/0002-adopt-diataxis-documentation-framework.md) | Accepted | Use Diataxis for non-ADR documentation. |
| [ADR-0003](org/0003-use-deny-all-gitignore-strategy.md) | Accepted | Use deny-all `.gitignore` allowlists. |
| [ADR-0004](org/0004-use-renovate-for-dependency-updates.md) | Accepted | Use Renovate for dependency updates. |
| [ADR-0005](org/0005-keep-github-control-planes-namespace-local.md) | Accepted | Keep GitHub control planes namespace-local. |

## Template ADRs

The `template/` scope is mirrored from the UBI 9 application template.

| ADR | Status | Decision |
| --- | --- | --- |
| [ADR-0001](template/0001-replace-chisel-with-ubi9.md) | Accepted | Build images from Red Hat UBI 9 instead of Ubuntu Chisel. |
| [ADR-0002](template/0002-compliance-gate-openscap-rhel9-stig.md) | Accepted | Gate releases on the OpenSCAP DISA RHEL 9 STIG profile. |
| [ADR-0003](template/0003-publish-image-per-image-frozen-cosign-identity.md) | Accepted | Freeze the Cosign keyless identity to `publish-image.yaml`. |

## Repo ADRs

The `repo/` scope holds decisions specific to this image.

| ADR | Status | Decision |
| --- | --- | --- |
| [ADR-0001](repo/0001-helper-go-native-fips.md) | Accepted | Compile the helper from source with the FIPS 140-3 Go Cryptographic Module. |
