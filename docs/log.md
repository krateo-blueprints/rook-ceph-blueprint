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

- **Rook v1.21.2.** The newest Rook release at least two weeks old on 2026-11-25 (v1.21.3 was 1 day old), vendored
  from `deploy/examples` at the tag. First pinned to v1.21.1 on 2026-11-18; from v1.21.1, only operator.yaml's image
  tag changed, and the default Ceph image stays v20.2.4.
- **Two charts.** rook-operator wraps Rook's manifests, with no CSI, because OpenStack uses librbd. rook-ceph-cluster
  renders only custom resources, with the Ceph-docs caps, and the read grant krateo-openstack-blueprint's key copies
  need (#308).
- **Dependabot** groups the pins by source (PUBLISHING.md rule 9).
- **Gates:** the vendored files (`--live`), the versions, a derived render, the OpenStack contract (`--live`), and kind
  admission with negative controls.
