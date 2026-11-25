---
type: Example
title: The Rook operator and a Ceph cluster for OpenStack
description: The rook-operator and rook-ceph-cluster Compositions, in the rook-ceph namespace, at the version this release serves.
resource: rook-ceph
tags:
  - krateo
  - example
  - rook
  - ceph
timestamp: 2026-11-19T00:00:00+00:00
---
# examples/basic

The two Compositions, as you apply them once both CompositionDefinitions are registered (docs/usage.md):

- [rook-operator.yaml](rook-operator.yaml): kind `RookOperator`, Rook's operator and CRDs.
- [rook-ceph-cluster.yaml](rook-ceph-cluster.yaml): kind `RookCephCluster`, a Ceph cluster with the pools, users and
  read grant an OpenStack install in namespace `openstack` consumes.

Both are served at `composition.krateo.io/v0-1-0`, the version of this repository's release that installs them, and
both live in `rook-ceph`: the cluster must be in the operator's namespace, where Rook's per-cluster RBAC is.
Applying both at once converges: the cluster refuses to render until Rook's CRDs and that RBAC exist, and then renders
on the next reconcile.
