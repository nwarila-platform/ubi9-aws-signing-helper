# Invariants

The following invariants should remain true for this image repository.

| Invariant | Why It Matters |
| --- | --- |
| The final image uses `FROM ubi-micro`. | Runtime contents stay close to the minimal Red Hat UBI 9 base plus explicit copies. |
| Both the `ubi-minimal` builder and `ubi-micro` runtime images are pinned by digest. | Builds do not silently follow mutable base tags. |
| The Go builder image is pinned by tag and digest. | The validated Go FIPS module selection remains reviewable and Renovate-managed. |
| The runtime rootfs is assembled from the manifest's `dnf.packages`. | Installed RPM contents stay explicit and reviewable. |
| The rpm database is preserved at `/var/lib/rpm`. | Trivy, Grype, and OpenSCAP can enumerate installed packages; deleting it would yield a false "0 CVE" result. |
| The CA bundle lives at `/etc/pki/tls/certs/ca-bundle.crt`. | The helper can validate TLS endpoints using the standard RHEL trust path. |
| The helper is compiled inside the Dockerfile with `GOFIPS140=v1.0.0` and `CGO_ENABLED=1`. | The binary carries the FIPS/cgo provenance required by repo ADR-0001. |
| The Dockerfile asserts `go version -m` and `readelf` evidence before runtime copy. | A non-FIPS, static, or wrong-module binary fails the build before it ships. |
| Runtime user is non-root. | Default execution does not grant root inside the container. |
| Runtime image has no shell and no dnf, microdnf, rpm, yum, curl, or wget. | Post-compromise download and package-install paths are reduced. |
| SBOM, provenance, signature, attestation, scan, and hardening evidence are tied to the pushed digest. | Consumers can verify what was built and how. |
