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

- **Rook v1.21.1.** The newest Rook release at least two weeks old on 2026-11-18T23:56Z (v1.21.2 was 13 days old),
  vendored from `deploy/examples` at the tag.
- **Two charts.** rook-operator wraps Rook's manifests, with no CSI, because OpenStack uses librbd. rook-ceph-cluster
  renders only custom resources, with the Ceph-docs caps, and the read grant krateo-openstack-blueprint's key copies
  need (#308).
- **Gates:** the vendored files (`--live`), the versions, a derived render, the OpenStack contract (`--live`), and kind
  admission with negative controls.
