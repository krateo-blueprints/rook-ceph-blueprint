---
type: Configuration
title: rook-ceph-blueprint configuration
description: Every value of both charts.
resource: rook-ceph
tags:
  - krateo
  - blueprint
  - rook
  - ceph
  - configuration

timestamp: 2026-11-19T00:00:00+00:00
---
# Configuration

## rook-operator

| Value | Default | Effect |
|---|---|---|
| `image.repository`, `image.tag` | `docker.io/rook/ceph`, `v1.21.2` | The operator image. The tag mirrors appVersion. |
| `image.pullPolicy` | `""` | Empty: upstream's. |
| `logLevel` | `INFO` | ROOK_LOG_LEVEL. |
| `resources`, `nodeSelector` | `{}` | The operator container and pod. |
| `tolerations` | `[]` | Added to upstream's node.kubernetes.io/unreachable toleration. |

## rook-ceph-cluster

| Value | Default | Effect |
|---|---|---|
| `cephVersion.image` | `quay.io/ceph/ceph:v20.2.4` | Rook v1.21.2's default Ceph. |
| `dataDirHostPath` | `/var/lib/rook` | Mon and Rook configuration on each node, when mons have no StorageClass. |
| `mon.count` | `3` | Odd; at least 3 unless `testOnly`. |
| `mon.storageClassName`, `mon.size` | `""`, `10Gi` | A claim per mon from a file-mode class, instead of the host path. |
| `mgr.count` | `2` | Active and standby. |
| `osd.source` | `devices` | `devices` or `storageClass`. |
| `osd.devices.nodeLabel.key/value` | `""` | The storage nodes. Required with devices. |
| `osd.devices.deviceFilter` | `""` | A regular expression over device names. Required with devices. |
| `osd.storageClass.name/count/size` | `""`, `3`, `100Gi` | Block-mode claims, one per OSD. |
| `placement.nodeLabel`, `placement.tolerations` | empty | Every Ceph daemon. |
| `pools.volumes/images/vms` | `cinder.volumes`, `glance.images`, `vms` (off) | The RBD pools, named as the OpenStack blueprint names them. |
| `replication.size`, `replication.failureDomain` | `3`, `host` | Per pool. Below 3 only with `testOnly`. |
| `clients.cinder`, `clients.glance` | `cinder`, `glance` | The Ceph users (CephClient names). |
| `consumer.namespace` | `""` | The Openstack Composition's namespace. Required. |
| `consumer.serviceAccount` | `openstack-credentials-ceph-reader` | Its copy store's ServiceAccount. |
| `testOnly` | `false` | Allows size and mon count below 3, and several mons or mgrs on one node. |
