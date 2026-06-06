# Governance

This repository carries workflow files and local checks, but GitHub repository
settings decide whether those checks are merge-blocking. Keep the repository
settings aligned with the organization baseline before treating a green pull
request as release-ready.

## Repository Rulesets

Use rulesets or branch protection to cover the default branch.

| Rule area | Expected setting |
| --- | --- |
| Branch creation, update, deletion | Protected on the default branch. |
| Non-fast-forward updates | Blocked. |
| Linear history | Required when the repository uses squash-only merges. |
| Signed commits | Required if the owning organization requires verified commits. |
| Pull request review | At least one approval, stale approvals dismissed on push, code-owner review required, review-thread resolution required. |
| Allowed merge methods | Squash unless the owning organization has a different baseline. |
| Release tags | Protected from deletion and non-fast-forward updates. |

## Required Status Checks

Rulesets must name real status checks. Empty required-status-check lists make CI
visible but non-blocking.

After a pull request runs, require the exact check names GitHub reports for
these gates:

| Gate | Source |
| --- | --- |
| actionlint | `.github/workflows/ci.yaml` |
| markdownlint | `.github/workflows/ci.yaml` |
| contract verify | `.github/workflows/ci.yaml` |
| image build + hardening | `.github/workflows/ci.yaml` calling `.github/workflows/reusable-ubi-image-build.yaml` |
| CodeQL | `.github/workflows/codeql.yaml` |
| Trivy + Gitleaks + zizmor | `.github/workflows/security.yaml` |
| OpenSSF Scorecard | `.github/workflows/scorecard.yaml` |
| repo hygiene | `.github/workflows/repo-hygiene.yaml` |

Do not require the auto-merge workflow as a merge gate. Auto-merge is the
mechanism that enables GitHub auto-merge for trusted bots after required checks
pass; it is not itself a quality gate.

## CODEOWNERS

`.github/CODEOWNERS` must reference users or teams with write access to the
repository. An organization login by itself is not a valid CODEOWNERS owner.
Verify CODEOWNERS after changes:

```sh
gh api repos/OWNER/REPO/codeowners/errors
```

The expected result is an empty `errors` array.

## Required Signatures

If rulesets require signed commits or signed tags, make that visible in
repository operating notes. Bot commits, release tags, and emergency fixes must
be able to satisfy the signature requirement or use an explicitly approved
bypass path.

## Security Settings

Enable these repository settings or inherit them from the organization:

- Secret scanning.
- Push protection.
- Dependabot alerts and security updates.
- Vulnerability alerts.
- Delete branch on merge.
- Auto-merge, if trusted-bot auto-merge is desired.
- Squash merge as the only allowed merge method, if using the baseline above.

## Actions Policy

This repository calls reusable workflows from
`nwarila-platform/.github` for CodeQL, Scorecard, security scanning, repository
hygiene, and auto-merge. The repository must allow those cross-repository
reusable workflow calls at the pinned SHAs recorded in the workflow files.

## Variables And Secrets

Pull-request CI does not require repository variables or custom secrets. It uses
`GITHUB_TOKEN` with read-only contents permission.

The publish workflow needs package write, ID token, and attestation permissions
for GHCR push, keyless signing, and GitHub artifact attestation. Keep release
credentials in workflow permissions or organization-approved secrets, not in the
manifest or Docker build args.
