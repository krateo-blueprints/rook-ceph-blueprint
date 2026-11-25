---
type: Component
title: rook-ceph-blueprint
description: Krateo blueprints for the Rook operator (v1.21.3, vendored from Rook's release manifests) and a Ceph cluster for OpenStack as Rook custom resources only.
resource: rook-ceph
tags:
  - krateo
  - blueprint
  - rook
  - ceph

timestamp: 2026-11-19T00:00:00+00:00
---
# rook-ceph-blueprint

Two Compositions:

- `RookOperator`: Rook's CRDs and operator.
- `RookCephCluster`: a Ceph cluster with the pools, the users (CephClients) and the read grant that
  krateo-openstack-blueprint consumes with `storage.backend: ceph-rook`.

Ceph mints every key; the OpenStack blueprint copies them. No client.admin key leaves Rook's namespace.

## Where to go next

- [overview.md](overview.md): why two charts, what each renders, the changes to upstream.
- [usage.md](usage.md): install order, the OpenStack side, upgrades, removal.
- [configuration.md](configuration.md): every value.
- [api.md](api.md): the generated kinds.
- [examples.md](examples.md), [release.md](release.md), [log.md](log.md).
