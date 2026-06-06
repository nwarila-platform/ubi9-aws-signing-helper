# Supply Chain Evidence

Release evidence is tied to the pushed image digest, not to mutable tags. See
[`publish-image.md`](../how-to/publish-image.md) for the concrete workflow.

## Required Evidence

| Evidence | Expected Mechanism |
| --- | --- |
| SBOM | Docker BuildKit SBOM attestation created with `--sbom=true`. The preserved rpm database at `/var/lib/rpm` lets scanners enumerate installed packages. |
| Provenance | Docker BuildKit provenance attestation created with `--provenance=mode=max`. |
| Artifact attestation | GitHub artifact attestation for the pushed image digest. |
| Signature | Cosign/Sigstore keyless signature over the image digest, using `cosign sign --recursive` so attached SBOM and attestation manifests are covered. |
| Compliance and scan | OpenSCAP RHEL 9 STIG advisory scorecard, plus Trivy and Grype vulnerability gates against the pushed digest. |
| Runtime hardening | Output from `tests/runtime-hardening.sh <image-ref> <entrypoint>` against the pushed digest. |
| Public pull | Output from `tools/verify_public_ghcr_pull.sh <image-ref>` proving anonymous GHCR pull works. |

## Anchors

- Red Hat Universal Base Images (UBI), including `ubi-minimal` and `ubi-micro`,
  are freely redistributable RHEL-derived base images:
  <https://catalog.redhat.com/software/base-images>
- `microdnf --installroot` assembles the runtime rootfs while keeping the rpm
  database available to scanners:
  <https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9>
- Docker BuildKit creates provenance and SBOM attestations with `--provenance`
  and `--sbom`:
  <https://docs.docker.com/build/metadata/attestations/>
- GitHub artifact attestations can establish provenance for container images:
  <https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations>
- Sigstore Cosign signs and verifies container images:
  <https://docs.sigstore.dev/quickstart/quickstart-cosign/>
- OpenSCAP evaluates images against SCAP content such as the RHEL 9 STIG
  profile:
  <https://www.open-scap.org/>
- SLSA Build levels describe increasing provenance guarantees:
  <https://slsa.dev/spec/v1.0/levels>
- NIST SP 800-190 is the application container security guide:
  <https://csrc.nist.gov/pubs/sp/800/190/final>

## Review Notes

Docker's local `--load` exporter is for runtime testing only. It does not
preserve SBOM or provenance attestations in the local image store. Publish jobs
must push by digest for registry-backed evidence.

Build args are visible in provenance. Do not put secrets in build args. If a
future source fetch needs private credentials, use BuildKit secrets and document
why the secret is needed before changing the build.
