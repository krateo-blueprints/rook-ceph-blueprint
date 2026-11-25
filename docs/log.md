---
type: Log
title: rook-ceph-blueprint changelog
description: Notable changes to the Rook blueprints, with the reasons behind each decision.
resource: rook-ceph
tags:
  - krateo
  - blueprint
  - rook
  - ceph
  - log

timestamp: 2026-11-19T00:00:00+00:00
---
# Log

## 0.1.0 (initial)

- **Rook v1.21.3.** Vendored from `deploy/examples` at the tag. First pinned to v1.21.1 (2026-11-18), then v1.21.2.
  #308's first live run (2026-11-25, GKE, v1.21.2) found its operator exiting every two minutes: with
  `ROOK_CREATE_CSI_OPERATOR_RESOURCES` false the csi.ceph.io CRDs are absent, and two controllers waited for their
  ClientProfile cache forever. v1.21.3 fixes exactly that (rook/rook#18806). The pin used to wait until a release was
  two weeks old, which kept the fix out; it is now the newest release, admitted by the gates and a live run
  (docs/release.md). From v1.21.2, crds.yaml changes only descriptions and operator.yaml only the image tag.
- **Ciphers (`cephx.keyType`, default `aes256k`).** A fresh Ceph 20 cluster still allows the legacy aes cipher and
  reports HEALTH_WARN (AUTH_INSECURE_KEYS_ALLOWED, AUTH_INSECURE_KEYS_CREATABLE), measured in the same run. Rook's
  controller sets the monitors' list from the CephCluster's `security.cephx.allowedCiphers`, and each CephClient's key
  type from its own `security.cephx.keyType`: both are rendered, no Job. OpenStack 2026.1's images carry Ceph 20.2.4
  libraries, which support aes256k.
- **OSD spread.** In the same run two of three claim-backed OSDs landed on one node, which a size-3 pool on failure
  domain host cannot use. The device set now spreads its OSDs and their prepare jobs over the nodes.
- **Two charts.** rook-operator wraps Rook's manifests, with no CSI, because OpenStack uses librbd. rook-ceph-cluster
  renders only custom resources, with the Ceph-docs caps, and the read grant krateo-openstack-blueprint's key copies
  need (#308).
- **Dependabot** groups the pins by source (PUBLISHING.md rule 9).
- **Gates:** the vendored files (`--live`), the versions, a derived render, the OpenStack contract (`--live`), and kind
  admission with negative controls.
