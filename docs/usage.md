---
type: Usage
title: Installing the Rook blueprints
description: Install order, wiring the OpenStack blueprint, upgrades and removal.
resource: rook-ceph
tags:
  - krateo
  - blueprint
  - rook
  - ceph
  - usage

timestamp: 2026-11-19T00:00:00+00:00
---
# Usage

## Preconditions

- Nodes for the OSDs:
  - raw block devices with no partition table or filesystem, on nodes you label (`osd.source: devices`);
  - or a StorageClass that serves volumeMode Block (`osd.source: storageClass`).
- At least 3 such nodes for size-3 pools on failure domain host.
- The operator and the cluster run privileged (Ceph needs raw device access).

## Install

1. Register both CompositionDefinitions:
   ```console
   kubectl apply -n rook-ceph -f blueprints/rook-operator/compositiondefinition.yaml
   kubectl apply -n rook-ceph -f blueprints/rook-ceph-cluster/compositiondefinition.yaml
   ```
2. Apply [examples/basic/rook-operator.yaml](../examples/basic/rook-operator.yaml).
3. Label the storage nodes (for example `storage-node=true`) and set the device filter to their device names. Then
   apply [examples/basic/rook-ceph-cluster.yaml](../examples/basic/rook-ceph-cluster.yaml) with `consumer.namespace` set
   to the Openstack Composition's namespace.
4. On the Openstack Composition:
   ```yaml
   storage:
     backend: ceph-rook
     ceph:
       sourceNamespace: rook-ceph
   ```
   Its copy store reads the client keys through the grant this cluster renders. With the defaults on both sides, the
   pool and user names agree (`hack/openstack-contract.yaml`).

## Upgrade

A new release of this repository pins a newer Rook. Rook upgrades the operator first, then each Ceph daemon in
turn. Read Rook's upgrade notes for the pinned version before you apply.

## Remove

- Removing rook-ceph-cluster deletes the CephCluster CR. Rook does not wipe disks unless `cleanupPolicy` is set, which
  this chart never sets.
- Removing rook-operator keeps every CRD (`helm.sh/resource-policy: keep`).
